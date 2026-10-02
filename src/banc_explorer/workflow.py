"""Cache-backed graph workflows shared by the CLI and reproducible demo builder."""

import json
import logging
import math
from dataclasses import dataclass
from pathlib import Path

import polars as pl
from pyarrow import feather

from banc_explorer.config import Settings
from banc_explorer.data.catalog import METADATA, edgelist
from banc_explorer.data.downloader import verify_cache
from banc_explorer.data.metadata import candidates
from banc_explorer.graph.build import ConnectomeGraph, build_graph
from banc_explorer.graph.costs import PathMode
from banc_explorer.graph.paths import NoPathError, find_path, path_result
from banc_explorer.models import PathResult
from banc_explorer.provenance import make_manifest, write_result

log = logging.getLogger(__name__)


@dataclass
class Session:
    graph: ConnectomeGraph
    settings: Settings
    metadata_receipt: dict
    edges_receipt: dict

    def calculate(
        self, source: int, target: int, mode: PathMode, proofread_endpoints: bool = False
    ) -> PathResult:
        found = find_path(
            self.graph,
            source,
            target,
            mode=mode,
            epsilon=self.settings.epsilon,
            proofread_endpoints=proofread_endpoints,
        )
        manifest = make_manifest(
            self.graph,
            source,
            target,
            mode,
            version=self.settings.connectivity_version,
            metadata_receipt=self.metadata_receipt,
            edges_receipt=self.edges_receipt,
            epsilon=self.settings.epsilon,
            proofread_endpoints=proofread_endpoints,
        )
        return path_result(found, manifest)


def open_session(settings: Settings, *, excluded_neurons: tuple[int, ...] = ()) -> Session:
    asset = edgelist(settings.connectivity_version)
    metadata_receipt = verify_cache(METADATA, settings.cache_dir)
    edges_receipt = verify_cache(asset, settings.cache_dir)
    log.info(
        "BANC v888 / connectivity %s / threshold >= %s",
        settings.connectivity_version,
        settings.min_synapse_count,
    )
    graph = build_graph(
        pl.from_arrow(feather.read_table(METADATA.local_path(settings.cache_dir))),
        pl.from_arrow(feather.read_table(asset.local_path(settings.cache_dir))),
        min_synapse_count=settings.min_synapse_count,
        excluded_neurons=excluded_neurons,
    )
    log.info(
        "Graph: %s vertices / %s edges; %s raw endpoint IDs lack metadata (retained)",
        graph.graph.vcount(),
        graph.graph.ecount(),
        graph.coverage["endpoint_ids_without_metadata"],
    )
    return Session(graph, settings, metadata_receipt, edges_receipt)


def choose_demo_pair(
    graph: ConnectomeGraph, *, body_part: str | None = "leg", max_sources: int = 25
) -> tuple[int, int]:
    """One BFS per source to all candidate targets; never an N x M pair-query loop."""
    if max_sources < 1:
        raise ValueError("max_sources must be positive.")
    sources = candidates(graph.metadata, "sensory", body_part=body_part)
    targets = candidates(graph.metadata, "motor", body_part=body_part)
    target_ids = [i for i in targets["banc_888_id"] if i in graph.indices]
    if not target_ids:
        raise NoPathError("No proofread motor candidates match the demo body-part filter.")
    source_ids = [i for i in sources["banc_888_id"] if i in graph.indices][:max_sources]
    for source in source_ids:
        distances = graph.graph.distances(
            source=[graph.indices[source]],
            target=[graph.indices[t] for t in target_ids],
            mode="out",
            weights=None,
        )[0]
        # A multi-step example makes intermediate neurons inspectable. Prefer fewer hops,
        # breaking ties by ID. This is a reproducible selection rule, not a biological claim.
        reachable = [
            (d, t)
            for d, t in zip(distances, target_ids, strict=True)
            if math.isfinite(d) and d >= 2
        ]
        if reachable:
            return source, min(reachable)[1]
    raise NoPathError(
        f"No multi-step demo found among the first {len(source_ids)} matching sensory "
        "candidates. Increase --max-sources or change --body-part."
    )


def export_demo(
    session: Session, directory: Path, *, body_part: str | None = "leg", max_sources: int = 25
) -> list[PathResult]:
    if directory.exists():
        raise ValueError(
            f"Demo directory already exists: {directory}. Choose a new output directory."
        )
    source, target = choose_demo_pair(session.graph, body_part=body_part, max_sources=max_sources)
    results = [
        session.calculate(source, target, mode, proofread_endpoints=True) for mode in PathMode
    ]
    directory.mkdir(parents=True)
    for result in results:
        write_result(result, directory / f"{result.manifest.path_mode.value}.json")
    selection = {
        "dataset": "BANC",
        "materialization": 888,
        "connectivity_version": session.settings.connectivity_version,
        "source_id": str(source),
        "target_id": str(target),
        "body_part": body_part,
        "max_sources": max_sources,
        "rationale": "Proofread sensory and motor metadata candidates matching a literal body-part "
        "substring; first sensory ID with a >=2-hop reachable motor; shortest hop "
        "distance then smallest motor ID. Illustrative structural example only.",
        "path_files": ["hops.json", "normalized.json"],
    }
    (directory / "selection.json").write_text(
        json.dumps(selection, indent=2) + "\n", encoding="utf-8"
    )
    return results
