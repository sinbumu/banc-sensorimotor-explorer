import json
import math
from pathlib import Path

import polars as pl
import pytest

from banc_explorer.config import Settings
from banc_explorer.graph.build import build_graph
from banc_explorer.graph.costs import PathMode
from banc_explorer.graph.paths import NoPathError, find_path
from banc_explorer.models import PathResult
from banc_explorer.provenance import write_result
from banc_explorer.workflow import Session, choose_demo_pair, export_demo


@pytest.fixture
def session(toy_tables):
    receipt = {"url": "synthetic-fixture", "sha256": "a" * 64, "bytes": 1, "generation": None}
    return Session(build_graph(*toy_tables), Settings(), receipt, receipt)


def test_manifest_round_trip_and_no_overwrite(session, tmp_path):
    result = session.calculate(1, 5, PathMode.normalized)
    path = tmp_path / "result.json"
    write_result(result, path)
    restored = PathResult.model_validate_json(path.read_text())
    assert restored == result
    payload = json.loads(path.read_text())
    assert payload["neurons"][0]["id"] == "1"
    assert payload["manifest"]["source_ids"] == ["1"]
    with pytest.raises(ValueError, match="already exists"):
        write_result(result, path)


@pytest.mark.parametrize(
    "mutation",
    [
        lambda d: d.update(schema_version=99),
        lambda d: d["neurons"][0].update(id=1.0),
        lambda d: d["edges"][0].update(pre="2"),
        lambda d: d["edges"][0].update(cost=20),
        lambda d: d["edges"][0].update(normalized_input=0.5),
        lambda d: d.update(total_cost=99),
        lambda d: d["manifest"].update(excluded_neurons=["1"]),
        lambda d: d["manifest"].update(cost_definition="transmission probability"),
    ],
)
def test_reject_inconsistent_contract(session, mutation):
    payload = session.calculate(1, 5, PathMode.hops).model_dump(mode="json")
    mutation(payload)
    with pytest.raises(ValueError):
        PathResult.model_validate(payload)


def test_demo_selection_and_exports(session, tmp_path):
    assert choose_demo_pair(session.graph) == (1, 5)
    directory = tmp_path / "demo"
    results = export_demo(session, directory)
    assert [r.hop_count for r in results] == [2, 3]
    selection = json.loads((directory / "selection.json").read_text())
    assert selection["source_id"] == "1"
    assert selection["target_id"] == "5"
    assert selection["rationale"]
    with pytest.raises(NoPathError):
        choose_demo_pair(session.graph, body_part="nonexistent")


def test_real_sample_exact_ids_values_and_recomputed_norm():
    fixture = json.loads(
        (Path(__file__).parent / "fixtures/banc_v888_v3_path_sample.json").read_text()
    )
    metadata = pl.DataFrame(fixture["metadata"])
    edges = pl.DataFrame(fixture["edges"])
    graph = build_graph(metadata, edges)
    source, target = int(metadata["banc_888_id"][0]), int(metadata["banc_888_id"][-1])
    hops = find_path(graph, source, target)
    strength = find_path(graph, source, target, mode=PathMode.normalized)
    assert [n.id for n in hops.neurons] == [int(x) for x in metadata["banc_888_id"]]
    assert [e.count for e in hops.edges] == [11, 10]
    assert strength.edges[0].cost == pytest.approx(-math.log(11 / 1525))
    assert strength.edges[0].cost != pytest.approx(-math.log(0.007213), abs=1e-9, rel=0)
    assert strength.edges[0].norm == 0.007213
    session = Session(graph, Settings(), fixture["metadata_source"], fixture["edgelist_source"])
    result = session.calculate(source, target, PathMode.normalized)
    restored = PathResult.model_validate_json(result.model_dump_json())
    assert restored.neurons[0].id == 720575941350568496
