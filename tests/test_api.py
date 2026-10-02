"""Local API contracts: no public data, network downloads or CAVE credentials."""

import os
import socket
import subprocess
import time
from pathlib import Path
from threading import Event, Thread

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient

from banc_explorer.api.app import create_app
from banc_explorer.api.service import ExplorerService
from banc_explorer.config import Settings
from banc_explorer.graph.build import build_graph
from banc_explorer.morphology.export import load_scene
from banc_explorer.morphology.swc import parse_swc
from banc_explorer.workflow import Session


@pytest.fixture
def local_service(tmp_path, monkeypatch, toy_tables):
    metadata, edges = toy_tables
    receipt = {"url": "synthetic-fixture", "sha256": "a" * 64, "bytes": 1, "generation": None}
    builds = []
    service = ExplorerService(Settings(), tmp_path / "jobs", offline=True)

    def start():
        service.metadata = metadata
        service.metadata_receipt = receipt

    def session(settings):
        builds.append(settings.min_synapse_count)
        return Session(
            build_graph(metadata, edges, min_synapse_count=settings.min_synapse_count),
            settings,
            receipt,
            receipt,
        )

    def skeleton(neuron_id, *args, **kwargs):
        assert kwargs["offline"]
        x = neuron_id * 10000
        return parse_swc(
            f"0 0 {x} 0 0 100 -1\n9 2 {x + 1000} 2000 3000 50 0\n", source_units="nm"
        ), receipt

    monkeypatch.setattr(service, "start", start)
    monkeypatch.setattr("banc_explorer.api.service.open_session", session)
    monkeypatch.setattr("banc_explorer.morphology.export.fetch_skeleton", skeleton)
    return service, builds


@pytest.fixture
def client(local_service):
    service, _ = local_service
    with TestClient(
        create_app(Settings(), service.output, service=service), base_url="http://127.0.0.1"
    ) as connection:
        yield connection


