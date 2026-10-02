import polars as pl
import pytest

from banc_explorer.config import Settings
from banc_explorer.graph.build import build_graph, filtered_graph
from banc_explorer.graph.costs import PathMode
from banc_explorer.graph.interventions import (
    InterventionReport,
    InterventionRules,
    compare_intervention,
)
from banc_explorer.workflow import Session


@pytest.fixture
def session(toy_tables):
    metadata, edges = toy_tables
    metadata = metadata.with_columns(
        pl.Series("cell_type", ["SN", "weak", "strong", "strong", "MN", None]),
        pl.Series("side", ["right", "left", "right", "right", "right", None]),
    )
    receipt = dict(url="synthetic", sha256="a" * 64, bytes=1, generation=None)
    return Session(build_graph(metadata, edges), Settings(), receipt, receipt)


@pytest.mark.parametrize("mode", list(PathMode))
def test_neuron_intervention_keeps_objective_totals_and_baseline(session, mode):
    before = session.calculate(1, 5, mode)
    excluded = 2 if mode == PathMode.hops else 3
    report = compare_intervention(session, before, InterventionRules(excluded_neurons=[excluded]))
    assert report.after is not None
    assert [n.id for n in report.after.neurons] == (
        [1, 3, 4, 5] if mode == PathMode.hops else [1, 2, 5]
    )
    assert all(e.post_count == 100 for e in report.after.edges)
    assert report.after.manifest.path_mode == mode
    assert report.summary()["removed_ids"] == (["2"] if mode == PathMode.hops else ["3", "4"])
    assert session.calculate(1, 5, mode).neurons == before.neurons
    assert not session.graph.excluded_neurons
    assert InterventionReport.model_validate_json(report.model_dump_json()) == report


def test_cell_type_side_and_threshold_rules(session):
    before = session.calculate(1, 5, PathMode.normalized)
    report = compare_intervention(
        session, before, InterventionRules(excluded_cell_types=["strong"])
    )
    assert [n.id for n in report.after.neurons] == [1, 2, 5]
    assert report.after_manifest.excluded_neurons == [3, 4]
    report = compare_intervention(session, before, InterventionRules(side="right"))
    assert report.after_manifest.excluded_neurons == [2, 6]
    assert report.after.neurons == before.neurons
    assert report.after_manifest.filters["metadata_missing_policy"] == "exclude unknown side"
    hop_before = session.calculate(1, 5, PathMode.hops)
    report = compare_intervention(session, hop_before, InterventionRules(min_synapse_count=6))
    assert report.after.hop_count == 3 and report.before.hop_count == 2


@pytest.mark.parametrize(
    "rules,reason",
    [
        (InterventionRules(excluded_neurons=[1]), "endpoint_filtered"),
        (InterventionRules(side="left"), "endpoint_filtered"),
        (InterventionRules(min_synapse_count=91), "no_directed_path"),
        (InterventionRules(excluded_neurons=[2, 3]), "no_directed_path"),
    ],
)
def test_no_path_is_a_reproducible_comparison(session, rules, reason):
    report = compare_intervention(session, session.calculate(1, 5, PathMode.hops), rules)
    assert report.after is None and report.no_path_reason == reason
    assert report.summary()["after_cost"] is None
    assert report.summary()["removed_ids"] == []  # no invented replacement path
    assert InterventionReport.model_validate_json(report.model_dump_json()) == report


def test_unknown_filters_and_changed_sources_are_rejected(session):
    before = session.calculate(1, 5, PathMode.hops)
    for rules in [
        InterventionRules(excluded_neurons=[999]),
        InterventionRules(excluded_cell_types=["missing"]),
    ]:
        with pytest.raises(ValueError, match="absent"):
            compare_intervention(session, before, rules)
    session.edges_receipt = session.edges_receipt | dict(sha256="b" * 64)
    with pytest.raises(ValueError, match="source changed"):
        compare_intervention(session, before, InterventionRules())


def test_filtered_graph_retains_unknown_isolated_vertices(toy_tables):
    metadata, edges = toy_tables
    edges = pl.concat(
        [
            edges,
            pl.DataFrame(
                dict(
                    pre=[99], post=[100], count=[1], norm=[0.01], pre_count=[100], post_count=[100]
                )
            ),
        ]
    )
    graph = build_graph(metadata, edges)
    assert 99 in graph.ids and 100 in graph.ids
    kept = filtered_graph(graph, min_synapse_count=10, excluded_neurons=[2])
    assert 99 in kept.ids and 100 in kept.ids
    removed = filtered_graph(graph, min_synapse_count=10, excluded_neurons=[99, 100])
    assert 99 not in removed.ids
    assert graph.coverage == kept.coverage
    with pytest.raises(ValueError):
        filtered_graph(graph, min_synapse_count=1, excluded_neurons=[])


def test_cli_exports_offline_comparison_and_protects_existing_output(
    session, tmp_path, monkeypatch
):
    from typer.testing import CliRunner

    from banc_explorer.cli import app
    from banc_explorer.models import PathResult

    before = session.calculate(1, 5, PathMode.hops)
    source = tmp_path / "before.json"
    source.write_text(before.model_dump_json(), encoding="utf-8")
    monkeypatch.setattr("banc_explorer.cli.open_session", lambda settings: session)
    destination = tmp_path / "result"
    args = [
        "path",
        "intervene",
        "--baseline",
        str(source),
        "--output",
        str(destination),
        "--exclude-id",
        "2",
    ]
    result = CliRunner().invoke(app, args)
    assert result.exit_code == 0, result.output
    report = InterventionReport.model_validate_json((destination / "comparison.json").read_bytes())
    assert PathResult.model_validate_json((destination / "after.json").read_bytes()) == report.after
    assert CliRunner().invoke(app, args).exit_code == 1
