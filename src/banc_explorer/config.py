"""Configuration paths are relative to the config's repository root."""

import tomllib
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class Settings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    materialization: Literal[888] = 888
    connectivity_version: Literal["v2", "v3"] = "v3"
    cache_dir: Path = Path(".cache/banc/v888")
    min_synapse_count: int = Field(default=5, ge=1)
    epsilon: float = Field(default=1e-12, gt=0, le=1, allow_inf_nan=False)
    max_download_bytes: int = Field(default=1_000_000_000, gt=0, le=1_000_000_000)


def load_settings(path: Path | None = None) -> Settings:
    if path is None:
        return Settings()
    with path.open("rb") as stream:
        settings = Settings.model_validate(tomllib.load(stream))
    if not settings.cache_dir.is_absolute():
        settings.cache_dir = path.resolve().parent.parent / settings.cache_dir
    return settings
