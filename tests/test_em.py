"""No public network: asymmetric volumes, range guards and portable image contracts."""

import gzip
import io
import json
import os
import struct
import subprocess
from hashlib import sha256
from pathlib import Path

import numpy as np
import pytest

pytest.importorskip("PIL")
from PIL import Image

from banc_explorer.em.export import MorphologyPoint, SynapsePoint, export_roi, load_roi
from banc_explorer.em.provider import (
    PublicEmProvider,
    RoiRequest,
    decode_jpeg,
    decode_minishard,
    morton,
)
from banc_explorer.em.transport import BASE, RangeCache
from banc_explorer.models import SourceFile


def jpeg(value):
    stream = io.BytesIO()
    Image.fromarray(value).save(stream, format="JPEG", quality=100)
    return stream.getvalue()


def synthetic_source():
    scale = dict(
        key="8_8_45",
        resolution=[8, 8, 45],
        size=[256, 256, 32],
        voxel_offset=[0, 0, 0],
        chunk_sizes=[[128, 128, 16]],
        encoding="jpeg",
        sharding={
            "@type": "neuroglancer_uint64_sharded_v1",
            "hash": "identity",
            "preshift_bits": 11,
            "minishard_bits": 2,
            "shard_bits": 17,
            "minishard_index_encoding": "gzip",
            "data_encoding": "raw",
        },
    )
    # These 2x2x2 Morton IDs can be written without calling the production encoder.
    chunks = []
    for id in range(8):
        x, y, z = id & 1, (id >> 1) & 1, (id >> 2) & 1
        pixels = np.zeros((16, 128, 128), dtype=np.uint8)
        for k in range(16):
            pixels[k] = x * 70 + y * 30 + (z * 16 + k) * 3
        chunks.append(jpeg(pixels.reshape(2048, 128)))
    data = b"".join(chunks)
    index = gzip.compress(
        np.array([[0] + [1] * 7, [0] * 8, [len(c) for c in chunks]], dtype="<u8").tobytes()
    )
    header = struct.pack("<QQ", len(data), len(data) + len(index)) + bytes(48)
    return {
        "info": json.dumps(
            dict(type="image", data_type="uint8", num_channels=1, scales=[scale])
        ).encode(),
        "8_8_45/00000.shard": header + data + index,
    }


class Response(io.BytesIO):
    def __init__(self, data, status=200, headers=None):
        super().__init__(data)
        self.status = status
        self.headers = {
            "Content-Length": str(len(data)),
            "ETag": '"fixture"',
            "x-goog-generation": "123",
            **(headers or {}),
        }


@pytest.fixture
def em_source(monkeypatch):
    objects = synthetic_source()
    calls = []

    def serve(request, **kwargs):
        calls.append(request)
        data = objects[request.full_url.removeprefix(BASE + "/")]
        if request.has_header("Range"):
            a, b = map(int, request.get_header("Range")[6:].split("-"))
            return Response(data[a : b + 1], 206, {"Content-Range": f"bytes {a}-{b}/{len(data)}"})
        return Response(data)

    monkeypatch.setattr("banc_explorer.em.transport.urlopen", serve)
    return objects, calls


def point():
    return MorphologyPoint(
        neuron_id=720575941350568496,
        swc_node_id="824",
        center_nm=(1024, 1024, 720),
        skeleton_source=SourceFile(url="synthetic", sha256="a" * 64, bytes=1),
    )


def synapse_point():
    from banc_explorer.synapses.evidence import query_suffix
    from banc_explorer.synapses.transport import BASE as CAVE_BASE

    return SynapsePoint(
        connectivity_version="v3",
        table="synapses_v3",
        synapse_id="9007199254740993",
        pre="720575941350568496",
        post="720575941557376164",
        center_nm=(1024, 1024, 720),
        evidence_sha256="a" * 64,
        path_sha256="b" * 64,
        query_source=SourceFile(
            url=CAVE_BASE + query_suffix("synapses_v3"), sha256="c" * 64, bytes=1
        ),
    )


def test_synapse_roi_roundtrip_schema_and_provenance(tmp_path, em_source):
    directory = tmp_path / "synapse-roi"
    exported = export_roi(
        PublicEmProvider(RangeCache(tmp_path / "cache")),
        synapse_point(),
        directory,
        size_voxels=(10, 12, 8),
    )
    assert exported.schema_version == 2 and load_roi(directory) == exported
    assert exported.point.synapse_id == 9007199254740993
    data = exported.model_dump(mode="json")
    data["schema_version"] = 1
    from banc_explorer.em.export import RoiManifest

    with pytest.raises(ValueError, match="schema/interpretation"):
        RoiManifest.model_validate(data)


