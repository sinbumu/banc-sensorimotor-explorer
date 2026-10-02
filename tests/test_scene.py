import json
from io import BytesIO
from urllib.error import HTTPError

import pytest
from typer.testing import CliRunner

from banc_explorer.cli import app
from banc_explorer.config import Settings
from banc_explorer.data import downloader
from banc_explorer.data.catalog import skeleton
from banc_explorer.graph.build import build_graph
from banc_explorer.graph.costs import PathMode
from banc_explorer.morphology.export import export_scene, load_scene, safe_file
from banc_explorer.morphology.models import SkeletonGeometry, SkeletonScene
from banc_explorer.morphology.preview import write_preview
from banc_explorer.morphology.provider import fetch_skeleton
from banc_explorer.provenance import write_result
from banc_explorer.workflow import Session


class Response(BytesIO):
    def __init__(self, payload):
        super().__init__(payload)
        self.headers = {"Content-Length": str(len(payload))}


@pytest.fixture
def scene_input(tmp_path, monkeypatch, toy_tables):
    receipt = {"url": "synthetic-fixture", "sha256": "a" * 64, "bytes": 1, "generation": None}
    session = Session(build_graph(*toy_tables), Settings(), receipt, receipt)
    path = tmp_path / "input.json"
    write_result(session.calculate(1, 5, PathMode.hops), path)
    requested = []

    def serve(url, **kwargs):
        requested.append(url)
        neuron_id = int(url.rsplit("/", 1)[-1].split("_")[0])
        # Distinct spatial locations test that neurons aren't individually centered.
        x = neuron_id * 10000
        return Response(f"9 2 {x + 1000} 2000 3000 50 0\n0 0 {x} 0 0 100 -1\n".encode())

    monkeypatch.setattr(downloader, "urlopen", serve)
    return path, tmp_path / "scene", tmp_path / "cache", requested


def test_fetch_export_roundtrip_topology_and_relative_positions(scene_input, monkeypatch):
    path, directory, cache, requested = scene_input
    scene = export_scene(path, directory, cache)
    assert requested == [skeleton(i).url for i in [1, 2, 5]]
    assert all("compiled_data/banc_888/banc_banc_space_swc" in url for url in requested)
    assert not list(directory.parent.glob(".scene-*"))
    monkeypatch.setattr(downloader, "urlopen", lambda *a, **k: pytest.fail("offline network"))
    parsed, geometries = load_scene(directory)
    assert parsed == scene
    assert (directory / "graph-path.json").read_bytes() == path.read_bytes()
    assert geometries[0].node_ids == ["9", "0"]
    assert geometries[0].parents == [1, None]
    assert geometries[0].radii == [0.005, 0.01]
    assert geometries[2].points[1][0] - geometries[0].points[1][0] == pytest.approx(4)
    for reference, geometry in zip(parsed.neurons, geometries, strict=True):
        raw, _ = fetch_skeleton(reference.id, cache, offline=True)
        for point, node in zip(geometry.points, raw.nodes, strict=True):
            assert parsed.coordinate_transform.inverse(point) == pytest.approx(node.xyz_nm)
    export_scene(path, directory.with_name("offline"), cache, offline=True)


def test_failed_fetch_does_not_publish_scene_or_substitute(scene_input, monkeypatch):
    path, directory, cache, _ = scene_input
    requested = []

    def unavailable(url, **kwargs):
        requested.append(url)
        raise HTTPError(url, 404, "not found", None, None)

    monkeypatch.setattr(downloader, "urlopen", unavailable)
    with pytest.raises(ValueError, match="No v888 full skeleton"):
        export_scene(path, directory, cache)
    assert len(requested) == 1
    assert not directory.exists()


def test_corruption_and_unsupported_contract(scene_input):
    path, directory, cache, _ = scene_input
    scene = export_scene(path, directory, cache)
    payload = scene.model_dump(mode="json")
    payload["schema_version"] = 99
    with pytest.raises(ValueError):
        SkeletonScene.model_validate(payload)
    payload["schema_version"] = 1
    payload["neurons"][0]["skeleton"] = "../outside.json"
    with pytest.raises(ValueError):
        SkeletonScene.model_validate(payload)
    with pytest.raises(ValueError, match="escapes"):
        safe_file(directory, "../outside.json")
    (directory / scene.neurons[0].skeleton).write_text("{}")
    with pytest.raises(ValueError, match="integrity"):
        load_scene(directory)


def test_reject_cyclic_geometry():
    with pytest.raises(ValueError, match="Cycle"):
        SkeletonGeometry(
            neuron_id=1,
            node_ids=["0", "1", "2"],
            labels=[0, 0, 0],
            points=[(0, 0, 0)] * 3,
            radii=[1] * 3,
            parents=[None, 2, 1],
        )


def test_scene_cli_and_safe_preview(scene_input):
    path, directory, cache, _ = scene_input
    config = path.parent / "config.toml"
    config.write_text(f"cache_dir = {json.dumps(cache.as_posix())}\n")
    runner = CliRunner()
    args = [
        "scene",
        "export",
        "--path",
        str(path),
        "--output",
        str(directory),
        "--config",
        str(config),
    ]
    result = runner.invoke(app, args)
    assert result.exit_code == 0, result.output
    assert runner.invoke(app, args).exit_code == 1
    result = runner.invoke(app, ["scene", "validate", "--scene", str(directory)])
    assert result.exit_code == 0, result.output
    result = runner.invoke(app, ["scene", "inspect", "--scene", str(directory)])
    assert result.exit_code == 0, result.output
    preview = (directory / "inspection.html").read_text(encoding="utf-8")
    assert "new ResizeObserver" in preview
    assert "__SCENE_DATA__" not in preview
    with pytest.raises(ValueError, match="already exists"):
        write_preview(directory, directory / "inspection.html")


def test_preview_escapes_metadata(scene_input):
    path, directory, cache, _ = scene_input
    original = json.loads(path.read_text())
    original["neurons"][0]["cell_type"] = "</script><script>alert(1)</script>"
    path.write_text(json.dumps(original))
    export_scene(path, directory, cache)
    write_preview(directory, directory / "inspection.html")
    text = (directory / "inspection.html").read_text(encoding="utf-8")
    assert "</script><script>alert(1)" not in text
    assert r"\u003c/script\u003e" in text


def test_cached_budget_enforced(scene_input):
    _, _, cache, _ = scene_input
    fetch_skeleton(1, cache)
    with pytest.raises(ValueError, match="byte budget"):
        fetch_skeleton(1, cache, offline=True, max_bytes=1)


def test_failed_final_validation_cleans_stage_without_publishing(scene_input, monkeypatch):
    path, directory, cache, _ = scene_input
    neighbor = directory.parent / "keep.txt"
    neighbor.write_text("unrelated")

    def reject(_directory):
        raise ValueError("simulated final validation failure")

    monkeypatch.setattr("banc_explorer.morphology.export.load_scene", reject)
    with pytest.raises(ValueError, match="simulated final"):
        export_scene(path, directory, cache)
    assert not directory.exists()
    assert not list(directory.parent.glob(".scene-*"))
    assert neighbor.read_text() == "unrelated"
