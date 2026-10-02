from pathlib import Path

import pytest

from banc_explorer.morphology.swc import parse_swc, read_swc
from banc_explorer.morphology.transforms import CoordinateTransform


def test_unordered_zero_ids_forest_and_units():
    text = "# Comment\n9 2 1.5 -2 3 0.25 0\n0 0 0 0 0 0 -1\n45 1 9 9 9 1 -1 # root\n"
    skeleton = parse_swc(text, source_units="um")
    assert skeleton.roots == (0, 45)
    assert skeleton.nodes[0].xyz_nm == (1500, -2000, 3000)
    assert skeleton.nodes[0].radius_nm == 250
    assert skeleton.nodes[0].parent_id == 0
    assert parse_swc(text, source_units="nm").nodes[0].xyz_nm == (1.5, -2, 3)


@pytest.mark.parametrize(
    "text",
    [
        "",
        "# no nodes",
        "1 0 0 0 0 1",
        "1.5 0 0 0 0 1 -1",
        "1 0 nan 0 0 1 -1",
        "1 0 0 inf 0 1 -1",
        "1 0 0 0 0 -1 -1",
        "1 0 0 0 0 1 99",
        "1 0 0 0 0 1 -2",
        "1 0 0 0 0 1 1",
        "0 0 0 0 0 1 -1\n0 0 1 1 1 1 -1",
        "0 0 0 0 0 1 -1\n1 0 0 0 0 1 2\n2 0 0 0 0 1 1",
    ],
)
def test_reject_invalid_swc(text):
    with pytest.raises(ValueError):
        parse_swc(text, source_units="nm")


def test_deep_chain_without_recursion():
    skeleton = parse_swc(
        "\n".join(f"{i} 0 {i} 0 0 1 {i - 1}" for i in range(5000)), source_units="nm"
    )
    assert len(skeleton.nodes) == 5000
    assert skeleton.roots == (0,)


def test_forward_inverse_and_scale():
    transform = CoordinateTransform(origin_nm=(400000, 800000, 100000))
    assert transform.forward((410000, 820000, 130000)) == (1, -3, 2)
    assert transform.inverse((1, -3, 2)) == (410000, 820000, 130000)
    assert transform.forward(transform.origin_nm) == (0, 0, 0)
    assert transform.inverse(transform.forward((404567.89, 808901.23, 104567.89))) == pytest.approx(
        (404567.89, 808901.23, 104567.89)
    )
    for scale in [0, -1000, float("nan"), float("inf")]:
        with pytest.raises(ValueError):
            CoordinateTransform(origin_nm=(0, 0, 0), nm_per_world_unit=scale)
    with pytest.raises(ValueError):
        CoordinateTransform(origin_nm=(0, float("nan"), 0))


def test_real_v888_swc_excerpt():
    skeleton = read_swc(
        Path(__file__).parent / "fixtures/banc_v888_sensory_excerpt.swc", source_units="nm"
    )
    assert len(skeleton.nodes) == 8
    assert skeleton.roots == (1,)
    assert skeleton.nodes[0].xyz_nm == (450455, 790717, 134504)
    assert skeleton.nodes[0].radius_nm == pytest.approx(37.568678806055)
