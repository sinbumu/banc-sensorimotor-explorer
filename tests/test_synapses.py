"""Synthetic CAVE responses exercise the wire contract without credentials/network."""

import io
import json
import os
import runpy
import subprocess
from hashlib import sha256
from pathlib import Path
from urllib.error import HTTPError

import polars as pl
import pytest
from typer.testing import CliRunner

from banc_explorer.cli import app
from banc_explorer.config import Settings
from banc_explorer.em.export import point_from_evidence
from banc_explorer.graph.build import build_graph
from banc_explorer.graph.costs import PathMode
from banc_explorer.provenance import write_result
from banc_explorer.synapses.evidence import (
    CaveSynapseProvider,
    Evidence,
    export_evidence,
    load_evidence,
)
from banc_explorer.synapses.transport import BASE, CaveTransport, NoRedirect, local_token
from banc_explorer.workflow import Session


@pytest.fixture
def cave_wire(monkeypatch, tmp_path, toy_tables):
    base = 720575941350568496
    metadata, edges = toy_tables
    metadata = metadata.with_columns(pl.col("banc_888_id") + base)
    edges = edges.with_columns(pl.col("pre") + base, pl.col("post") + base)
    receipt = {"url": "synthetic-fixture", "sha256": "a" * 64, "bytes": 1}
    session = Session(build_graph(metadata, edges), Settings(), receipt, receipt)
    graph = session.calculate(base + 1, base + 5, PathMode.hops)
    write_result(graph, tmp_path / "graph.json")
    edge = graph.edges[0]
    rows = [
        dict(
            id=9007199254740993 + i,
            pre_pt_root_id=edge.pre,
            post_pt_root_id=edge.post,
            size=10,
            ctr_pt_position=[1024 + i, 1024, 720],
        )
        for i in range(edge.count)
    ]
    responses = {
        "": {
            "version": 888,
            "valid": True,
            "datastack": "brain_and_nerve_cord",
            "time_stamp": "2026-04-09T00:00:00",
        },
        "/tables": ["synapses_v2", "synapses_v3"],
        "/table/synapses_v3/metadata": {
            "table_name": "synapses_v3",
            "voxel_resolution_x": 16,
            "voxel_resolution_y": 16,
            "voxel_resolution_z": 45,
        },
        "/table/synapses_v3/query?return_pyarrow=false&split_positions=false": rows,
    }
    calls = []
    headers = {"Content-Type": "application/json", "dataframe_resolution": "[1, 1, 1]"}

    class Opener:
        def open(self, request, **kwargs):
            calls.append(request)
            suffix = request.full_url.removeprefix(BASE)
            data = responses[suffix]
            if request.data:
                data = data[: json.loads(request.data)["limit"]]
            body = json.dumps(data).encode()
            response = io.BytesIO(body)
            response.status = 200
            response.headers = headers | {"Content-Length": str(len(body))}
            return response

    monkeypatch.setattr("banc_explorer.synapses.transport.local_token", lambda: "synthetic-token")
    monkeypatch.setattr("banc_explorer.synapses.transport.build_opener", lambda *a: Opener())
    return graph, responses, headers, calls


