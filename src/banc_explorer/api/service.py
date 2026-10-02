"""Bounded local jobs backed by the existing graph and versioned scene contract."""

import importlib.util
import logging
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from pathlib import Path
from threading import Lock
from typing import Literal
from uuid import uuid4

import polars as pl
from pydantic import Field, model_validator

from banc_explorer.config import Settings
from banc_explorer.data.catalog import METADATA
from banc_explorer.data.downloader import verify_cache
from banc_explorer.data.metadata import candidates, load_metadata
from banc_explorer.graph.costs import PathMode
from banc_explorer.graph.paths import NoPathError
from banc_explorer.models import Contract, NeuronId, PathNeuron
from banc_explorer.morphology.export import export_scene
from banc_explorer.provenance import write_result
from banc_explorer.workflow import Session, open_session

log = logging.getLogger(__name__)
Kind = Literal["sensory", "motor"]


class PathRequest(Contract):
    source_id: NeuronId
    target_id: NeuronId
    modes: list[PathMode] = Field(
        default_factory=lambda: list(PathMode), min_length=1, max_length=2
    )
    min_synapse_count: int = Field(default=5, ge=1, le=100000, strict=True)
    proofread_endpoints: bool = True
    allow_downloads: bool = False
    include_context: bool = False

    @model_validator(mode="after")
    def distinct_modes(self):
        if len(self.modes) != len(set(self.modes)):
            raise ValueError("Path modes must be distinct.")
        return self


class BusyError(ValueError):
    pass


