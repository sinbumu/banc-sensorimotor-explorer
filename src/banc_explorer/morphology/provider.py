import logging
from pathlib import Path
from urllib.error import HTTPError

from banc_explorer.data.catalog import skeleton
from banc_explorer.data.downloader import download, verify_cache
from banc_explorer.morphology.swc import Skeleton, read_swc

log = logging.getLogger(__name__)
MAX_SWC_BYTES = 20_000_000


def fetch_skeleton(
    neuron_id: int,
    cache: Path,
    *,
    offline: bool = False,
    max_bytes: int = MAX_SWC_BYTES,
    refresh: bool = False,
) -> tuple[Skeleton, dict]:
    if offline and refresh:
        raise ValueError("--offline and --refresh cannot be used together.")
    if not 0 < max_bytes <= MAX_SWC_BYTES:
        raise ValueError("SWC byte budget must be between 1 and 20,000,000 bytes.")
    asset = skeleton(neuron_id)
    path = asset.local_path(cache)
    try:
        if not offline:
            download(asset, cache, max_bytes=max_bytes, refresh=refresh)
        receipt = verify_cache(asset, cache)
    except HTTPError as exc:
        if exc.code == 404:
            raise ValueError(
                f"No v888 full skeleton for neuron {neuron_id}: {asset.url}. "
                "No older ID or morphology version was substituted."
            ) from exc
        raise
    except ValueError as exc:
        if offline:
            raise ValueError(
                f"Offline skeleton unavailable or invalid: {path}. "
                f"Run morphology fetch --id {neuron_id}. {exc}"
            ) from exc
        raise
    if receipt.get("materialization") != 888:
        raise ValueError(f"Unexpected morphology materialization in {path} receipt.")
    if receipt["bytes"] > max_bytes:
        raise ValueError(f"SWC exceeds the remaining scene byte budget: {path}.")
    parsed = read_swc(path, source_units="nm")
    log.info(
        "SWC %s: %s nodes / %s roots / source nm", neuron_id, len(parsed.nodes), len(parsed.roots)
    )
    return parsed, receipt