def test_bounded_cave_export_cli_validate_exact_ids(tmp_path, cave_wire, monkeypatch):
    graph, responses, headers, calls = cave_wire
    output = tmp_path / "evidence"
    evidence = export_evidence(CaveSynapseProvider(), (tmp_path / "graph.json"), output)
    assert evidence.count_comparison == "matches"
    assert len(evidence.rows) == graph.edges[0].count
    assert evidence.native_resolution_nm == (16, 16, 45)
    assert evidence.rows[0].center_nm == (1024, 1024, 720)  # no second scaling
    assert len(calls) == 4 and all(
        r.get_header("Authorization") == "Bearer synthetic-token" for r in calls
    )
    query = json.loads(calls[-1].data)
    assert query["limit"] == 251
    assert query["filter_equal_dict"]["synapses_v3"] == {
        "pre_pt_root_id": graph.edges[0].pre,
        "post_pt_root_id": graph.edges[0].post,
    }
    assert query["filter_greater_equal_dict"] == {"synapses_v3": {"size": 10}}
    assert query["desired_resolution"] == [1, 1, 1]
    stored = json.loads((output / "evidence.json").read_bytes())
    assert stored["rows"][0]["id"] == "9007199254740993"
    assert stored["query"]["filter_equal_dict"]["synapses_v3"]["pre_pt_root_id"] == str(
        graph.edges[0].pre
    )
    assert "synthetic-token" not in (output / "evidence.json").read_text()
    monkeypatch.setattr(
        "banc_explorer.synapses.transport.local_token", lambda: pytest.fail("offline auth")
    )
    assert load_evidence(output) == evidence
    result = CliRunner().invoke(app, ["synapses", "validate", "--evidence", str(output)])
    assert result.exit_code == 0 and "matches" in result.stdout
    point = point_from_evidence(output, "9007199254740993")
    assert point.center_nm == (1024, 1024, 720)
    assert point.evidence_sha256 == sha256((output / "evidence.json").read_bytes()).hexdigest()
    with pytest.raises(ValueError, match="not present"):
        point_from_evidence(output, "1")
    with pytest.raises(ValueError, match="already exists"):
        export_evidence(None, (tmp_path / "graph.json"), output)


@pytest.mark.parametrize("case", ["capped", "empty", "differs", "warning", "v2"])
def test_response_limits_count_mismatch_and_versions(cave_wire, case):
    graph, responses, headers, calls = cave_wire
    limit = 250
    key = next(k for k in responses if "query?" in k)
    if case == "capped":
        limit = 2
    elif case == "empty":
        responses[key] = []
    elif case == "differs":
        responses[key] = responses[key][:1]
    elif case == "warning":
        headers["Warning"] = "Synthetic server limit notice"
    else:
        graph.manifest.connectivity_version = "v2"
        responses[key.replace("v3", "v2")] = responses.pop(key)
        md = responses.pop("/table/synapses_v3/metadata") | {"table_name": "synapses_v2"}
        responses["/table/synapses_v2/metadata"] = md
    result = CaveSynapseProvider().fetch(graph, "a" * 64, 0, limit)
    assert result.count_comparison == (
        "incomplete" if case in ("capped", "warning") else "matches" if case == "v2" else "differs"
    )
    if case == "capped":
        assert result.response_rows == 3 and len(result.rows) == 2 and result.limit_reached
    if case == "v2":
        assert result.table == "synapses_v2" and result.min_size == 5


@pytest.mark.parametrize(
    "case",
    [
        "version",
        "datastack",
        "expired",
        "missing_table",
        "table_name",
        "native_units",
        "missing_units",
        "wrong_units",
        "wrong_pair",
        "size",
        "duplicate",
        "float_id",
        "missing_column",
        "nonfinite",
        "too_many",
    ],
)
def test_cave_refuses_unverified_provenance_and_broken_filters(cave_wire, case):
    graph, responses, headers, calls = cave_wire
    table = responses["/table/synapses_v3/metadata"]
    key = next(k for k in responses if "query?" in k)
    row = responses[key][0]
    if case == "version":
        responses[""]["version"] = 889
    elif case == "datastack":
        responses[""]["datastack"] = "other"
    elif case == "expired":
        responses[""]["valid"] = False
    elif case == "missing_table":
        responses["/tables"] = ["synapses_v2"]
    elif case == "table_name":
        table["table_name"] = "synapses_v2"
    elif case == "native_units":
        table["voxel_resolution_x"] = None
    elif case == "missing_units":
        headers.pop("dataframe_resolution")
    elif case == "wrong_units":
        headers["dataframe_resolution"] = "[16, 16, 45]"
    elif case == "wrong_pair":
        row["pre_pt_root_id"] = graph.edges[0].post
    elif case == "size":
        row["size"] = 1
    elif case == "duplicate":
        responses[key][1] = row.copy()
    elif case == "float_id":
        row["id"] = float(row["id"])
    elif case == "missing_column":
        row.pop("ctr_pt_position")
    elif case == "nonfinite":
        row["ctr_pt_position"][0] = float("nan")
    elif case == "too_many":
        transport = CaveTransport()
        original = transport.read

        def read(suffix, *args, **kwargs):
            data, resolution, warning, receipt = original(suffix, *args, **kwargs)
            if "query?" in suffix:
                data = data * 500
            return data, resolution, warning, receipt

        transport.read = read
        with pytest.raises(ValueError, match="row limit"):
            CaveSynapseProvider(transport).fetch(graph, "a" * 64, 0, 250)
        return
    with pytest.raises(ValueError):
        CaveSynapseProvider().fetch(graph, "a" * 64, 0, 250)


