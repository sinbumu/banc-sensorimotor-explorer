"""Cross-language contract and viewer tests. Set GODOT_BIN to enable in CI/locally."""

import json
import os
import subprocess
from hashlib import sha256
from pathlib import Path

import polars as pl
import pytest

from banc_explorer.config import Settings
from banc_explorer.graph.build import build_graph
from banc_explorer.graph.costs import PathMode
from banc_explorer.morphology.export import export_scene
from banc_explorer.morphology.swc import parse_swc
from banc_explorer.provenance import write_result
from banc_explorer.workflow import Session

ROOT = Path(__file__).resolve().parents[1]
ENGINE = os.environ.get("GODOT_BIN")
pytestmark = pytest.mark.skipif(
    not ENGINE, reason="Set GODOT_BIN for Godot engine integration tests"
)


@pytest.fixture
def godot_bundle(tmp_path, monkeypatch, toy_tables):
    # Values exceed IEEE-754's exact integer range; IDs must survive as strings.
    base = 720575941350568496
    metadata, edges = toy_tables
    metadata = metadata.with_columns(pl.col("banc_888_id") + base)
    edges = edges.with_columns(pl.col("pre") + base, pl.col("post") + base)
    receipt = {"url": "synthetic-fixture", "sha256": "a" * 64, "bytes": 1, "generation": None}

    def synthetic_swc(neuron_id, *args, **kwargs):
        offset = (neuron_id - base) * 10000
        raw = f"9 2 {offset + 2000} 2000 3000 50 0\n0 0 {offset} 0 0 100 -1\n"
        return parse_swc(raw, source_units="nm"), receipt

    monkeypatch.setattr("banc_explorer.morphology.export.fetch_skeleton", synthetic_swc)
    session = Session(build_graph(metadata, edges), Settings(), receipt, receipt)

    def make(mode=PathMode.normalized, zero_hops=False):
        path = tmp_path / f"{mode}.json"
        directory = tmp_path / str(mode)
        target = base + 1 if zero_hops else base + 5
        write_result(session.calculate(base + 1, target, mode), path)
        export_scene(path, directory, tmp_path / "cache", offline=True)
        return directory

    return make


def run_engine(directory, script, *arguments):
    result = subprocess.run(
        [
            str(Path(ENGINE).resolve()),
            "--headless",
            "--path",
            str(ROOT / "godot"),
            "--script",
            f"res://tests/{script}.gd",
            "--log-file",
            str(directory.parent / f"{script}.log"),
            "--",
            *map(str, arguments),
        ],
        capture_output=True,
        text=True,
        timeout=60,
    )
    output = result.stdout + result.stderr
    assert result.returncode == 0 and "ERROR:" not in output, output
    assert f"GODOT_{'SMOKE' if script == 'smoke' else 'VALIDATE'}_OK" in output, output


def write_json(path, value):
    path.write_text(json.dumps(value), encoding="utf-8")


def refresh_hashes(directory):
    scene = json.loads((directory / "path.json").read_text())
    for ref in scene["neurons"]:
        geometry = directory / ref["skeleton"]
        if geometry.is_file():
            ref["geometry_sha256"] = sha256(geometry.read_bytes()).hexdigest()
    write_json(directory / "path.json", scene)
    manifest = json.loads((directory / "manifest.json").read_text())
    for name, key in [("path.json", "scene_sha256"), ("graph-path.json", "graph_path_sha256")]:
        manifest[key] = sha256((directory / name).read_bytes()).hexdigest()
    write_json(directory / "manifest.json", manifest)


@pytest.mark.parametrize("mode", [PathMode.hops, PathMode.normalized])
def test_godot_fixture_render_controls_and_large_ids(godot_bundle, mode):
    directory = godot_bundle(mode)
    run_engine(directory, "smoke", "--scene-dir", directory)


def test_godot_zero_hop_isolated_root(godot_bundle):
    directory = godot_bundle(zero_hops=True)
    scene = json.loads((directory / "path.json").read_text())
    reference = scene["neurons"][0]
    geometry_path = directory / reference["skeleton"]
    geometry = json.loads(geometry_path.read_text())
    geometry.update(node_ids=["0"], parents=[None], points=[[0, 0, 0]], labels=[0], radii=[0.01])
    reference["node_count"] = 1
    scene["bounds_min"] = scene["bounds_max"] = [0, 0, 0]
    write_json(geometry_path, geometry)
    write_json(directory / "path.json", scene)
    refresh_hashes(directory)
    run_engine(directory, "smoke", "--scene-dir", directory)


@pytest.mark.parametrize(
    "case,expected",
    [
        ("schema", "Unsupported schema_version"),
        ("checksum", "SHA-256 mismatch"),
        ("numeric_id", "Invalid directed path"),
        ("reversed_edge", "Invalid directed path"),
        ("wrong_cost", "Invalid directed path"),
        ("path_traversal", "Unsafe or inconsistent"),
        ("units", "Unsupported coordinate units"),
        ("missing_parent", "Invalid skeleton coordinates/topology"),
        ("cycle", "Invalid skeleton coordinates/topology"),
        ("out_of_bounds", "Invalid skeleton coordinates/topology"),
        ("missing_geometry", "Missing file"),
    ],
)
def test_godot_rejects_invalid_bundle(godot_bundle, case, expected):
    directory = godot_bundle()
    scene_path = directory / "path.json"
    scene = json.loads(scene_path.read_text())
    geometry_path = directory / scene["neurons"][0]["skeleton"]
    geometry = json.loads(geometry_path.read_text())
    if case == "schema":
        scene["schema_version"] = 99
    elif case == "checksum":
        geometry_path.write_text("{}")
        run_engine(directory, "validate", directory, expected)
        return
    elif case in {"numeric_id", "reversed_edge", "wrong_cost"}:
        graph = scene["path_result"]
        if case == "numeric_id":
            graph["neurons"][0]["id"] = int(graph["neurons"][0]["id"])
        elif case == "reversed_edge":
            edge = graph["edges"][0]
            edge["pre"], edge["post"] = edge["post"], edge["pre"]
        else:
            graph["edges"][0]["cost"] = 99
        write_json(directory / "graph-path.json", graph)
    elif case == "path_traversal":
        scene["neurons"][0]["skeleton"] = "../escape.json"
    elif case == "units":
        scene["coordinate_transform"]["source_units"] = "um"
    elif case == "missing_parent":
        geometry["parents"][0] = 20
    elif case == "cycle":
        # Preserve a root plus a disconnected cycle, so counting roots is insufficient.
        geometry.update(
            node_ids=["0", "1", "2"],
            parents=[None, 2, 1],
            points=[geometry["points"][0]] * 3,
            labels=[0, 0, 0],
            radii=[0.1, 0.1, 0.1],
        )
        scene["neurons"][0]["node_count"] = 3
    elif case == "out_of_bounds":
        geometry["points"][0][0] = 1e6
    elif case == "missing_geometry":
        geometry_path.unlink()
    write_json(scene_path, scene)
    if case != "missing_geometry":
        write_json(geometry_path, geometry)
    refresh_hashes(directory)
    run_engine(directory, "validate", directory, expected)
