"""Two public BANC neuropil outlines; no volume, atlas or neuron-mesh download."""

import gzip
import io
import json
import struct
from pathlib import Path

import numpy as np

from banc_explorer.data.catalog import Asset
from banc_explorer.data.downloader import download, verify_cache

REGIONS = {"3": "BANC_brain_neuropil", "4": "BANC_vnc_neuropil"}
MAX_BYTES = 5_000_000
MAX_VERTICES = 100_000
MAX_TRIANGLES = 200_000


def context_asset(relative: str) -> Asset:
    # Callers only use fixed catalog entries, never a remote fragment's arbitrary URL.
    return Asset(
        relative, "context", "region_outlines", None, relative.replace("/", "_").replace(":", "_")
    )


def read_asset(relative: str, cache: Path, *, offline: bool, refresh: bool):
    asset = context_asset(relative)
    if not offline:
        download(asset, cache, max_bytes=MAX_BYTES, refresh=refresh)
    receipt = verify_cache(asset, cache)
    if receipt["bytes"] > MAX_BYTES:
        raise ValueError("Outline exceeds the 5 MB per-file byte budget.")
    payload = asset.local_path(cache).read_bytes()
    # GCS may return stored gzip or transparently decompressed legacy fragments.
    if payload.startswith(b"\x1f\x8b"):
        with gzip.GzipFile(fileobj=io.BytesIO(payload)) as stream:
            payload = stream.read(MAX_BYTES + 1)
        if len(payload) > MAX_BYTES:
            raise ValueError("Decompressed outline exceeds the 5 MB byte budget.")
    return payload, receipt


def parse_legacy_mesh(payload: bytes) -> tuple[list, list]:
    """Neuroglancer legacy mesh: uint32le count, float32le xyz nm, uint32le faces."""
    if len(payload) < 4 or len(payload) > MAX_BYTES:
        raise ValueError("Invalid legacy mesh byte length.")
    count = struct.unpack_from("<I", payload)[0]
    end = 4 + count * 12
    if not 3 <= count <= MAX_VERTICES or end >= len(payload) or (len(payload) - end) % 12:
        raise ValueError("Invalid legacy mesh vertex/triangle layout.")
    points = np.frombuffer(payload, dtype="<f4", count=count * 3, offset=4).reshape(-1, 3)
    triangles = np.frombuffer(payload, dtype="<u4", offset=end).reshape(-1, 3)
    if not np.isfinite(points).all() or len(triangles) > MAX_TRIANGLES or triangles.max() >= count:
        raise ValueError("Invalid legacy mesh coordinates or triangle indices.")
    if (
        np.any(triangles[:, 0] == triangles[:, 1])
        or np.any(triangles[:, 1] == triangles[:, 2])
        or np.any(triangles[:, 0] == triangles[:, 2])
    ):
        raise ValueError("Degenerate legacy mesh triangle indices.")
    return points.tolist(), triangles.tolist()


def fetch_context(cache: Path, *, offline=False, refresh=False) -> list[dict]:
    if offline and refresh:
        raise ValueError("Cannot refresh outlines offline.")
    info_raw, info_receipt = read_asset("info", cache, offline=offline, refresh=refresh)
    info = json.loads(info_raw)
    if (
        not isinstance(info, dict)
        or info.get("mesh") != "meshes"
        or info.get("segment_properties") != "segment_properties"
    ):
        raise ValueError("Unsupported BANC outline catalog layout.")
    properties_raw, properties_receipt = read_asset(
        "segment_properties/info", cache, offline=offline, refresh=refresh
    )
    properties = json.loads(properties_raw)
    inline = properties.get("inline") if isinstance(properties, dict) else None
    if not isinstance(inline, dict) or not isinstance(inline.get("properties"), list):
        raise ValueError("Invalid BANC outline segment properties.")
    labels = [p for p in inline["properties"] if isinstance(p, dict) and p.get("type") == "label"]
    ids = inline.get("ids", [])
    if (
        not isinstance(ids, list)
        or not all(isinstance(id, str) for id in ids)
        or len(labels) != 1
        or not isinstance(labels[0].get("values"), list)
        or len(labels[0].get("values", [])) != len(ids)
        or len(set(ids)) != len(ids)
    ):
        raise ValueError("Invalid BANC outline region labels.")
    names = dict(zip(ids, labels[0]["values"], strict=True))
    result = []
    for region_id, label in REGIONS.items():
        if names.get(region_id) != label:
            raise ValueError(f"BANC region {region_id} label changed; verify provider before use.")
        manifest_raw, manifest_receipt = read_asset(
            f"meshes/{region_id}:0", cache, offline=offline, refresh=refresh
        )
        fragment = f"{region_id}:0:1"
        if json.loads(manifest_raw) != {"fragments": [fragment]}:
            raise ValueError(
                "Unsupported outline fragments; expected the single verified fragment."
            )
        mesh_raw, mesh_receipt = read_asset(
            f"meshes/{fragment}", cache, offline=offline, refresh=refresh
        )
        points, triangles = parse_legacy_mesh(mesh_raw)
        result.append(
            dict(
                region_id=region_id,
                label=label,
                points_nm=points,
                triangles=triangles,
                receipts=[info_receipt, properties_receipt, manifest_receipt, mesh_receipt],
            )
        )
    return result