@pytest.fixture
def synthetic_em(monkeypatch):
    pytest.importorskip("PIL")
    import numpy as np

    from banc_explorer.em.provider import EmVolume

    receipt = {"url": "synthetic-fixture", "sha256": "a" * 64, "bytes": 1, "generation": None}

    def skeleton(neuron_id, *args, **kwargs):
        assert kwargs["offline"]
        return parse_swc(
            f"0 0 {neuron_id * 10000} 20000 30000 50 -1\n9 2 {neuron_id * 10000 + 1000} 22000 33000 50 0\n",
            source_units="nm",
        ), receipt

    class Provider:
        def __init__(self, transport):
            assert transport.offline

        def fetch_roi(self, request):
            resolution = (8, 8, 45)
            origin = tuple(
                int(c // r) - s // 2
                for c, r, s in zip(request.center_nm, resolution, request.size_voxels, strict=True)
            )
            data = np.zeros(request.size_voxels[::-1], dtype=np.uint8)
            for i in range(data.shape[0]):
                data[i] = i * 3
            return EmVolume(
                data, origin, resolution, "8_8_45", {}, [dict(url="synthetic", bytes=1)], 0
            )

    monkeypatch.setattr("banc_explorer.em.service.fetch_skeleton", skeleton)
    monkeypatch.setattr("banc_explorer.em.service.PublicEmProvider", Provider)


def request_body(**overrides):
    return {
        "source_id": "1",
        "target_id": "5",
        "modes": ["hops", "normalized"],
        "allow_downloads": False,
        **overrides,
    }


def complete_job(client, **overrides):
    response = client.post("/paths", json=request_body(**overrides))
    assert response.status_code == 202, response.text
    job_id = response.json()["id"]
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        job = client.get(f"/paths/{job_id}").json()
        if job["status"] in {"complete", "error"}:
            return job
        time.sleep(0.005)
    pytest.fail("API path job did not finish")


def test_health_facets_search_and_pagination(client):
    assert client.get("/health").json()["materialization"] == 888
    assert client.get("/health").json()["offline"] is True
    assert client.get("/metadata/facets").json() == {"sensory": ["leg"], "motor": ["leg"]}
    assert (
        client.get("/neurons/search", params={"kind": "motor", "q": "5"}).json()["neurons"][0]["id"]
        == "5"
    )
    result = client.get(
        "/neurons/search", params={"kind": "motor", "body_part": "leg", "limit": 1, "offset": 1}
    ).json()
    assert result["total"] == 2 and result["neurons"][0]["id"] == "6"
    assert client.get("/neurons/search", params={"kind": "sensory", "q": "["}).json()["total"] == 0
    assert client.get("/neurons/search", params={"kind": "invalid"}).status_code == 422
    assert client.get("/neurons/search", params={"kind": "motor", "limit": 101}).status_code == 422


def test_jobs_export_both_modes_and_reuse_one_graph(client, local_service):
    job = complete_job(client)
    assert job["status"] == "complete", job
    assert job["results"]["hops"]["neuron_ids"] == ["1", "2", "5"]
    assert job["results"]["normalized"]["neuron_ids"] == ["1", "3", "4", "5"]
    for mode, result in job["results"].items():
        scene, _ = load_scene(Path(result["scene_directory"]))
        assert scene.path_result.manifest.path_mode == mode
        assert scene.path_result.manifest.materialization == 888
    assert complete_job(client)["status"] == "complete"
    assert local_service[1] == [5]
    assert complete_job(client, min_synapse_count=10)["status"] == "complete"
    assert local_service[1] == [5, 10]


def test_expected_errors_do_not_break_next_job(client):
    assert complete_job(client, target_id="6")["error_code"] == "no_path"
    assert complete_job(client)["status"] == "complete"
    assert client.get("/paths/nonexistent").status_code == 404
    for changes in [
        {"source_id": "5"},
        {"target_id": "7"},
        {"source_id": 1.5},
        {"modes": ["hops", "hops"]},
        {"min_synapse_count": 0},
        {"allow_downloads": True},
        {"output": "../escape"},
    ]:
        assert client.post("/paths", json=request_body(**changes)).status_code == 422


def test_busy_job_is_rejected_without_queuing(client, local_service, monkeypatch):
    service = local_service[0]
    entered, release = Event(), Event()
    real_run = service._run

    def slow_run(*args):
        entered.set()
        assert release.wait(5)
        real_run(*args)

    monkeypatch.setattr(service, "_run", slow_run)
    try:
        assert client.post("/paths", json=request_body()).status_code == 202
        assert entered.wait(2)
        assert client.post("/paths", json=request_body()).status_code == 409
    finally:
        release.set()


def test_failed_morphology_does_not_publish_scene(client, local_service, monkeypatch):
    def missing(*args, **kwargs):
        raise ValueError("Missing cached SWC; fetch selected skeletons first.")

    monkeypatch.setattr("banc_explorer.morphology.export.fetch_skeleton", missing)
    job = complete_job(client)
    assert job["status"] == "error" and "Missing cached SWC" in job["message"]
    assert job["results"] == {}
    assert not list(local_service[0].output.glob("*/hops/manifest.json"))


def test_loopback_host_origin_and_body_guards(client):
    assert client.get("/health", headers={"Host": "external.invalid"}).status_code == 400
    assert (
        client.post(
            "/paths", json=request_body(), headers={"Origin": "https://external.invalid"}
        ).status_code
        == 403
    )
    assert (
        client.post("/paths", content="{}", headers={"Content-Type": "text/plain"}).status_code
        == 415
    )
    assert (
        client.post(
            "/paths", content=" " * 5000, headers={"Content-Type": "application/json"}
        ).status_code
        == 413
    )


def test_startup_requires_cached_metadata(tmp_path):
    service = ExplorerService(Settings(cache_dir=tmp_path / "empty"), tmp_path / "output")
    try:
        with pytest.raises(ValueError, match="Missing cache"):
            service.start()
        assert not service.output.exists()
    finally:
        service.close()


@pytest.mark.skipif(
    not os.environ.get("GODOT_BIN"), reason="Set GODOT_BIN for HTTP/Godot integration"
)
@pytest.mark.parametrize("feature", ["base", "em", "intervention"])
def test_godot_search_compute_and_scene_switch_over_http(local_service, request, feature):
    import uvicorn

    if feature == "em":
        request.getfixturevalue("synthetic_em")

    service, builds = local_service
    app = create_app(Settings(), service.output, service=service)
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    port = listener.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, access_log=False))
    thread = Thread(target=lambda: server.run(sockets=[listener]), daemon=True)
    thread.start()
    try:
        deadline = time.monotonic() + 5
        while not server.started and time.monotonic() < deadline:
            time.sleep(0.01)
        assert server.started
        root = Path(__file__).resolve().parents[1]
        result = subprocess.run(
            [
                os.environ["GODOT_BIN"],
                "--headless",
                "--path",
                str(root / "godot"),
                "--script",
                "res://tests/explorer_smoke.gd",
                "--log-file",
                str(service.output.parent / "explorer.log"),
                "--",
                "--api-url",
                f"http://127.0.0.1:{port}",
                "--source-id",
                "1",
                "--target-id",
                "5",
                *(["--inspect-em"] if feature == "em" else []),
                *(["--intervene"] if feature == "intervention" else []),
            ],
            capture_output=True,
            text=True,
            timeout=90,
        )
        output = result.stdout + result.stderr
        assert result.returncode == 0 and "ERROR:" not in output, output
        assert "GODOT_EXPLORER_OK" in output, output
        assert builds == [5]
    finally:
        server.should_exit = True
        thread.join(timeout=10)
        listener.close()
    assert not thread.is_alive()


