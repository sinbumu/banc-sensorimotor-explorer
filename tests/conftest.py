import polars as pl
import pytest


@pytest.fixture
def toy_tables():
    # Short weak route: 1->2->5. Stronger longer route: 1->3->4->5.
    # Target 5's input totals are preserved even when an upstream neuron is excluded.
    metadata = pl.DataFrame(
        {
            "banc_888_id": [1, 2, 3, 4, 5, 6],
            "super_class": ["sensory", "intrinsic", "intrinsic", "intrinsic", "motor", "motor"],
            "proofread": [True, False, True, True, True, True],
            "body_part_sensory": ["leg", None, None, None, None, None],
            "body_part_effector": [None, None, None, None, "leg", "leg"],
        }
    )
    edges = pl.DataFrame(
        {
            "pre": [1, 2, 1, 3, 4],
            "post": [2, 5, 3, 4, 5],
            "count": [5, 5, 90, 90, 90],
            "norm": [0.05, 0.05, 0.9, 0.9, 0.9],
            "pre_count": [100, 100, 100, 100, 100],
            "post_count": [100, 100, 100, 100, 100],
        }
    )
    return metadata, edges


@pytest.fixture
def synthetic_context(monkeypatch):
    from banc_explorer.morphology.context import REGIONS

    receipt = {"url": "synthetic-outline", "sha256": "a" * 64, "bytes": 1, "generation": "123"}
    outlines = [
        dict(
            region_id=id,
            label=label,
            points_nm=[(0, 0, 0), (100000, 0, 0), (0, 100000, 0)],
            triangles=[(0, 1, 2)],
            receipts=[receipt] * 4,
        )
        for id, label in REGIONS.items()
    ]
    monkeypatch.setattr("banc_explorer.morphology.export.fetch_context", lambda *a, **k: outlines)
    return outlines
