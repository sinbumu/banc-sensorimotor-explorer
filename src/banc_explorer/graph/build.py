from dataclasses import dataclass

import igraph as ig
import polars as pl

from banc_explorer.data.edges import EDGE_COLUMNS, filter_edges, normalize_edges
from banc_explorer.data.metadata import normalize_metadata
from banc_explorer.models import parse_id


@dataclass
class ConnectomeGraph:
    graph: ig.Graph
    edges: pl.DataFrame
    metadata: pl.DataFrame
    ids: list[int]
    indices: dict[int, int]
    min_synapse_count: int
    excluded_neurons: list[int]
    coverage: dict


def build_graph(
    metadata: pl.DataFrame,
    edges: pl.DataFrame,
    *,
    min_synapse_count: int = 5,
    excluded_neurons: tuple[int, ...] = (),
) -> ConnectomeGraph:
    """Validate once, retain metadata-less vertices, then filter without changing input totals."""
    metadata = normalize_metadata(metadata)
    edges = normalize_edges(edges).select(EDGE_COLUMNS)
    endpoints = pl.concat([edges["pre"], edges["post"]]).unique().sort()
    missing = endpoints.filter(~endpoints.is_in(metadata["banc_888_id"].implode()))
    coverage = {
        "raw_edges": edges.height,
        "raw_endpoint_ids": len(endpoints),
        "endpoint_ids_without_metadata": len(missing),
        "missing_metadata_examples": [str(x) for x in missing.head(10)],
        "metadata_without_raw_edges": metadata.filter(
            ~pl.col("banc_888_id").is_in(endpoints.implode())
        ).height,
    }
    all_ids = pl.concat([endpoints, metadata["banc_888_id"].rename("pre")]).unique().sort()
    excluded = sorted({parse_id(value) for value in excluded_neurons})
    if set(excluded) - set(all_ids):
        raise ValueError("Excluded neuron ID is not present in metadata or connectivity.")
    # Include isolated metadata neurons: source==target is a valid zero-hop query.
    ids = all_ids.filter(~all_ids.is_in(excluded)).to_list()
    edges = (
        filter_edges(edges, min_synapse_count)
        .filter(~pl.col("pre").is_in(excluded) & ~pl.col("post").is_in(excluded))
        .sort("pre", "post")
    )
    lookup = pl.DataFrame({"id": ids}, schema={"id": pl.UInt64}).with_row_index("index")
    dense = (
        edges.select("pre", "post")
        .join(lookup.rename({"id": "pre", "index": "source"}), on="pre", maintain_order="left")
        .join(lookup.rename({"id": "post", "index": "target"}), on="post", maintain_order="left")
    )
    # No Python dictionary per edge; igraph receives dense integer vertex indices.
    graph = ig.Graph(
        n=len(ids), edges=dense.select("source", "target").to_numpy().astype("int64"), directed=True
    )
    return ConnectomeGraph(
        graph,
        edges,
        metadata,
        ids,
        {v: i for i, v in enumerate(ids)},
        min_synapse_count,
        excluded,
        coverage,
    )
