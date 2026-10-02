"""Small public BANC EM cutouts from explicitly supported precomputed sharding."""

import gzip
import io
import itertools
import json
import math
import struct
import zlib
from dataclasses import dataclass
from typing import Annotated, Protocol

import numpy as np
from pydantic import Field

from banc_explorer.em.transport import RangeCache
from banc_explorer.models import Contract
from banc_explorer.morphology.transforms import Vector3

Dimension = Annotated[int, Field(strict=True, ge=1, le=256)]
RoiSize = tuple[Dimension, Dimension, Annotated[int, Field(strict=True, ge=1, le=64)]]


class RoiRequest(Contract):
    center_nm: Vector3
    size_voxels: RoiSize = (256, 256, 32)
    mip: int = Field(default=0, ge=0, le=6, strict=True)


@dataclass
class EmVolume:
    voxels: np.ndarray  # z, y, x; no display-coordinate rotation
    origin_voxels: tuple[int, int, int]
    resolution_nm: tuple[float, float, float]
    scale_key: str
    source_info: dict
    receipts: list[dict]
    downloaded_bytes: int


class EmProvider(Protocol):
    def fetch_roi(self, request: RoiRequest) -> EmVolume: ...


def morton(coordinate, grid):
    if any(
        type(v) is not int or not 0 <= v < size for v, size in zip(coordinate, grid, strict=True)
    ):
        raise ValueError("Chunk coordinate outside grid.")
    result, output_bit = 0, 0
    for bit in range(max((n - 1).bit_length() for n in grid)):
        for dimension in range(3):
            if 1 << bit < grid[dimension]:
                result |= ((coordinate[dimension] >> bit) & 1) << output_bit
                output_bit += 1
    return result


def decode_minishard(raw: bytes, index_end: int) -> dict[int, tuple[int, int]]:
    try:
        with gzip.GzipFile(fileobj=io.BytesIO(raw)) as stream:
            data = stream.read(4_000_001)
    except (OSError, EOFError, zlib.error) as exc:
        raise ValueError("Invalid compressed EM minishard index.") from exc
    if len(data) > 4_000_000 or len(data) % 24 or not data:
        raise ValueError("Invalid or oversized EM minishard index.")
    values = np.frombuffer(data, dtype="<u8").reshape(3, -1)
    chunk_id, offset = 0, index_end
    result = {}
    for delta_id, delta_offset, size in zip(*values, strict=True):
        chunk_id += int(delta_id)
        offset += int(delta_offset)
        size = int(size)
        if (
            chunk_id >= 2**64
            or chunk_id in result
            or size <= 0
            or size > 2_000_000
            or offset + size >= 2**64
        ):
            raise ValueError("Invalid EM index entry.")
        result[chunk_id] = (offset, offset + size)
        offset += size
    return result


def decode_jpeg(data, shape):
    try:
        from PIL import Image
    except ImportError:
        raise ValueError("Install optional EM support: uv sync --extra api --extra em") from None
    with Image.open(io.BytesIO(data)) as image:
        if (
            image.format != "JPEG"
            or image.mode != "L"
            or image.width * image.height != math.prod(shape)
        ):
            raise ValueError("EM JPEG dimensions/type do not match its chunk.")
        # JPEG rows flatten in x-fastest order, independently of JPEG width/height.
        return np.asarray(image, dtype=np.uint8).reshape(tuple(reversed(shape))).copy()