@pytest.mark.parametrize("case", ["path_hash", "version", "row_pair", "query", "count", "source"])
def test_offline_subset_rejects_tampering(tmp_path, cave_wire, case):
    output = tmp_path / "evidence"
    export_evidence(CaveSynapseProvider(), (tmp_path / "graph.json"), output)
    path = output / "evidence.json"
    data = json.loads(path.read_bytes())
    if case == "path_hash":
        data["path_sha256"] = "0" * 64
    elif case == "version":
        data["connectivity_version"] = "v2"
    elif case == "row_pair":
        data["rows"][0]["post_root_id"] = data["pre"]
    elif case == "query":
        data["query"]["limit"] = 99999
    elif case == "count":
        data["count_comparison"] = "differs"
    else:
        data["receipts"][-1]["url"] = "https://wrong.invalid/query"
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError):
        load_evidence(output)


def test_credentials_standard_files_and_redacted_failures(tmp_path, monkeypatch):
    monkeypatch.delenv("BANC_CAVE_TOKEN", raising=False)
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    with pytest.raises(ValueError, match="missing"):
        local_token()
    directory = tmp_path / ".cloudvolume" / "secrets"
    directory.mkdir(parents=True)
    (directory / "cave-secret.json").write_text('{"token":"fixture-global"}')
    assert local_token() == "fixture-global"
    (directory / "cave.fanc-fly.com-cave-secret.json").write_text(
        '{"brain_and_nerve_cord":"fixture-host"}'
    )
    assert local_token() == "fixture-host"
    monkeypatch.setenv("BANC_CAVE_TOKEN", "fixture-environment")
    assert local_token() == "fixture-environment"
    monkeypatch.setenv("BANC_CAVE_TOKEN", "private\ninvalid")
    with pytest.raises(ValueError) as exc:
        local_token()
    assert "private" not in str(exc.value)


