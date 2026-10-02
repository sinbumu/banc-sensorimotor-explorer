import math

import polars as pl
import pytest

from banc_explorer.graph.build import build_graph
from banc_explorer.graph.costs import PathMode, normalized_cost, raw_count_cost
from banc_explorer.graph.paths import NoPathError, find_path


def ids(found):
    return [n.id for n in found.neurons]


def test_objectives_differ(toy_tables):
    graph = build_graph(*toy_tables)
    hops = find_path(graph, 1, 5)
    strength = find_path(graph, 1, 5, mode=PathMode.normalized)
    assert ids(hops) == [1, 2, 5]
    assert [e.cost for e in hops.edges] == [1, 1]
    assert ids(strength) == [1, 3, 4, 5]
    assert math.fsum(e.cost for e in strength.edges) == pytest.approx(-math.log(0.9**3))


def test_direction_disconnected_unknown_and_identity(toy_tables):
    graph = build_graph(*toy_tables)
    for source, target in [(5, 1), (1, 6)]:
        with pytest.raises(NoPathError, match="No directed path"):
            find_path(graph, source, target)
    assert ids(find_path(graph, 6, 6)) == [6]
    assert find_path(graph, 6, 6).edges == []
    with pytest.raises(ValueError, match="Unknown"):
        find_path(graph, 100, 1)


def test_intervention_threshold_and_original_totals(toy_tables):
    original = build_graph(*toy_tables)
    excluded = build_graph(*toy_tables, excluded_neurons=(2,))
    thresholded = build_graph(*toy_tables, min_synapse_count=6)
    assert ids(find_path(excluded, 1, 5)) == [1, 3, 4, 5]
    assert ids(find_path(thresholded, 1, 5)) == [1, 3, 4, 5]
    assert find_path(excluded, 1, 5).edges[-1].post_count == 100
    assert original.graph.ecount() == 5
    with pytest.raises(ValueError, match="excluded"):
        find_path(excluded, 2, 5)
    with pytest.raises(ValueError, match="Excluded"):
        build_graph(*toy_tables, excluded_neurons=(999,))
    empty = build_graph(*toy_tables, min_synapse_count=101)
    with pytest.raises(NoPathError):
        find_path(empty, 1, 5)


def test_missing_metadata_and_endpoint_proofread(toy_tables):
    meta, edges = toy_tables
    graph = build_graph(meta.filter(pl.col("banc_888_id") != 2), edges)
    found = find_path(graph, 1, 5, proofread_endpoints=True)
    assert ids(found) == [1, 2, 5]
    assert found.neurons[1].metadata_available is False
    assert graph.coverage["endpoint_ids_without_metadata"] == 1
    with pytest.raises(ValueError, match="proofread"):
        find_path(graph, 2, 5, proofread_endpoints=True)


def test_edge_order_and_integer_mapping(toy_tables):
    meta, edges = toy_tables
    offset = 720575940000000000
    meta = meta.with_columns(pl.col("banc_888_id") + offset)
    edges = edges.reverse().with_columns(pl.col("pre") + offset, pl.col("post") + offset)
    found = find_path(build_graph(meta, edges), offset + 1, offset + 5)
    assert ids(found) == [offset + 1, offset + 2, offset + 5]
    assert [(e.pre, e.post, e.count) for e in found.edges] == [
        (offset + 1, offset + 2, 5),
        (offset + 2, offset + 5, 5),
    ]


def test_costs_and_zero_cost_route():
    assert normalized_cost(1) == 0
    assert normalized_cost(0, 1e-12) == pytest.approx(-math.log(1e-12))
    assert raw_count_cost(9) == pytest.approx(1 / math.log(10))
    for bad in [-1, 1.1, float("nan"), float("inf")]:
        with pytest.raises(ValueError):
            normalized_cost(bad)
    for bad in [0, -1, float("nan"), 2]:
        with pytest.raises(ValueError):
            normalized_cost(0.5, bad)
    meta = pl.DataFrame(
        {
            "banc_888_id": [1, 2, 3],
            "super_class": ["sensory", "intrinsic", "motor"],
            "proofread": [True] * 3,
        }
    )
    edge = pl.DataFrame(
        {
            "pre": [1, 2],
            "post": [2, 3],
            "count": [5, 5],
            "norm": [1.0, 1.0],
            "pre_count": [5, 5],
            "post_count": [5, 5],
        }
    )
    found = find_path(build_graph(meta, edge), 1, 3, mode=PathMode.normalized)
    assert ids(found) == [1, 2, 3]
    assert sum(e.cost for e in found.edges) == 0
