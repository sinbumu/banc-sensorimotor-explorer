"""Bounded atomic downloads with local SHA-256 receipts and offline cache reuse."""

import hashlib
import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from urllib.request import urlopen

from banc_explorer.data.catalog import Asset

log = logging.getLogger(__name__)
LIMIT = 1_000_000_000


def recovery_command(asset: Asset) -> str:
    if asset.category == "skeletons":
        return f"morphology fetch --id {asset.filename.split('_')[0]}"
    return "data prepare"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def verify_cache(asset: Asset, cache: Path) -> dict:
    path = asset.local_path(cache)
    receipt_path = path.with_suffix(path.suffix + ".json")
    if not path.exists() or not receipt_path.exists():
        raise ValueError(f"Missing cache or receipt: {path}. Run {recovery_command(asset)}.")
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    if (
        receipt.get("url") != asset.url
        or receipt.get("bytes") != path.stat().st_size
        or receipt.get("sha256") != sha256(path)
    ):
        raise ValueError(
            f"Cache integrity check failed: {path}. Run {recovery_command(asset)} --refresh."
        )
    return receipt


def download(asset: Asset, cache: Path, *, max_bytes: int = LIMIT, refresh: bool = False) -> Path:
    if not 0 < max_bytes <= LIMIT:
        raise ValueError(
            "Downloads are capped at 1 GB; use a separate approved workflow for bulk data."
        )
    path = asset.local_path(cache)
    if path.exists() and not refresh:
        verify_cache(asset, cache)
        log.info("Verified cached file: %s", path.resolve())
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_suffix(path.suffix + ".part")
    receipt_path = path.with_suffix(path.suffix + ".json")
    receipt_partial = receipt_path.with_suffix(".json.part")
    log.info("Downloading %s -> %s (limit %.0f MB)", asset.url, path.resolve(), max_bytes / 1e6)
    try:
        with urlopen(asset.url, timeout=60) as response:
            length = response.headers.get("Content-Length")
            expected = int(length) if length is not None else None
            if expected is not None and expected > max_bytes:
                raise ValueError(f"Download refused: {expected:,} bytes exceeds {max_bytes:,}.")
            log.info("Remote size: %s bytes", expected if expected is not None else "unknown")
            digest = hashlib.sha256()
            total = 0
            with partial.open("wb") as stream:
                while block := response.read(1024 * 1024):
                    total += len(block)
                    if total > max_bytes:
                        raise ValueError("Download exceeded the configured byte limit.")
                    stream.write(block)
                    digest.update(block)
            if total == 0 or (expected is not None and total != expected):
                raise ValueError("Incomplete download; no cache file was promoted.")
            receipt = {
                "dataset": "BANC",
                "materialization": asset.materialization,
                "url": asset.url,
                "bytes": total,
                "sha256": digest.hexdigest(),
                "etag": response.headers.get("ETag"),
                "generation": response.headers.get("x-goog-generation"),
                "downloaded_at": datetime.now(UTC).isoformat(),
            }
        receipt_partial.write_text(json.dumps(receipt, indent=2), encoding="utf-8")
        partial.replace(path)
        receipt_partial.replace(receipt_path)
    finally:
        partial.unlink(missing_ok=True)
        receipt_partial.unlink(missing_ok=True)
    log.info("Cached %.1f MB: %s", total / 1e6, path.resolve())
    return path