class ExplorerService:
    def __init__(self, settings: Settings, output: Path, *, offline=False):
        self.settings = settings
        self.output = output.resolve()
        self.offline = offline
        self.metadata = None
        self.metadata_receipt = None
        self.session: Session | None = None
        self.lock = Lock()
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="banc-path")
        self.jobs: dict[str, dict] = {}
        self.active: str | None = None

    def start(self):
        # Starting the API never downloads bulk metadata or connectivity.
        self.metadata_receipt = verify_cache(METADATA, self.settings.cache_dir)
        self.metadata = load_metadata(METADATA.local_path(self.settings.cache_dir))

    def close(self):
        self.executor.shutdown(wait=True, cancel_futures=True)
        self.session = None

    def health(self):
        return {
            "service": "banc-explorer",
            "api_version": 1,
            "dataset": "BANC",
            "materialization": 888,
            "connectivity_version": self.settings.connectivity_version,
            "status": "ready",
            "offline": self.offline,
            "em_available": importlib.util.find_spec("PIL") is not None,
            "metadata_sha256": self.metadata_receipt["sha256"],
        }

    def facets(self):
        result = {}
        for kind, field in [("sensory", "body_part_sensory"), ("motor", "body_part_effector")]:
            frame = candidates(self.metadata, kind, proofread_only=False)
            result[kind] = (
                frame[field].drop_nulls().unique().sort().to_list()
                if field in frame.columns
                else []
            )
        return result

    def search(self, kind: Kind, q="", body_part=None, proofread_only=True, limit=30, offset=0):
        frame = candidates(self.metadata, kind, proofread_only=proofread_only)
        if body_part:
            field = "body_part_sensory" if kind == "sensory" else "body_part_effector"
            frame = (
                frame.filter(pl.col(field) == body_part)
                if field in frame.columns
                else frame.head(0)
            )
        if q:
            names = [
                "banc_888_id",
                "cell_type",
                "nerve",
                "neuromere",
                "side",
                "body_part_sensory",
                "body_part_effector",
                "cell_function",
            ]
            frame = frame.filter(
                pl.any_horizontal(
                    [
                        pl.col(name)
                        .cast(pl.String)
                        .str.to_lowercase()
                        .str.contains(q.lower(), literal=True)
                        .fill_null(False)
                        for name in names
                        if name in frame.columns
                    ]
                )
            )
        total = frame.height
        neurons = []
        for row in frame.slice(offset, limit).to_dicts():
            values = {
                k: row.get(k)
                for k in PathNeuron.model_fields
                if k not in {"id", "metadata_available"}
            }
            neurons.append(
                PathNeuron(id=row["banc_888_id"], metadata_available=True, **values).model_dump(
                    mode="json"
                )
            )
        return {"neurons": neurons, "total": total, "offset": offset, "limit": limit}

    def _validate_endpoints(self, request: PathRequest):
        for neuron_id, kind in [(request.source_id, "sensory"), (request.target_id, "motor")]:
            row = self.metadata.filter(pl.col("banc_888_id") == neuron_id)
            if row.is_empty() or row["super_class"][0] != kind:
                raise ValueError(f"Select a {kind} neuron from the v888 metadata results.")
            if request.proofread_endpoints and row["proofread"][0] is not True:
                raise ValueError(
                    f"Endpoint {neuron_id} is not proofread; change the endpoint filter."
                )

    def submit(self, request: PathRequest):
        self._validate_endpoints(request)
        if request.allow_downloads and self.offline:
            raise ValueError("This server is offline. Uncheck 'Fetch missing scene assets'.")
        with self.lock:
            if self.active is not None:
                raise BusyError("A data job is already running. Wait for it to finish.")
            # Keep a small status history; durable provenance lives in exported bundles.
            while len(self.jobs) >= 32:
                del self.jobs[next(iter(self.jobs))]
            job_id = uuid4().hex
            self.jobs[job_id] = {
                "id": job_id,
                "status": "queued",
                "message": "Waiting for path calculation",
                "request": request.model_dump(mode="json"),
                "results": {},
            }
            self.active = job_id
            initial = deepcopy(self.jobs[job_id])
        self.executor.submit(self._run, job_id, request)
        return initial

    def get_job(self, job_id):
        with self.lock:
            if job_id not in self.jobs:
                raise KeyError(job_id)
            return deepcopy(self.jobs[job_id])

    def submit_em(self, request):
        if importlib.util.find_spec("PIL") is None:
            raise ValueError("Install optional EM support: uv sync --extra api --extra em")
        if request.allow_downloads and self.offline:
            raise ValueError("This server is offline. Uncheck 'Fetch missing EM ranges'.")
        with self.lock:
            if self.active is not None:
                raise BusyError("A data job is already running. Wait for it to finish.")
            while len(self.jobs) >= 32:
                del self.jobs[next(iter(self.jobs))]
            job_id = uuid4().hex
            self.jobs[job_id] = dict(
                id=job_id,
                kind="em",
                status="queued",
                message="Preparing selected-point image context",
                results={},
            )
            self.active = job_id
            initial = deepcopy(self.jobs[job_id])
        self.executor.submit(self._run_em, job_id, request)
        return initial

    def _run_em(self, job_id, request):
        from banc_explorer.em.service import build_em_scene

        try:
            self._update(
                job_id, status="running", message="Reading bounded EM ranges (32 MB transfer cap)"
            )
            directory = self.output / job_id / "em"
            manifest = build_em_scene(request, self.settings.cache_dir, directory, self.offline)
            self._update(
                job_id,
                status="complete",
                message="Selected-point image context ready",
                results=dict(
                    roi_directory=str(directory),
                    downloaded_bytes=manifest.downloaded_bytes,
                    neuron_id=str(manifest.point.neuron_id),
                    swc_node_id=manifest.point.swc_node_id,
                ),
            )
        except (ValueError, OSError) as exc:
            self._update(job_id, status="error", error_code="data_error", message=str(exc))
            log.warning("EM job %s failed: %s", job_id, exc)
        except Exception:
            log.exception("Unexpected EM job failure: %s", job_id)
            self._update(
                job_id,
                status="error",
                error_code="internal_error",
                message="Unexpected EM error; see the API log.",
            )
        finally:
            with self.lock:
                if self.active == job_id:
                    self.active = None

    def _update(self, job_id, **values):
        with self.lock:
            self.jobs[job_id].update(values)
            if values.get("status") in {"complete", "error"} and self.active == job_id:
                # A terminal status and permission to submit the next job are atomic.
                self.active = None

    def _run(self, job_id, request):
        try:
            self._update(
                job_id, status="running", message="Loading verified connectivity and building graph"
            )
            if (
                self.session is None
                or self.session.settings.min_synapse_count != request.min_synapse_count
            ):
                # Retain only one graph. Release it before building a different threshold.
                self.session = None
                settings = self.settings.model_copy(
                    update={"min_synapse_count": request.min_synapse_count}
                )
                session = open_session(settings)
                if session.metadata_receipt["sha256"] != self.metadata_receipt["sha256"]:
                    raise ValueError(
                        "Metadata cache changed. Restart the local API to use the new snapshot."
                    )
                self.session = session
            self._update(job_id, message="Calculating directed graph paths")
            results = [
                self.session.calculate(
                    request.source_id, request.target_id, mode, request.proofread_endpoints
                )
                for mode in request.modes
            ]
            if any(len(result.neurons) > 40 for result in results):
                raise ValueError(
                    "This viewer limits paths to 40 neurons. Choose closer endpoints or a different threshold."
                )
            directory = self.output / job_id
            directory.mkdir(parents=True)
            summaries = {}
            for result in results:
                mode = result.manifest.path_mode.value
                path_file = directory / f"{mode}.json"
                write_result(result, path_file)
                self._update(
                    job_id,
                    message=f"Preparing {mode} scene: {len(result.neurons)} selected skeletons",
                )
                scene_dir = directory / mode
                scene = export_scene(
                    path_file,
                    scene_dir,
                    self.settings.cache_dir,
                    offline=not request.allow_downloads or self.offline,
                    include_context=request.include_context,
                )
                node_count = sum(n.node_count for n in scene.neurons)
                if node_count > 1_000_000:
                    raise ValueError(
                        "Scene exceeds the viewer's one-million-point budget. Choose a smaller path."
                    )
                summaries[mode] = {
                    "scene_directory": str(scene_dir),
                    "hop_count": result.hop_count,
                    "total_cost": result.total_cost,
                    "neuron_ids": [str(n.id) for n in result.neurons],
                    "node_count": node_count,
                }
            self._update(
                job_id, status="complete", message="Verified scenes ready", results=summaries
            )
        except (ValueError, OSError) as exc:
            code = "no_path" if isinstance(exc, NoPathError) else "data_error"
            self._update(
                job_id,
                status="error",
                error_code=code,
                message=str(exc).replace("--min-synapse-count", "minimum synapse count"),
            )
            log.warning("Path job %s failed: %s", job_id, exc)
        except Exception:
            log.exception("Unexpected path job failure: %s", job_id)
            self._update(
                job_id,
                status="error",
                error_code="internal_error",
                message="Unexpected server error; see the local API terminal log.",
            )
        finally:
            with self.lock:
                if self.active == job_id:
                    self.active = None