def test_morton_asymmetric_grid_and_index_deltas():
    assert morton((0, 0, 0), (8, 4, 2)) == 0
    assert morton((4, 2, 1), (8, 4, 2)) == 52  # x2 -> bit5, y1 -> bit4, z0 -> bit2
    assert morton((7, 3, 1), (8, 4, 2)) == 63
    with pytest.raises(ValueError):
        morton((8, 0, 0), (8, 4, 2))
    encoded = gzip.compress(np.array([[7, 5], [9, 3], [11, 13]], dtype="<u8").tobytes())
    assert decode_minishard(encoded, 64) == {7: (73, 84), 12: (87, 100)}


def test_cross_chunk_roi_axes_crop_and_offline_cache(tmp_path, em_source, monkeypatch):
    request = RoiRequest(center_nm=point().center_nm, size_voxels=(10, 12, 8))
    transport = RangeCache(tmp_path)
    volume = PublicEmProvider(transport).fetch_roi(request)
    assert volume.origin_voxels == (123, 122, 12) and volume.voxels.shape == (8, 12, 10)
    for z in range(8):
        for y in range(12):
            for x in range(10):
                assert (
                    abs(
                        int(volume.voxels[z, y, x])
                        - ((x + 123) // 128 * 70 + (y + 122) // 128 * 30 + (z + 12) * 3)
                    )
                    <= 1
                )
    assert 0 < transport.downloaded < 1000000
    range_requests = [r for r in em_source[1] if r.has_header("Range")]
    assert all(r.has_header("If-match") for r in range_requests[1:])
    monkeypatch.setattr(
        "banc_explorer.em.transport.urlopen", lambda *a, **k: pytest.fail("offline network")
    )
    cached = PublicEmProvider(RangeCache(tmp_path, offline=True)).fetch_roi(request)
    assert cached.downloaded_bytes == 0
    np.testing.assert_array_equal(cached.voxels, volume.voxels)


@pytest.mark.parametrize(
    "case", ["ignored", "wrong_range", "short", "oversize", "compressed", "missing_version"]
)
def test_transport_rejects_bad_http_before_cache(tmp_path, monkeypatch, case):
    headers = {"Content-Range": "bytes 0-63/9999"}
    data = b"x" * 64
    status = 206
    if case == "ignored":
        status = 200
    elif case == "wrong_range":
        headers["Content-Range"] = "bytes 1-64/9999"
    elif case == "short":
        data = data[:-1]
    elif case == "oversize":
        headers["Content-Length"] = "9999999"
    elif case == "compressed":
        headers["Content-Encoding"] = "gzip"
    elif case == "missing_version":
        headers["ETag"] = ""
    response = Response(data, status, headers)

    def serve(*a, **k):
        return response

    monkeypatch.setattr("banc_explorer.em.transport.urlopen", serve)
    with pytest.raises(ValueError):
        RangeCache(tmp_path).read("8_8_45/00000.shard", 0, 64)
    assert not list(tmp_path.rglob("*.bin"))


def test_transport_budget_paths_missing_cache_and_integrity(tmp_path, em_source, monkeypatch):
    cache = RangeCache(tmp_path)
    for name, a, b in [("../escape", 0, 64), ("8_8_45/00000.shard", 0, 2000001)]:
        with pytest.raises(ValueError):
            cache.read(name, a, b)
    assert not em_source[1]
    with pytest.raises(ValueError, match="Missing EM"):
        RangeCache(tmp_path, offline=True).read("info")
    cache.downloaded = 32_000_000
    with pytest.raises(ValueError, match="transfer budget"):
        cache.read("info")
    cache.downloaded = 0
    cache.read("info")
    next(tmp_path.rglob("*.bin")).write_bytes(b"broken")
    with pytest.raises(ValueError, match="integrity"):
        cache.read("info")


def test_changed_etag_between_cached_ranges_is_rejected(tmp_path, em_source):
    cache = RangeCache(tmp_path)
    cache.read("8_8_45/00000.shard", 0, 16)
    cache.read("8_8_45/00000.shard", 16, 32)
    for path in tmp_path.rglob("*.json"):
        receipt = json.loads(path.read_text())
        if receipt["start"] == 16:
            receipt["etag"] = '"changed"'
            path.write_text(json.dumps(receipt))
    with pytest.raises(ValueError, match="changed"):
        cache.read("8_8_45/00000.shard", 16, 32)


def test_malformed_cached_receipt_is_actionable(tmp_path, em_source):
    cache = RangeCache(tmp_path)
    cache.read("info")
    next(tmp_path.rglob("*.json")).write_text("[]")
    with pytest.raises(ValueError, match="Invalid EM cache receipt"):
        cache.read("info")


@pytest.mark.parametrize("case", ["invalid_deflate", "decompression_limit"])
def test_minishard_compression_guards(case):
    data = (
        b"\x1f\x8b\x08\x00\x00\x00\x00\x00\x00\xff\x07" + bytes(8)
        if case == "invalid_deflate"
        else gzip.compress(bytes(4_000_008))
    )
    with pytest.raises(ValueError, match="EM minishard index"):
        decode_minishard(data, 64)


@pytest.mark.parametrize("case", ["bounds", "schema", "missing_chunk", "bad_jpeg", "bad_index"])
def test_provider_refuses_missing_or_changed_source(tmp_path, em_source, case):
    objects, _ = em_source
    request = RoiRequest(center_nm=(1024, 1024, 720), size_voxels=(10, 12, 8))
    if case == "bounds":
        request = RoiRequest(center_nm=(0, 0, 0))
    elif case == "schema":
        objects["info"] = objects["info"].replace(b'"jpeg"', b'"raw"')
    elif case == "missing_chunk":
        objects["8_8_45/00000.shard"] = bytes(64)
    elif case == "bad_jpeg":
        with pytest.raises(ValueError):
            decode_jpeg(jpeg(np.zeros((3, 4), dtype=np.uint8)), (128, 128, 16))
        return
    elif case == "bad_index":
        with pytest.raises(ValueError):
            decode_minishard(gzip.compress(b"bad"), 64)
        return
    with pytest.raises(ValueError):
        PublicEmProvider(RangeCache(tmp_path)).fetch_roi(request)


def test_manifest_export_roundtrip_and_tampering(tmp_path, em_source):
    destination = tmp_path / "roi"
    result = export_roi(
        PublicEmProvider(RangeCache(tmp_path / "cache")),
        point(),
        destination,
        size_voxels=(10, 12, 8),
    )
    assert load_roi(destination) == result
    assert result.point.kind == "swc_node" and result.image_materialization is None
    assert (
        json.loads((destination / "roi.json").read_text())["point"]["neuron_id"]
        == "720575941350568496"
    )
    with pytest.raises(ValueError, match="already exists"):
        export_roi(None, point(), destination)
    (destination / result.slices[0].file).write_bytes(b"bad")
    with pytest.raises(ValueError, match="integrity"):
        load_roi(destination)


def test_roi_limits_before_download():
    for changes in [
        dict(size_voxels=(257, 256, 32)),
        dict(size_voxels=(1, 1, 65)),
        dict(mip=7),
        dict(center_nm=(float("nan"), 0, 0)),
        dict(size_voxels=(True, 2, 3)),
    ]:
        with pytest.raises(ValueError):
            RoiRequest.model_validate(dict(center_nm=(0, 0, 0)) | changes)


@pytest.mark.skipif(
    not os.environ.get("GODOT_BIN"), reason="Set GODOT_BIN for EM loader integration"
)
@pytest.mark.parametrize(
    "case",
    [
        "valid",
        "indices",
        "checksum",
        "png_dimensions",
        "schema",
        "provenance",
        "synapse",
        "synapse_version",
        "synapse_hash",
        "synapse_id",
        "synapse_source",
    ],
)
def test_godot_em_contract(tmp_path, em_source, case):
    directory = tmp_path / "roi"
    export_roi(
        PublicEmProvider(RangeCache(tmp_path / "cache")),
        synapse_point() if case.startswith("synapse") else point(),
        directory,
        size_voxels=(10, 12, 8),
    )
    path = directory / "roi.json"
    value = json.loads(path.read_text())
    expected = ""
    if case == "indices":
        value["slices"][0]["file"] = "../escape.png"
        expected = "Unsafe"
    elif case == "checksum":
        (directory / value["slices"][0]["file"]).write_bytes(b"bad")
        expected = "checksum"
    elif case == "png_dimensions":
        image_path = directory / value["slices"][0]["file"]
        Image.fromarray(np.zeros((11, 10), dtype=np.uint8)).save(image_path)
        value["slices"][0]["sha256"] = sha256(image_path.read_bytes()).hexdigest()
        expected = "dimensions"
    elif case == "schema":
        value["schema_version"] = 99
        expected = "Unsupported schema"
    elif case == "provenance":
        value["image_materialization"] = 888
        expected = "Unsupported EM source"
    elif case == "synapse_version":
        value["point"]["table"] = "synapses_v2"
        expected = "version"
    elif case == "synapse_hash":
        value["point"]["evidence_sha256"] = "z" * 64
        expected = "hashes"
    elif case == "synapse_id":
        value["point"]["synapse_id"] = 9007199254740993
        expected = "provenance"
    elif case == "synapse_source":
        value["point"]["query_source"]["url"] = "https://wrong.invalid/query"
        expected = "source"
    path.write_text(json.dumps(value), encoding="utf-8")
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [
            os.environ["GODOT_BIN"],
            "--headless",
            "--path",
            str(root / "godot"),
            "--script",
            "res://tests/em_validate.gd",
            "--log-file",
            str(tmp_path / "em.log"),
            "--",
            str(directory),
            expected,
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )
    output = result.stdout + result.stderr
    assert result.returncode == 0 and "ERROR:" not in output and "GODOT_EM_OK" in output, output