class PublicEmProvider:
    def __init__(self, transport: RangeCache):
        self.transport = transport
        self.indices = {}

    def fetch_roi(self, request: RoiRequest) -> EmVolume:
        info = json.loads(self.transport.read("info"))
        if (
            not isinstance(info, dict)
            or info.get("type") != "image"
            or info.get("data_type") != "uint8"
            or info.get("num_channels") != 1
        ):
            raise ValueError("Unsupported EM image metadata.")
        scales = info.get("scales", [])
        if not isinstance(scales, list) or request.mip >= len(scales):
            raise ValueError("Requested EM scale is unavailable.")
        scale = scales[request.mip]
        resolution = [8 * 2**request.mip, 8 * 2**request.mip, 45]
        # Deliberately narrow provider: reject changed layouts rather than guessing.
        expected_sharding = {
            "@type": "neuroglancer_uint64_sharded_v1",
            "hash": "identity",
            "preshift_bits": 11,
            "minishard_bits": 2,
            "shard_bits": 17 - 2 * request.mip,
            "minishard_index_encoding": "gzip",
            "data_encoding": "raw",
        }
        if (
            not isinstance(scale, dict)
            or scale.get("resolution") != resolution
            or scale.get("voxel_offset") != [0, 0, 0]
            or scale.get("chunk_sizes") != [[128, 128, 16]]
            or scale.get("encoding") != "jpeg"
            or scale.get("sharding") != expected_sharding
            or scale.get("key") != "_".join(map(str, resolution))
        ):
            raise ValueError("Unsupported BANC EM scale/sharding layout; verify source metadata.")
        volume_size = scale.get("size")
        if (
            not isinstance(volume_size, list)
            or len(volume_size) != 3
            or any(type(v) is not int or v <= 0 for v in volume_size)
        ):
            raise ValueError("Invalid EM volume dimensions.")
        origin = tuple(
            math.floor(c / r) - n // 2
            for c, r, n in zip(request.center_nm, resolution, request.size_voxels, strict=True)
        )
        end = tuple(a + n for a, n in zip(origin, request.size_voxels, strict=True))
        if any(a < 0 or b > s for a, b, s in zip(origin, end, volume_size, strict=True)):
            raise ValueError(
                "Requested EM ROI extends outside the public volume; choose an interior point or smaller ROI."
            )
        chunk = (128, 128, 16)
        grid = tuple(math.ceil(v / c) for v, c in zip(volume_size, chunk, strict=True))
        ranges = [
            range(a // c, (b - 1) // c + 1) for a, b, c in zip(origin, end, chunk, strict=True)
        ]
        if math.prod(map(len, ranges)) > 64:
            raise ValueError("EM ROI exceeds the 64-chunk budget.")
        result = np.empty(tuple(reversed(request.size_voxels)), dtype=np.uint8)
        for coord in itertools.product(*ranges):
            begin = tuple(c * n for c, n in zip(coord, chunk, strict=True))
            stop = tuple(min(a + n, v) for a, n, v in zip(begin, chunk, volume_size, strict=True))
            shape = tuple(b - a for a, b in zip(begin, stop, strict=True))
            identifier = morton(coord, grid)
            data = self._chunk(scale, identifier)
            pixels = decode_jpeg(data, shape)
            low = tuple(max(a, b) for a, b in zip(begin, origin, strict=True))
            high = tuple(min(a, b) for a, b in zip(stop, end, strict=True))
            target = tuple(slice(a - o, b - o) for a, b, o in zip(low, high, origin, strict=True))[
                ::-1
            ]
            source = tuple(slice(a - o, b - o) for a, b, o in zip(low, high, begin, strict=True))[
                ::-1
            ]
            result[target] = pixels[source]
        return EmVolume(
            result,
            origin,
            tuple(resolution),
            scale["key"],
            info,
            list(self.transport.receipts.values()),
            self.transport.downloaded,
        )

    def _chunk(self, scale, identifier):
        spec = scale["sharding"]
        shifted = identifier >> spec["preshift_bits"]
        mini = shifted & 3
        shard = (shifted >> 2) & ((1 << spec["shard_bits"]) - 1)
        name = f"{scale['key']}/{shard:0{math.ceil(spec['shard_bits'] / 4)}x}.shard"
        key = (name, mini)
        if key not in self.indices:
            header = self.transport.read(name, 0, 64)
            start, end = struct.unpack_from("<QQ", header, mini * 16)
            if end <= start:
                raise ValueError(
                    "No EM data for this chunk; missing imagery is not filled with zeros."
                )
            self.indices[key] = decode_minishard(
                self.transport.read(name, 64 + start, 64 + end), 64
            )
        entry = self.indices[key].get(identifier)
        if entry is None:
            raise ValueError("No EM data for this chunk; missing imagery is not filled with zeros.")
        return self.transport.read(name, *entry)