def test_em_endpoint_resolves_verified_swc_and_recovers(client, synthetic_em):
    from banc_explorer.em.export import load_roi

    body = dict(neuron_id="1", swc_node_id="9", swc_sha256="a" * 64, size_voxels=[32, 32, 8])

    def run(values):
        response = client.post("/em", json=values)
        assert response.status_code == 202, response.text
        id = response.json()["id"]
        for _ in range(200):
            result = client.get(f"/em/{id}").json()
            if result["status"] in {"complete", "error"}:
                return result
            time.sleep(0.01)
        pytest.fail("EM job timeout")

    completed = run(body)
    assert completed["status"] == "complete", completed
    manifest = load_roi(Path(completed["results"]["roi_directory"]))
    assert manifest.point.center_nm == (11000, 22000, 33000)
    assert run(body | dict(swc_sha256="b" * 64))["status"] == "error"
    assert run(body | dict(swc_node_id="999"))["status"] == "error"
    assert run(body)["status"] == "complete"
    for change in [
        dict(allow_downloads=True),
        dict(size_voxels=[257, 256, 32]),
        dict(mip=9),
        dict(swc_node_id="../outside"),
    ]:
        assert client.post("/em", json=body | change).status_code == 422


def intervention_job(client, baseline, **changes):
    response = client.post(
        "/interventions/path",
        json=dict(baseline_job_id=baseline["id"], mode="hops", excluded_neurons=["2"], **changes),
    )
    assert response.status_code == 202, response.text
    for _ in range(500):
        job = client.get("/interventions/" + response.json()["id"]).json()
        if job["status"] in {"complete", "error"}:
            return job
        time.sleep(0.01)
    pytest.fail("Intervention job timeout")


def test_intervention_api_comparison_and_no_path_recovery(client):
    from banc_explorer.graph.interventions import InterventionReport

    baseline = complete_job(client)
    after = intervention_job(client, baseline)
    assert after["status"] == "complete", after
    report = InterventionReport.model_validate_json(
        Path(after["results"]["report_file"]).read_bytes()
    )
    assert report.before.hop_count == 2 and report.after.hop_count == 3
    assert (
        load_scene(Path(after["results"]["after_scene_directory"]))[0].path_result == report.after
    )
    unreachable = intervention_job(client, baseline, min_synapse_count=100)
    assert unreachable["status"] == "complete" and unreachable["results"]["reachable"] is False
    assert unreachable["results"]["after_scene_directory"] is None
    assert complete_job(client)["results"]["hops"]["neuron_ids"] == ["1", "2", "5"]
    assert (
        client.post(
            "/interventions/path", json=dict(baseline_job_id="0" * 32, mode="hops")
        ).status_code
        == 422
    )


def test_intervention_keeps_graph_report_when_after_swc_missing(client, monkeypatch):
    baseline = complete_job(client)

    def unavailable(*args, **kwargs):
        raise ValueError("Missing SWC cache")

    monkeypatch.setattr("banc_explorer.api.service.export_scene", unavailable)
    job = intervention_job(client, baseline)
    assert job["status"] == "complete" and job["results"]["reachable"] is True
    assert job["results"]["after_scene_directory"] is None
    assert "Missing SWC" in job["results"]["after_scene_error"]
    assert Path(job["results"]["report_file"]).exists()


def test_optional_context_job_and_missing_cache_recovery(client, synthetic_context, monkeypatch):
    job = complete_job(client, include_context=True)
    assert job["status"] == "complete", job
    for result in job["results"].values():
        scene, _ = load_scene(Path(result["scene_directory"]))
        assert scene.schema_version == 2 and len(scene.context) == 2

    def missing(*args, **kwargs):
        assert kwargs["offline"]
        raise ValueError("Missing outline cache. Run morphology context-fetch.")

    monkeypatch.setattr("banc_explorer.morphology.export.fetch_context", missing)
    assert complete_job(client, include_context=True)["error_code"] == "data_error"
    assert complete_job(client)["status"] == "complete"
