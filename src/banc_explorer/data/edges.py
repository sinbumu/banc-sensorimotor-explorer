from pathlib import Path

import polars as pl
from pyarrow import feather

from banc_explorer.data.metadata import normalize_ids, require_columns

EDGE_COLUMNS = ["pre", "post", "count", "norm", "pre_count", "post_count"]
# Published norm is rounded; retain it rather than silently replacing source data.
NORM_ABSOLUTE_TOLERANCE = 5.1e-5


def normalize_edges(frame: pl.DataFrame) -> pl.DataFrame:
    require_columns(frame, EDGE_COLUMNS)
    frame = normalize_ids(frame, ["pre", "post"])
    for name in ["count", "pre_count", "post_count"]:
        if not frame.schema[name].is_integer():
            raise ValueError(f"{name} must contain integer synapse counts.")
        if frame[name].null_count() or frame.filter(pl.col(name) <= 0).height:
            raise ValueError(f"{name} must contain positive, non-null counts.")
    if not frame.schema["norm"].is_numeric():
        raise ValueError("norm must be numeric.")
    if (
        frame["norm"].null_count()
        or frame.filter(
            ~pl.col("norm").is_finite() | (pl.col("norm") <= 0) | (pl.col("norm") > 1)
        ).height
    ):
        raise ValueError("norm must be finite and in (0, 1].")
    if frame.filter(
        (pl.col("count") > pl.col("post_count")) | (pl.col("count") > pl.col("pre_count"))
    ).height:
        raise ValueError("Edge count exceeds source/target total.")
    if frame.filter(
        (pl.col("norm") - pl.col("count") / pl.col("post_count")).abs() > NORM_ABSOLUTE_TOLERANCE
    ).height:
        raise ValueError("norm differs from count/post_count beyond published rounding tolerance.")
    if frame.select(pl.struct("pre", "post").is_duplicated().any()).item():
        raise ValueError("Duplicate directed pre/post pairs in simple edgelist.")
    return frame


def load_edges(path: Path) -> pl.DataFrame:
    return normalize_edges(pl.from_arrow(feather.read_table(path)))


def filter_edges(frame: pl.DataFrame, min_synapse_count: int = 5) -> pl.DataFrame:
    if min_synapse_count < 1:
        raise ValueError("min_synapse_count must be >= 1.")
    return frame.filter(pl.col("count") >= min_synapse_count)
