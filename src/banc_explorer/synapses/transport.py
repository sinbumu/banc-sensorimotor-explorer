"""Narrow CAVE JSON transport with a fixed host and bounded response bodies."""

import hashlib
import json
import os
import re
from http.client import HTTPException
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener

HOST = "https://cave.fanc-fly.com"
BASE = f"{HOST}/materialize/api/v3/datastack/brain_and_nerve_cord/version/888"
MAX_RESPONSE = 2_000_000
MAX_TRANSFER = 2_300_000


def local_token() -> str:
    """Read standard CAVE credential files; never log, copy or write credentials."""
    token = os.environ.get("BANC_CAVE_TOKEN")
    if token is None:
        directory = Path.home() / ".cloudvolume" / "secrets"
        for name in ("cave.fanc-fly.com-cave-secret.json", "cave-secret.json"):
            path = directory / name
            if not path.is_file():
                continue
            try:
                if path.stat().st_size > 64_000:
                    raise ValueError()
                value = json.loads(path.read_bytes())
                token = value.get("brain_and_nerve_cord", value.get("token"))
            except (ValueError, OSError, AttributeError):
                raise ValueError("Invalid CAVE credential file. See docs/synapses.md.") from None
            if token is not None:
                break
    if not isinstance(token, str) or not re.fullmatch(r"[!-~]{1,8192}", token):
        raise ValueError(
            "CAVE credential is missing or invalid. Configure the standard local CAVE "
            "credential file (docs/synapses.md); do not paste a token into chat."
        )
    return token


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # Never forward Authorization to a login service or a changed host.
        return None


class CaveTransport:
    def __init__(self):
        self._token = local_token()
        self._opener = build_opener(NoRedirect())
        self.downloaded = 0

    def read(self, suffix: str, payload: dict | None = None, *, limit=100_000):
        if suffix not in ("", "/tables") and not re.fullmatch(
            r"/table/synapses_v[23]/(metadata|query\?return_pyarrow=false&split_positions=false)",
            suffix,
        ):
            raise ValueError("Unsupported CAVE endpoint.")
        if not 0 < limit <= MAX_RESPONSE or self.downloaded + limit > MAX_TRANSFER:
            raise ValueError("CAVE query exceeds its response/transfer budget.")
        url = BASE + suffix
        request = Request(
            url,
            data=None if payload is None else json.dumps(payload).encode(),
            headers={
                "Authorization": "Bearer " + self._token,
                "Accept": "application/json",
                "Content-Type": "application/json",
                "Accept-Encoding": "identity",
            },
        )
        try:
            with self._opener.open(request, timeout=30) as response:
                if response.status != 200:
                    raise ValueError("Unexpected CAVE response status.")
                if response.headers.get("Content-Encoding", "identity") != "identity":
                    raise ValueError("Unsupported CAVE response compression.")
                if response.headers.get("Content-Type", "").split(";")[0] != "application/json":
                    raise ValueError("CAVE returned non-JSON data; check account access.")
                try:
                    content_length = int(response.headers.get("Content-Length", limit))
                except (TypeError, ValueError):
                    raise ValueError("Invalid CAVE response length header.") from None
                if not 0 <= content_length <= limit:
                    raise ValueError("CAVE response exceeds the byte budget.")
                body = response.read(limit + 1)
                if len(body) > limit:
                    raise ValueError("CAVE response exceeds the byte budget.")
                resolution = response.headers.get("dataframe_resolution")
                # Warnings may signal server limits or remapped/expired snapshots.
                warning = bool(response.headers.get("Warning"))
        except HTTPError as exc:
            code = exc.code
            exc.close()
            if code in (301, 302, 303, 307, 308, 401, 403):
                raise ValueError(
                    "CAVE access denied/login required. See docs/synapses.md."
                ) from None
            raise ValueError(
                f"CAVE HTTP {code}; required v888 table/API may be unavailable. No fallback used."
            ) from None
        except (URLError, OSError, HTTPException):
            raise ValueError("CAVE connection failed; check connectivity and retry.") from None
        self.downloaded += len(body)
        try:
            data = json.loads(body)
        except (ValueError, UnicodeError):
            raise ValueError("CAVE returned invalid JSON.") from None
        receipt = dict(url=url, sha256=hashlib.sha256(body).hexdigest(), bytes=len(body))
        return data, resolution, warning, receipt
