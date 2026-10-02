from pathlib import Path

import polars as pl
from pyarrow import feather


def normalize_ids(frame: pl.DataFrame, names: list[str]) -> pl.DataFrame:
    for name in names:
        dtype = frame.schema[name]
        if dtype != pl.String and not dtype.is_integer():
            raise ValueError(
                f"{name}: IDs must be integer or decimal string, never float ({dtype})."
            )
        if dtype == pl.String and frame.filter(~pl.col(name).str.contains(r"^[0-9]+$")).height:
            raise ValueError(f"{name}: invalid decimal neuron ID.")
        frame = frame.with_columns(pl.col(name).cast(pl.UInt64, strict=True))
        if frame[name].null_count() or frame.filter(pl.col(name) == 0).height:
            raise ValueError(f"{name}: missing or zero neuron ID.")
    return frame


def require_columns(frame: pl.DataFrame, names: list[str]) -> None:
    missing = set(names) - set(frame.columns)
    if missing:
        raise ValueError(f"Missing required columns: {', '.join(sorted(missing))}")
    if frame.is_empty():
        raise ValueError("Data table is empty.")


def normalize_metadata(frame: pl.DataFrame) -> pl.DataFrame:
    require_columns(frame, ["banc_888_id", "super_class", "proofread"])
    frame = normalize_ids(frame, ["banc_888_id"])
    if frame["banc_888_id"].n_unique() != frame.height:
        raise ValueError("Duplicate banc_888_id values in metadata.")
    if frame.schema["proofread"] == pl.String:
        values = pl.col("proofread").str.to_lowercase()
        if frame.filter(~values.is_in(["true", "false"])).height:
            raise ValueError("proofread must contain TRUE/FALSE or boolean values.")
        frame = frame.with_columns((values == "true").alias("proofread"))
    elif frame.schema["proofread"] != pl.Boolean:
        raise ValueError("proofread must be boolean or TRUE/FALSE strings.")
    return frame


def load_metadata(path: Path) -> pl.DataFrame:
    return normalize_metadata(pl.from_arrow(feather.read_table(path)))


def candidates(
    frame: pl.DataFrame, kind: str, *, body_part: str | None = None, proofread_only: bool = True
) -> pl.DataFrame:
    if kind not in {"sensory", "motor"}:
        raise ValueError("Candidate kind must be sensory or motor.")
    result = frame.filter(pl.col("super_class") == kind)
    if proofread_only:
        result = result.filter(pl.col("proofread").fill_null(False))
    if body_part:
        field = "body_part_sensory" if kind == "sensory" else "body_part_effector"
        require_columns(frame, [field])
        result = result.filter(pl.col(field).str.contains(body_part, literal=True))
    return result.sort("banc_888_id")