def test_interactive_setup_hides_token_and_preserves_existing_file(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setattr("getpass.getpass", lambda prompt: "fixture-only-local-secret")
    script = Path(__file__).resolve().parents[1] / "scripts" / "configure_cave.py"
    setup = runpy.run_path(str(script))["main"]
    assert setup() == 0
    target = tmp_path / ".cloudvolume" / "secrets" / "cave.fanc-fly.com-cave-secret.json"
    before = target.read_bytes()
    assert json.loads(before) == {"token": "fixture-only-local-secret"}
    monkeypatch.setattr("getpass.getpass", lambda prompt: pytest.fail("existing credential prompt"))
    assert setup() == 1 and target.read_bytes() == before
    assert "fixture-only-local-secret" not in capsys.readouterr().out


@pytest.mark.parametrize(
    "case",
    [
        "oversize",
        "stream_oversize",
        "redirect",
        "denied",
        "html",
        "compression",
        "invalid_json",
        "invalid_length",
        "truncated",
        "budget",
    ],
)
def test_transport_guards_and_no_auth_error_leaks(monkeypatch, case):
    secret = "synthetic-secret-value"
    monkeypatch.setenv("BANC_CAVE_TOKEN", secret)

    class Opener:
        def open(self, req, **kwargs):
            if case in ("redirect", "denied"):
                raise HTTPError(
                    req.full_url + secret,
                    302 if case == "redirect" else 403,
                    secret,
                    {},
                    io.BytesIO(secret.encode()),
                )

            class Response(io.BytesIO):
                status = 200
                headers = {"Content-Type": "application/json"}

                def read(self, n):
                    if case == "truncated":
                        from http.client import IncompleteRead

                        raise IncompleteRead(secret.encode(), 100)
                    if case in ("oversize", "html", "compression"):
                        pytest.fail("read rejected body")
                    return super().read(n)

            response = Response(b"x" * (102 if case == "stream_oversize" else 1))
            if case == "oversize":
                response.headers["Content-Length"] = "101"
            if case == "invalid_length":
                response.headers["Content-Length"] = secret
            if case == "html":
                response.headers["Content-Type"] = "text/html"
            if case == "compression":
                response.headers["Content-Encoding"] = "gzip"
            return response

    monkeypatch.setattr("banc_explorer.synapses.transport.build_opener", lambda *a: Opener())
    transport = CaveTransport()
    if case == "budget":
        transport.downloaded = 2_300_000
    with pytest.raises(ValueError) as exc:
        transport.read("", limit=100)
    assert secret not in str(exc.value)
    assert NoRedirect().redirect_request(None, None, 302, "", {}, "https://elsewhere") is None


def test_invalid_query_and_output_precede_network(cave_wire, tmp_path, monkeypatch):
    graph = cave_wire[0]
    provider = CaveSynapseProvider()
    for edge_index, limit in [(-1, 2), (999, 2), (0, 0), (0, 1001)]:
        with pytest.raises(ValueError):
            provider.fetch(graph, "a" * 64, edge_index, limit)
    assert cave_wire[3] == []
    monkeypatch.setattr("banc_explorer.synapses.transport.local_token", lambda: pytest.fail("auth"))
    result = CliRunner().invoke(
        app,
        [
            "synapses",
            "fetch",
            "--path",
            str(tmp_path / "graph.json"),
            "--output",
            str(tmp_path / "new"),
            "--edge-index",
            "999",
        ],
    )
    assert result.exit_code == 1 and "Edge index" in result.stdout


def test_evidence_contract_roundtrip(cave_wire):
    result = CaveSynapseProvider().fetch(cave_wire[0], "a" * 64, 0, 10)
    assert Evidence.model_validate_json(result.model_dump_json()) == result


def test_selected_edge_through_em_export_and_cli(tmp_path, cave_wire, monkeypatch):
    pytest.importorskip("PIL")
    import numpy as np

    from banc_explorer.em.export import load_roi
    from banc_explorer.em.provider import EmVolume

    evidence_dir = tmp_path / "subset"
    roi_dir = tmp_path / "roi"
    cli = CliRunner()
    fetched = cli.invoke(
        app,
        [
            "synapses",
            "fetch",
            "--path",
            str(tmp_path / "graph.json"),
            "--output",
            str(evidence_dir),
        ],
    )
    assert fetched.exit_code == 0, fetched.stdout

    class Provider:
        def __init__(self, *args):
            pass

        def fetch_roi(self, request):
            assert request.center_nm == (1024, 1024, 720)
            assert request.size_voxels == (10, 10, 8)
            return EmVolume(
                np.arange(800, dtype=np.uint8).reshape(8, 10, 10),
                (123, 123, 12),
                (8, 8, 45),
                "8_8_45",
                {"synthetic": True},
                [{"synthetic": True}],
                0,
            )

    monkeypatch.setattr("banc_explorer.em.provider.PublicEmProvider", Provider)
    monkeypatch.setattr(
        "banc_explorer.synapses.transport.local_token", lambda: pytest.fail("offline credentials")
    )
    inspected = cli.invoke(
        app,
        [
            "em",
            "synapse",
            "--evidence",
            str(evidence_dir),
            "--synapse-id",
            "9007199254740993",
            "--output",
            str(roi_dir),
            "--size-xy",
            "10",
            "--depth",
            "8",
            "--offline",
        ],
    )
    assert inspected.exit_code == 0, inspected.stdout
    manifest = load_roi(roi_dir)
    assert manifest.schema_version == 2 and manifest.point.pre == cave_wire[0].edges[0].pre
    if os.environ.get("GODOT_BIN"):
        root = Path(__file__).resolve().parents[1]
        result = subprocess.run(
            [
                os.environ["GODOT_BIN"],
                "--headless",
                "--path",
                str(root / "godot"),
                "--script",
                "res://tests/synapse_em_smoke.gd",
                "--log-file",
                str(tmp_path / "godot.log"),
                "--",
                str(roi_dir),
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        output = result.stdout + result.stderr
        assert (
            result.returncode == 0 and "ERROR:" not in output and "GODOT_SYNAPSE_EM_OK" in output
        ), output
