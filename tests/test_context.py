import gzip
import json
import struct
from io import BytesIO

import pytest

from banc_explorer.data import downloader
from banc_explorer.morphology.context import (
    REGIONS,
    context_asset,
    fetch_context,
    parse_legacy_mesh,
    read_asset,
)


def triangle():
    return struct.pack("<I9f3I", 3, 1000, 2000, 3000, 4000, 2000, 3000, 1000, 5000, 3000, 0, 1, 2)


def test_legacy_mesh_layout_nm_and_indices():
    points, faces = parse_legacy_mesh(triangle())
    assert points == [[1000, 2000, 3000], [4000, 2000, 3000], [1000, 5000, 3000]]
    assert faces == [[0, 1, 2]]


@pytest.mark.parametrize(
    "payload",
    [
        b"",
        triangle()[:-1],
        triangle() + b"0",
        struct.pack("<I", 2**32 - 1),
        triangle()[:-4] + struct.pack("<I", 3),
        triangle()[:-4] + struct.pack("<I", 1),
        triangle()[:4] + struct.pack("<f", float("nan")) + triangle()[8:],
    ],
)
def test_legacy_rejects_malformed_geometry(payload):
    with pytest.raises(ValueError):
        parse_legacy_mesh(payload)


class Response(BytesIO):
    def __init__(self, data):
        super().__init__(data)
        self.headers = {"Content-Length": str(len(data)), "x-goog-generation": "123"}


@pytest.fixture
def catalog(monkeypatch):
    payloads = {
        "info": json.dumps({"mesh": "meshes", "segment_properties": "segment_properties"}).encode(),
        "segment_properties/info": json.dumps(
            {
                "inline": {
                    "ids": list(REGIONS),
                    "properties": [{"type": "label", "values": list(REGIONS.values())}],
                }
            }
        ).encode(),
    }
    for id in REGIONS:
        payloads[f"meshes/{id}:0"] = json.dumps({"fragments": [f"{id}:0:1"]}).encode()
        payloads[f"meshes/{id}:0:1"] = gzip.compress(triangle())
    calls = []

    def serve(url, **kwargs):
        relative = url.split("/region_outlines/")[1]
        calls.append(relative)
        return Response(payloads[relative])

    monkeypatch.setattr(downloader, "urlopen", serve)
    return payloads, calls


def test_bounded_catalog_cache_gzip_labels_and_windows_paths(tmp_path, catalog, monkeypatch):
    outlines = fetch_context(tmp_path)
    assert len(catalog[1]) == 6
    assert [o["label"] for o in outlines] == list(REGIONS.values())
    assert outlines[0]["points_nm"][0] == [1000, 2000, 3000]
    assert all(
        r["materialization"] is None and r["generation"] == "123"
        for o in outlines
        for r in o["receipts"]
    )
    assert ":" not in context_asset("meshes/3:0:1").local_path(tmp_path).name
    monkeypatch.setattr(downloader, "urlopen", lambda *a, **k: pytest.fail("offline network"))
    assert fetch_context(tmp_path, offline=True) == outlines
    context_asset("meshes/3:0:1").local_path(tmp_path).write_bytes(b"corruption")
    with pytest.raises(ValueError, match="integrity"):
        fetch_context(tmp_path, offline=True)


def test_unexpected_fragment_never_fetched(tmp_path, catalog):
    catalog[0]["meshes/3:0"] = b'{"fragments": ["https://other-host/huge"]}'
    with pytest.raises(ValueError, match="Unsupported outline fragments"):
        fetch_context(tmp_path)
    assert catalog[1] == ["info", "segment_properties/info", "meshes/3:0"]


def test_gzip_expansion_is_bounded(tmp_path, catalog, monkeypatch):
    monkeypatch.setattr("banc_explorer.morphology.context.MAX_BYTES", 100)
    catalog[0]["info"] = gzip.compress(b"a" * 101)
    with pytest.raises(ValueError, match="Decompressed outline"):
        read_asset("info", tmp_path, offline=False, refresh=False)


def test_context_offline_missing_and_refresh(tmp_path):
    with pytest.raises(ValueError, match="context-fetch"):
        fetch_context(tmp_path, offline=True)
    with pytest.raises(ValueError, match="Cannot refresh"):
        fetch_context(tmp_path, offline=True, refresh=True)


@pytest.mark.parametrize(
    "name,payload",
    [
        ("info", b"[]"),
        ("segment_properties/info", b"null"),
        ("segment_properties/info", b'{"inline":{"ids":[[]],"properties":[]}}'),
    ],
)
def test_changed_catalog_schema_is_actionable(tmp_path, catalog, name, payload):
    catalog[0][name] = payload
    with pytest.raises(ValueError, match="BANC outline"):
        fetch_context(tmp_path)
