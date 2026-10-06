"""Validated, portable selected-edge subsets with conservative count semantics."""

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal, Protocol

from pydantic import Field, model_validator

from banc_explorer import __version__
from banc_explorer.models import Contract, NeuronId, PathResult, PositiveCount, SourceFile
from banc_explorer.morphology.export import safe_file, staging_directory
from banc_explorer.morphology.models import Digest
from banc_explorer.morphology.transforms import Vector3
from banc_explorer.synapses.transport import BASE, MAX_RESPONSE, CaveTransport

INTERPRETATION = (
    "Predicted synapse subset from CAVE v888; not independently verified contacts "
    "or guaranteed reproduction of the static edgelist."
)


class SynapseRow(Contract):
    id: NeuronId
    pre_root_id: NeuronId
    post_root_id: NeuronId
    size: PositiveCount
    center_nm: Vector3


class Evidence(Contract):
    schema_version: Literal[1] = 1
    artifact_type: Literal["synapse_evidence"] = "synapse_evidence"
    dataset: Literal["BANC"] = "BANC"
    materialization: Literal[888] = 888
    connectivity_version: Literal["v2", "v3"]
    table: Literal["synapses_v2", "synapses_v3"]
    path_sha256: Digest
    edgelist_source: SourceFile
    pre: NeuronId
    post: NeuronId
    graph_count: PositiveCount
    min_size: PositiveCount
    limit: int = Field(strict=True, ge=1, le=1000)
    response_rows: int = Field(strict=True, ge=0, le=1001)
    limit_reached: bool = Field(strict=True)
    server_warning: bool = Field(strict=True)
    count_comparison: Literal["matches", "differs", "incomplete"]
    coordinate_field: Literal["ctr_pt_position"] = "ctr_pt_position"
    coordinate_units: Literal["nm"] = "nm"
    native_resolution_nm: Vector3
    response_resolution_nm: tuple[Literal[1], Literal[1], Literal[1]] = (1, 1, 1)
    version_timestamp: str = Field(min_length=1, max_length=100)
    query: dict
    receipts: list[SourceFile] = Field(min_length=4, max_length=4)
    rows: list[SynapseRow] = Field(max_length=1000)
    interpretation: Literal[INTERPRETATION] = INTERPRETATION
    created_at: datetime
    software_version: str

    @model_validator(mode="after")
    def check_subset(self):
        if self.table != f"synapses_{self.connectivity_version}":
            raise ValueError("Synapse detector/table version mismatch.")
        if self.min_size != (10 if self.connectivity_version == "v3" else 5):
            raise ValueError("Unexpected detector size filter.")
        if any(v <= 0 for v in self.native_resolution_nm):
            raise ValueError("Missing native coordinate resolution.")
        if (
            self.pre == self.post
            or self.response_rows > self.limit + 1
            or self.limit_reached != (self.response_rows > self.limit)
            or len(self.rows) != min(self.limit, self.response_rows)
            or len({row.id for row in self.rows}) != len(self.rows)
        ):
            raise ValueError("Inconsistent synapse subset size/identity.")
        for row in self.rows:
            if (row.pre_root_id, row.post_root_id) != (self.pre, self.post):
                raise ValueError("Synapse row does not match the selected directed edge.")
            if row.size < self.min_size:
                raise ValueError("Synapse response violates the size filter.")
        expected = (
            "incomplete"
            if self.limit_reached or self.server_warning
            else "matches"
            if len(self.rows) == self.graph_count
            else "differs"
        )
        if self.count_comparison != expected:
            raise ValueError("Synapse count comparison disagrees with the response.")
        if self.query != query_payload(self.table, self.pre, self.post, self.min_size, self.limit):
            raise ValueError("Synapse query provenance does not match its subset.")
        endpoints = ("", "/tables", f"/table/{self.table}/metadata", query_suffix(self.table))
        if [r.url for r in self.receipts] != [BASE + e for e in endpoints]:
            raise ValueError("Unexpected CAVE source/version receipts.")
        return self


def query_suffix(table):
    return f"/table/{table}/query?return_pyarrow=false&split_positions=false"


def query_payload(table, pre, post, min_size, limit):
    return {
        "filter_equal_dict": {table: {"pre_pt_root_id": str(pre), "post_pt_root_id": str(post)}},
        "filter_greater_equal_dict": {table: {"size": min_size}},
        "select_columns": ["id", "pre_pt_root_id", "post_pt_root_id", "size", "ctr_pt_position"],
        "desired_resolution": [1, 1, 1],
        "limit": limit + 1,
    }


class SynapseProvider(Protocol):
    def fetch(
        self, result: PathResult, path_sha256: str, edge_index: int, limit: int
    ) -> Evidence: ...


