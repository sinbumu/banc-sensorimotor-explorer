from datetime import UTC, datetime
from pathlib import Path

import igraph

from banc_explorer import __version__
from banc_explorer.graph.build import ConnectomeGraph
from banc_explorer.graph.costs import PathMode, cost_definition
from banc_explorer.models import Manifest, PathResult, SourceFile


def source_file(receipt: dict) -> SourceFile:
    return SourceFile(**{k: receipt.get(k) for k in SourceFile.model_fields})


def make_manifest(
    graph: ConnectomeGraph,
    source: int,
    target: int,
    mode: PathMode,
    *,
    version: str,
    metadata_receipt: dict,
    edges_receipt: dict,
    epsilon: float,
    proofread_endpoints: bool,
) -> Manifest:
    return Manifest(
        connectivity_version=version,
        metadata_source=source_file(metadata_receipt),
        edgelist_source=source_file(edges_receipt),
        min_synapse_count=graph.min_synapse_count,
        path_mode=mode,
        cost_definition=cost_definition(mode),
        epsilon=epsilon,
        source_ids=[source],
        target_ids=[target],
        excluded_neurons=graph.excluded_neurons,
        filters={
            "proofread_endpoints": proofread_endpoints,
            "intermediate_neuron_filter": None,
            "metadata_missing_policy": "retain",
            "direction": "pre_to_post",
        },
        graph_vertices=graph.graph.vcount(),
        graph_edges=graph.graph.ecount(),
        coverage=graph.coverage,
        created_at=datetime.now(UTC),
        software_version=__version__,
        igraph_version=igraph.__version__,
    )


def write_result(result: PathResult, path: Path) -> None:
    # Validate the final serialized contract, including IDs and all path invariants.
    payload = result.model_dump_json(indent=2)
    PathResult.model_validate_json(payload)
    if path.exists():
        raise ValueError(f"Output already exists: {path}. Choose a new output path.")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as stream:
        stream.write(payload + "\n")
