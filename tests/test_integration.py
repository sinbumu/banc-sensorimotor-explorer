"""Network-free prepare -> Feather -> normalization -> CLI report integration."""

import json
from io import BytesIO

import pyarrow as pa
import pytest
from pyarrow import feather
from typer.testing import CliRunner

from banc_explorer.cli import app
from banc_explorer.data import downloader


class Response(BytesIO):
    def __init__(self, data):
        super().__init__(data)
        self.headers = {"Content-Length": str(len(data))}


@pytest.mark.parametrize("version", ["v2", "v3"])
def test_prepare_validate_candidates(tmp_path, monkeypatch, version):
    tables = {
        "meta": pa.table(
            {
                "banc_888_id": ["9007199254740993", "9007199254740995"],
                "super_class": ["sensory", "motor"],
                "proofread": ["TRUE", "TRUE"],
            }
        ),
        "edges": pa.table(
            {
                "pre": ["9007199254740993"],
                "post": ["9007199254740995"],
                "count": [5],
                "pre_count": [5],
                "post_count": [10],
                "norm": [0.5],
            }
        ),
    }

    def serve(url, **kwargs):
        stream = BytesIO()
        feather.write_feather(tables["meta" if "_meta." in url else "edges"], stream)
        return Response(stream.getvalue())

    monkeypatch.chdir(tmp_path)
    (tmp_path / "configs").mkdir()
    config = tmp_path / "configs" / "test.toml"
    config.write_text(f'connectivity_version = "{version}"\n')
    monkeypatch.setattr(downloader, "urlopen", serve)
    runner = CliRunner()
    result = runner.invoke(app, ["data", "prepare", "--config", str(config)])
    assert result.exit_code == 0, result.output
    monkeypatch.setattr(
        downloader,
        "urlopen",
        lambda *a, **k: (_ for _ in ()).throw(
            AssertionError("offline validation attempted network")
        ),
    )
    result = runner.invoke(
        app, ["data", "validate", "--output", "report.json", "--config", str(config)]
    )
    assert result.exit_code == 0, result.output
    report = json.loads((tmp_path / "report.json").read_text())
    assert report["files"][0]["rows"] == 2
    assert report["files"][1]["edges_at_threshold"] == 1
    result = runner.invoke(app, ["candidates", "sensory"])
    assert result.exit_code == 0
    assert "9007199254740993" in result.output
    result = runner.invoke(
        app,
        [
            "path",
            "find",
            "--source-id",
            "9007199254740993",
            "--target-id",
            "9007199254740995",
            "--mode",
            "normalized",
            "--config",
            str(config),
            "--output",
            "path.json",
        ],
    )
    assert result.exit_code == 0, result.output
    path = json.loads((tmp_path / "path.json").read_text())
    assert path["manifest"]["connectivity_version"] == version
    assert f"_{version}.feather" in path["manifest"]["edgelist_source"]["url"]
    assert path["neurons"][0]["id"] == "9007199254740993"
    assert path["hop_count"] == 1
    result = runner.invoke(
        app,
        [
            "path",
            "find",
            "--source-id",
            "9007199254740995",
            "--target-id",
            "9007199254740993",
            "--config",
            str(config),
            "--output",
            "no-path.json",
        ],
    )
    assert result.exit_code == 1
    assert "No directed path" in result.output
    assert not (tmp_path / "no-path.json").exists()