class CaveSynapseProvider:
    def __init__(self, transport=None):
        self.transport = transport if transport is not None else CaveTransport()

    def fetch(self, result, path_sha256, edge_index=0, limit=250):
        if type(limit) is not int or not 1 <= limit <= 1000:
            raise ValueError("Synapse limit must be between 1 and 1000.")
        if type(edge_index) is not int or not 0 <= edge_index < len(result.edges):
            raise ValueError("Select an existing directed path edge (zero-based index).")
        edge = result.edges[edge_index]
        version = result.manifest.connectivity_version
        table = f"synapses_{version}"
        receipts = []
        warned = False

        def read(suffix, payload=None, **kwargs):
            nonlocal warned
            data, resolution, warning, receipt = self.transport.read(suffix, payload, **kwargs)
            receipts.append(SourceFile(**receipt))
            warned = warned or warning
            return data, resolution

        metadata, _ = read("")
        if (
            not isinstance(metadata, dict)
            or type(metadata.get("version")) is not int
            or metadata["version"] != 888
            or metadata.get("datastack") != "brain_and_nerve_cord"
            or metadata.get("valid") is not True
            or not isinstance(metadata.get("time_stamp"), str)
        ):
            raise ValueError("CAVE did not confirm valid BANC materialization v888.")
        tables, _ = read("/tables")
        if not isinstance(tables, list) or table not in tables:
            raise ValueError(f"CAVE v888 does not expose {table}. No live/version fallback used.")
        table_meta, _ = read(f"/table/{table}/metadata")
        if not isinstance(table_meta, dict) or table_meta.get("table_name") != table:
            raise ValueError("CAVE table metadata does not match the requested detector.")
        native = tuple(table_meta.get(f"voxel_resolution_{axis}") for axis in "xyz")
        if any(type(v) not in (int, float) or not 0 < v < 1e6 for v in native):
            raise ValueError("CAVE table has no valid coordinate resolution; refusing to guess.")
        min_size = 10 if version == "v3" else 5
        query = query_payload(table, edge.pre, edge.post, min_size, limit)
        # Wire integers preserve exact IDs for SQL; portable JSON uses decimal strings.
        wire_query = query | {
            "filter_equal_dict": {table: {"pre_pt_root_id": edge.pre, "post_pt_root_id": edge.post}}
        }
        data, resolution = read(query_suffix(table), wire_query, limit=MAX_RESPONSE)
        try:
            verified_resolution = json.loads(resolution or "null")
        except ValueError:
            verified_resolution = None
        if verified_resolution != [1, 1, 1]:
            raise ValueError("CAVE did not confirm nm response coordinates; refusing to guess.")
        if not isinstance(data, list) or len(data) > limit + 1:
            raise ValueError("CAVE response violated the bounded row limit.")
        rows = []
        for row in data:
            if not isinstance(row, dict):
                raise ValueError("CAVE returned an invalid synapse row.")
            try:
                rows.append(
                    SynapseRow(
                        id=row["id"],
                        pre_root_id=row["pre_pt_root_id"],
                        post_root_id=row["post_pt_root_id"],
                        size=row["size"],
                        center_nm=row["ctr_pt_position"],
                    )
                )
            except (KeyError, ValueError):
                raise ValueError(
                    "CAVE synapse schema changed or contains invalid values."
                ) from None
        # Validate even the sentinel; it must be from the same query and not duplicate an ID.
        if len({r.id for r in rows}) != len(rows) or any(
            (r.pre_root_id, r.post_root_id) != (edge.pre, edge.post) or r.size < min_size
            for r in rows
        ):
            raise ValueError("CAVE ignored edge/size filters or returned duplicate synapse IDs.")
        capped = len(rows) > limit
        return Evidence(
            connectivity_version=version,
            table=table,
            path_sha256=path_sha256,
            edgelist_source=result.manifest.edgelist_source,
            pre=edge.pre,
            post=edge.post,
            graph_count=edge.count,
            min_size=min_size,
            limit=limit,
            response_rows=len(rows),
            limit_reached=capped,
            server_warning=warned,
            count_comparison="incomplete"
            if capped or warned
            else "matches"
            if len(rows) == edge.count
            else "differs",
            native_resolution_nm=native,
            version_timestamp=metadata["time_stamp"],
            query=query,
            receipts=receipts,
            rows=rows[:limit],
            created_at=datetime.now(UTC),
            software_version=__version__,
        )


def export_evidence(
    provider: SynapseProvider, path: Path, directory: Path, *, edge_index=0, limit=250
):
    if directory.exists():
        raise ValueError("Evidence output already exists; choose a new directory.")
    if path.stat().st_size > 2_000_000:
        raise ValueError("Path result exceeds the 2 MB budget.")
    data = path.read_bytes()
    result = PathResult.model_validate_json(data)
    evidence = provider.fetch(result, hashlib.sha256(data).hexdigest(), edge_index, limit)
    directory.parent.mkdir(parents=True, exist_ok=True)
    with staging_directory(directory.parent) as stage:
        (stage / "graph-path.json").write_bytes(data)
        (stage / "evidence.json").write_text(
            evidence.model_dump_json(indent=2) + "\n", encoding="utf-8"
        )
        load_evidence(stage)
        stage.rename(directory)
    return evidence


def load_evidence(directory: Path) -> Evidence:
    evidence_file = safe_file(directory, "evidence.json")
    path_file = safe_file(directory, "graph-path.json")
    if any(p.stat().st_size > 2_000_000 for p in (evidence_file, path_file)):
        raise ValueError("Synapse evidence exceeds the 2 MB file budget.")
    evidence = Evidence.model_validate_json(evidence_file.read_bytes())
    data = path_file.read_bytes()
    result = PathResult.model_validate_json(data)
    if hashlib.sha256(data).hexdigest() != evidence.path_sha256:
        raise ValueError("Evidence path checksum mismatch.")
    if (
        result.manifest.connectivity_version != evidence.connectivity_version
        or result.manifest.edgelist_source != evidence.edgelist_source
        or not any(
            (e.pre, e.post, e.count) == (evidence.pre, evidence.post, evidence.graph_count)
            for e in result.edges
        )
    ):
        raise ValueError("Evidence does not match the source graph path/version.")
    return evidence
