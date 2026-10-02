import polars as pl
import pytest
from typer.testing import CliRunner

from banc_explorer.cli import app
from banc_explorer.config import load_settings
from banc_explorer.data.catalog import METADATA, edgelist
from banc_explorer.data.edges import filter_edges, normalize_edges
from banc_explorer.data.metadata import candidates, normalize_metadata


def metadata():
    # Synthetic IDs deliberately exceed JavaScript's and float64's exact integer range.
    return pl.DataFrame(
        {
            "banc_888_id": ["720575940000000001", "720575940000000002"],
            "super_class": ["sensory", "motor"],
            "proofread": ["TRUE", "FALSE"],
            "body_part_sensory": ["leg", None],
        }
    )


def edges():
    return pl.DataFrame(
        {
            "pre": ["1", "2"],
            "post": ["2", "1"],
            "count": [4, 6],
            "norm": [0.4, 0.6],
            "pre_count": [10, 10],
            "post_count": [10, 10],
        }
    )


def test_metadata_exact_ids_and_candidates():
    frame = normalize_metadata(metadata())
    assert frame["banc_888_id"].to_list() == [720575940000000001, 720575940000000002]
    assert candidates(frame, "sensory", body_part="leg").height == 1
    assert candidates(frame, "motor").height == 0
    assert candidates(frame, "motor", proofread_only=False).height == 1


@pytest.mark.parametrize(
    "mutation",
    [
        lambda d: d.with_columns(pl.col("banc_888_id").cast(pl.Float64)),
        lambda d: d.with_columns(pl.lit("invalid").alias("banc_888_id")),
        lambda d: d.with_columns(pl.lit("1").alias("banc_888_id")),
        lambda d: d.with_columns(pl.lit("yes").alias("proofread")),
        lambda d: d.drop("super_class"),
    ],
)
def test_reject_invalid_metadata(mutation):
    with pytest.raises(ValueError):
        normalize_metadata(mutation(metadata()))


def test_threshold_preserves_direction_and_source():
    original = normalize_edges(edges())
    filtered = filter_edges(original)
    assert filtered.select("pre", "post").rows() == [(2, 1)]
    assert original.height == 2


@pytest.mark.parametrize(
    "field,value", [("count", 0), ("norm", float("nan")), ("norm", 0.9), ("post_count", 1)]
)
def test_reject_invalid_edges(field, value):
    with pytest.raises(ValueError):
        normalize_edges(edges().with_columns(pl.lit(value).alias(field)))


def test_rounded_source_norm():
    frame = (
        edges()
        .head(1)
        .with_columns(
            pl.lit(3).alias("post_count"), pl.lit(1).alias("count"), pl.lit(0.3333).alias("norm")
        )
    )
    assert normalize_edges(frame)["norm"][0] == 0.3333


def test_duplicate_edges():
    with pytest.raises(ValueError, match="Duplicate"):
        normalize_edges(pl.concat([edges(), edges()]))


def test_catalog_and_config(tmp_path):
    folder = tmp_path / "configs"
    folder.mkdir()
    config = folder / "default.toml"
    config.write_text('connectivity_version = "v2"\ncache_dir = "cache"')
    assert load_settings(config).cache_dir == tmp_path / "cache"
    assert "_v2.feather" in edgelist("v2").url
    assert "banc_888" in METADATA.url
    with pytest.raises(ValueError):
        edgelist("v1")


def test_missing_cache_is_actionable(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = CliRunner().invoke(app, ["data", "validate"])
    assert result.exit_code == 1
    assert "Run data prepare" in result.output
