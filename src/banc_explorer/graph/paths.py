import math
import warnings
from dataclasses import dataclass

import polars as pl

from banc_explorer.graph.build import ConnectomeGraph
from banc_explorer.graph.costs import PathMode, normalized_weights
from banc_explorer.models import Manifest, PathEdge, PathNeuron, PathResult, parse_id


class NoPathError(ValueError):
    pass


@dataclass
class FoundPath:
    neurons: list[PathNeuron]
    edges: list[PathEdge]


def find_path(
    graph: ConnectomeGraph,
    source: int,
    target: int,
    *,
    mode: PathMode = PathMode.hops,
    epsilon: float = 1e-12,
    proofread_endpoints: bool = False,
) -> FoundPath:
    mode = PathMode(mode)
    source, target = parse_id(source), parse_id(target)
    # Validate epsilon even for hops, since it will be included in the manifest.
    if not math.isfinite(epsilon) or not 0 < epsilon <= 1:
        raise ValueError("epsilon must be finite and in (0, 1].")
    for neuron_id in [source, target]:
        if neuron_id in graph.excluded_neurons:
            raise ValueError(f"Endpoint {neuron_id} is excluded by this graph intervention.")
        if neuron_id not in graph.indices:
            raise ValueError(f"Unknown neuron ID: {neuron_id}.")
        if proofread_endpoints:
            row = graph.metadata.filter(pl.col("banc_888_id") == neuron_id)
            if row.is_empty() or row["proofread"][0] is not True:
                raise ValueError(f"Endpoint {neuron_id} is not a proofread metadata neuron.")
    weights = None
    if mode == PathMode.normalized:
        weights = normalized_weights(
            graph.edges["count"].to_numpy(), graph.edges["post_count"].to_numpy(), epsilon
        )
    with warnings.catch_warnings():
        warnings.filterwarnings(
            "ignore", message=".*Couldn't reach some vertices.*", category=RuntimeWarning
        )
        edge_ids = graph.graph.get_shortest_paths(
            graph.indices[source],
            to=graph.indices[target],
            weights=weights,
            mode="out",
            output="epath",
        )[0]
    if not edge_ids and source != target:
        raise NoPathError(
            "No directed path exists under the current threshold. "
            "Try lowering --min-synapse-count or changing the target."
        )
    path_edges = []
    ids = [source]
    for edge_id in edge_ids:
        row = graph.edges.row(edge_id, named=True)
        path_edges.append(
            PathEdge(
                **row,
                normalized_input=row["count"] / row["post_count"],
                cost=1.0 if weights is None else float(weights[edge_id]),
            )
        )
        ids.append(row["post"])
    annotations = {
        row["banc_888_id"]: row
        for row in graph.metadata.filter(pl.col("banc_888_id").is_in(ids)).to_dicts()
    }
    neurons = []
    for neuron_id in ids:
        row = annotations.get(neuron_id, {})
        values = {
            k: row.get(k) for k in PathNeuron.model_fields if k not in {"id", "metadata_available"}
        }
        neurons.append(PathNeuron(id=neuron_id, metadata_available=bool(row), **values))
    return FoundPath(neurons, path_edges)


def path_result(found: FoundPath, manifest: Manifest) -> PathResult:
    return PathResult(
        manifest=manifest,
        neurons=found.neurons,
        edges=found.edges,
        hop_count=len(found.edges),
        total_cost=math.fsum(e.cost for e in found.edges),
    )
