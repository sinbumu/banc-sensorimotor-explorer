"""A small offline inspection aid; the production viewer remains Godot."""

import json
from importlib.resources import files
from pathlib import Path

from banc_explorer.morphology.export import load_scene


def write_preview(directory: Path, output: Path) -> None:
    if output.exists():
        raise ValueError(f"Preview already exists: {output}. Choose a new output file.")
    scene, geometries = load_scene(directory)
    payload = {
        "version": scene.path_result.manifest.connectivity_version,
        "mode": scene.path_result.manifest.path_mode.value,
        "scale": scene.coordinate_transform.nm_per_world_unit,
        "neurons": [
            {
                "id": str(n.id),
                "label": n.cell_type or "Unlabeled neuron",
                "class": n.super_class or "Unknown class",
                "points": g.points,
                "parents": g.parents,
            }
            for n, g in zip(scene.path_result.neurons, geometries, strict=True)
        ],
    }
    # Metadata is data, never executable HTML or JS. Prevent closing the script element.
    encoded = (
        json.dumps(payload, separators=(",", ":"))
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("&", "\\u0026")
    )
    template = (
        files("banc_explorer.morphology").joinpath("inspection.html").read_text(encoding="utf-8")
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8") as stream:
        stream.write(template.replace("__SCENE_DATA__", encoded))
