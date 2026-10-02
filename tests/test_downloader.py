from io import BytesIO

import pytest

from banc_explorer.data import downloader as module
from banc_explorer.data.catalog import METADATA


class Response(BytesIO):
    def __init__(self, payload, length=None):
        super().__init__(payload)
        self.headers = {} if length is None else {"Content-Length": str(length)}


def test_cache_integrity_and_offline_reuse(tmp_path, monkeypatch):
    monkeypatch.setattr(module, "urlopen", lambda *a, **k: Response(b"fixture", 7))
    path = module.download(METADATA, tmp_path)
    monkeypatch.setattr(module, "urlopen", lambda *a, **k: pytest.fail("cache accessed network"))
    assert module.download(METADATA, tmp_path) == path
    assert module.verify_cache(METADATA, tmp_path)["bytes"] == 7
    path.write_bytes(b"corrupt")
    with pytest.raises(ValueError, match="integrity"):
        module.verify_cache(METADATA, tmp_path)


@pytest.mark.parametrize(
    "payload,length,limit", [(b"abc", 3, 2), (b"abc", None, 2), (b"abc", 4, 10), (b"", None, 10)]
)
def test_size_guards_and_partial_cleanup(tmp_path, monkeypatch, payload, length, limit):
    monkeypatch.setattr(module, "urlopen", lambda *a, **k: Response(payload, length))
    with pytest.raises(ValueError):
        module.download(METADATA, tmp_path, max_bytes=limit)
    assert not METADATA.local_path(tmp_path).exists()
    assert not list(tmp_path.rglob("*.part"))


def test_failed_refresh_preserves_cache(tmp_path, monkeypatch):
    monkeypatch.setattr(module, "urlopen", lambda *a, **k: Response(b"original", 8))
    path = module.download(METADATA, tmp_path)
    monkeypatch.setattr(module, "urlopen", lambda *a, **k: Response(b"bad", 100))
    with pytest.raises(ValueError):
        module.download(METADATA, tmp_path, refresh=True)
    assert path.read_bytes() == b"original"
    module.verify_cache(METADATA, tmp_path)
