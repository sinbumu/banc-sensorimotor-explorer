from dataclasses import dataclass
from pathlib import Path

BUCKET = "https://storage.googleapis.com/lee-lab_brain-and-nerve-cord-fly-connectome"


@dataclass(frozen=True)
class Asset:
    filename: str
    category: str
    remote_directory: str = "compiled_data/banc_888"
    materialization: int | None = 888
    cache_filename: str | None = None

    @property
    def url(self) -> str:
        return f"{BUCKET}/{self.remote_directory}/{self.filename}"

    def local_path(self, cache: Path) -> Path:
        return cache / self.category / (self.cache_filename or self.filename)


METADATA = Asset("banc_888_meta.feather", "metadata")


def edgelist(version: str = "v3") -> Asset:
    if version not in {"v2", "v3"}:
        raise ValueError("Connectivity version must be v2 or v3.")
    return Asset(f"banc_888_edgelist_simple_{version}.feather", "edges")


def skeleton(neuron_id: int) -> Asset:
    from banc_explorer.models import parse_id

    return Asset(
        f"{parse_id(neuron_id)}_skeleton.swc",
        "skeletons",
        "compiled_data/banc_888/banc_banc_space_swc",
    )
