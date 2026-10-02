"""Verified byte-range cache. A server that ignores Range is never read in full."""

import hashlib
import json
import logging
import re
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from uuid import uuid4

BASE = "https://storage.googleapis.com/seunglab_lee_fly_cns_001_alignment/aligned/v0"
MAX_RANGE = 2_000_000
MAX_TRANSFER = 32_000_000
log = logging.getLogger(__name__)


class RangeCache:
    def __init__(self, cache: Path, *, offline=False):
        self.directory = cache / "em" / "ranges"
        self.offline = offline
        self.downloaded = 0
        self.accessed = 0
        self.receipts: dict[str, dict] = {}
        self.versions: dict[str, tuple] = {}

    def read(self, relative: str, start: int | None = None, end: int | None = None) -> bytes:
        if relative != "info" and not re.fullmatch(
            r"[0-9]+_[0-9]+_[0-9]+/[a-f0-9]+\.shard", relative
        ):
            raise ValueError("Unsupported EM source path.")
        if relative == "info":
            if start is not None or end is not None:
                raise ValueError("Info must be read as bounded metadata.")
            limit = 100_000
        else:
            if (
                type(start) is not int
                or type(end) is not int
                or not 0 <= start < end
                or end - start > MAX_RANGE
            ):
                raise ValueError("EM range exceeds the 2 MB per-request budget.")
            limit = end - start
        url = f"{BASE}/{relative}"
        identity = dict(url=url, start=start, end=end)
        key = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()
        path = self.directory / f"{key}.bin"
        receipt_path = self.directory / f"{key}.json"
        if path.exists() and receipt_path.exists():
            receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
            if (
                not isinstance(receipt, dict)
                or any(receipt.get(k) != v for k, v in identity.items())
                or not 0 < path.stat().st_size <= limit
            ):
                raise ValueError("Invalid EM cache receipt/size. Use a fresh EM cache directory.")
            data = path.read_bytes()
            if receipt.get("sha256") != hashlib.sha256(data).hexdigest() or receipt.get(
                "bytes"
            ) != len(data):
                raise ValueError("EM cache integrity failure. Use a fresh EM cache directory.")
            if start is not None and len(data) != end - start:
                raise ValueError("Truncated cached EM range.")
        else:
            if self.offline:
                raise ValueError(
                    "Missing EM range cache. Enable EM fetching or run em fetch once online."
                )
            if self.downloaded + limit > MAX_TRANSFER:
                raise ValueError("EM request exceeds the 32 MB transfer budget.")
            headers = {"Accept-Encoding": "identity"}
            if start is not None:
                headers["Range"] = f"bytes={start}-{end - 1}"
            if url in self.versions:
                headers["If-Match"] = self.versions[url][0]
            log.info(
                "EM fetch %s %s (max %s bytes)", relative, headers.get("Range", "metadata"), limit
            )
            try:
                with urlopen(Request(url, headers=headers), timeout=20) as response:
                    expected_status = 200 if start is None else 206
                    if response.status != expected_status:
                        raise ValueError(
                            "EM server ignored the byte range; refusing whole-shard download."
                        )
                    if response.headers.get("Content-Encoding", "identity") != "identity":
                        raise ValueError("Unexpected HTTP compression on EM byte ranges.")
                    if int(response.headers.get("Content-Length", limit)) > limit:
                        raise ValueError("EM response exceeds its byte budget.")
                    total = None
                    if start is not None:
                        match = re.fullmatch(
                            r"bytes ([0-9]+)-([0-9]+)/([0-9]+)",
                            response.headers.get("Content-Range", ""),
                        )
                        if (
                            not match
                            or tuple(map(int, match.groups()[:2])) != (start, end - 1)
                            or int(match[3]) < end
                        ):
                            raise ValueError("EM Content-Range disagrees with the requested bytes.")
                        total = int(match[3])
                    data = response.read(limit + 1)
                    if not data or len(data) > limit or (start is not None and len(data) != limit):
                        raise ValueError("Incomplete or oversized EM range response.")
                    receipt = identity | dict(
                        bytes=len(data),
                        sha256=hashlib.sha256(data).hexdigest(),
                        etag=response.headers.get("ETag"),
                        generation=response.headers.get("x-goog-generation"),
                        object_bytes=total,
                    )
            except HTTPError as exc:
                raise ValueError(
                    f"Public EM request failed (HTTP {exc.code}); source may have changed or the chunk may be unavailable."
                ) from None
            self.downloaded += len(data)
            self._version(url, receipt)
            self.directory.mkdir(parents=True, exist_ok=True)
            temporary = self.directory / f".{uuid4().hex}.part"
            try:
                temporary.write_bytes(data)
                temporary.replace(path)
                temporary.write_text(json.dumps(receipt, indent=2), encoding="utf-8")
                temporary.replace(receipt_path)
            finally:
                temporary.unlink(missing_ok=True)
        self._version(url, receipt)
        self.accessed += len(data)
        if self.accessed > 64_000_000 or len(self.receipts) >= 200:
            raise ValueError("EM operation exceeds its 64 MB / 200 range access budget.")
        self.receipts[key] = receipt
        return data

    def _version(self, url, receipt):
        version = (receipt.get("etag"), receipt.get("generation"))
        if not all(isinstance(v, str) and v for v in version):
            raise ValueError("EM source is missing ETag/generation provenance.")
        if url in self.versions and self.versions[url] != version:
            raise ValueError("EM source changed between ranges. Use a fresh EM cache directory.")
        self.versions[url] = version
