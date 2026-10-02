"""Validated file bundles; only selected path neurons are fetched."""

import math
import shutil
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from banc_explorer import __version__
from banc_explorer.data.downloader import sha256
from banc_explorer.models import PathResult
from banc_explorer.morphology.context import fetch_context
from banc_explorer.morphology.models import (
    ContextGeometry,
    ContextReference,
    SceneManifest,
    SkeletonGeometry,
    SkeletonReference,
    SkeletonScene,
)
from banc_explorer.morphology.provider import MAX_SWC_BYTES, fetch_skeleton
from banc_explorer.morphology.transforms import CoordinateTransform
from banc_explorer.provenance import source_file

MAX_SCENE_SOURCE_BYTES = 100_000_000


@contextmanager
def staging_directory(parent: Path):
    # Windows TemporaryDirectory applies an owner-only ACL. A renamed export then
    # cannot be read by the desktop user when built by the sandbox account.
    # Normal mkdir inherits the destination's ACL; use an unpredictable sibling.
    parent = parent.resolve()
    stage = parent / f".scene-{uuid4().hex}"
    stage.mkdir()
    try:
        yield stage
    finally:
        if stage.exists():
            if stage.resolve().parent != parent:
                raise ValueError("Refusing to clean a staging directory outside its parent.")
            shutil.rmtree(stage)


def bounds(points):
    return (
        tuple(min(p[axis] for p in points) for axis in range(3)),
        tuple(max(p[axis] for p in points) for axis in range(3)),
    )


def export_scene(
    path_file: Path,
    directory: Path,
    cache: Path,
    *,
    offline: bool = False,
    nm_per_world_unit: float = 10000,
    include_context: bool = False,
) -> SkeletonScene:
    if directory.exists():
        raise ValueError(f"Output already exists: {directory}. Choose a new scene directory.")
    # Validate before any network request or output creation.
    original = path_file.read_bytes()
    result = PathResult.model_validate_json(original)
    CoordinateTransform(origin_nm=(0, 0, 0), nm_per_world_unit=nm_per_world_unit)
    outlines = fetch_context(cache, offline=offline) if include_context else []
    skeletons = []
    remaining = MAX_SCENE_SOURCE_BYTES
    for neuron in result.neurons:
        if remaining <= 0:
            raise ValueError("Scene exceeds the 100 MB source-SWC budget.")
        item = fetch_skeleton(
            neuron.id, cache, offline=offline, max_bytes=min(MAX_SWC_BYTES, remaining)
        )
        remaining -= item[1]["bytes"]
        skeletons.append(item)
    points_nm = [node.xyz_nm for skeleton, _ in skeletons for node in skeleton.nodes]
    lower, upper = bounds(points_nm)
    transform = CoordinateTransform(
        origin_nm=tuple((a + b) / 2 for a, b in zip(lower, upper, strict=True)),
        nm_per_world_unit=nm_per_world_unit,
    )
    directory.parent.mkdir(parents=True, exist_ok=True)
    with staging_directory(directory.parent) as stage:
        (stage / "skeletons").mkdir()
        references, world_points = [], []
        for order, (neuron, (skeleton, receipt)) in enumerate(
            zip(result.neurons, skeletons, strict=True)
        ):
            indices = {node.id: i for i, node in enumerate(skeleton.nodes)}
            geometry = SkeletonGeometry(
                neuron_id=neuron.id,
                node_ids=[str(n.id) for n in skeleton.nodes],
                labels=[n.label for n in skeleton.nodes],
                points=[transform.forward(n.xyz_nm) for n in skeleton.nodes],
                radii=[n.radius_nm / nm_per_world_unit for n in skeleton.nodes],
                parents=[
                    None if n.parent_id is None else indices[n.parent_id] for n in skeleton.nodes
                ],
            )
            relative = f"skeletons/{neuron.id}.json"
            geometry_file = stage / relative
            geometry_file.write_text(geometry.model_dump_json() + "\n", encoding="utf-8")
            world_points.extend(geometry.points)
            references.append(
                SkeletonReference(
                    id=neuron.id,
                    order=order,
                    skeleton=relative,
                    geometry_sha256=sha256(geometry_file),
                    node_count=len(skeleton.nodes),
                    root_count=len(skeleton.roots),
                    source=source_file(receipt),
                )
            )
        lower, upper = bounds(world_points)
        context = []
        if outlines:
            (stage / "context").mkdir()
        for outline in outlines:
            geometry = ContextGeometry(
                region_id=outline["region_id"],
                points=[transform.forward(p) for p in outline["points_nm"]],
                triangles=outline["triangles"],
            )
            relative = f"context/{geometry.region_id}.json"
            (stage / relative).write_text(geometry.model_dump_json() + "\n", encoding="utf-8")
            context_lower, context_upper = bounds(geometry.points)
            context.append(
                ContextReference(
                    region_id=geometry.region_id,
                    label=outline["label"],
                    geometry=relative,
                    geometry_sha256=sha256(stage / relative),
                    vertex_count=len(geometry.points),
                    triangle_count=len(geometry.triangles),
                    bounds_min=context_lower,
                    bounds_max=context_upper,
                    sources=[source_file(r) for r in outline["receipts"]],
                )
            )
        scene = SkeletonScene(
            schema_version=2 if context else 1,
            context=context,
            path_result=result,
            neurons=references,
            coordinate_transform=transform,
            bounds_min=lower,
            bounds_max=upper,
        )
        # Keep v1 outputs readable by earlier Python readers with extra='forbid'.
        (stage / "path.json").write_text(
            scene.model_dump_json(indent=2, exclude={"context"} if not context else None) + "\n",
            encoding="utf-8",
        )
        (stage / "graph-path.json").write_bytes(original)
        manifest = SceneManifest(
            scene_sha256=sha256(stage / "path.json"),
            graph_path_sha256=sha256(stage / "graph-path.json"),
            created_at=datetime.now(UTC),
            software_version=__version__,
        )
        (stage / "manifest.json").write_text(
            manifest.model_dump_json(indent=2) + "\n", encoding="utf-8"
        )
        load_scene(stage)
        # All files validated before the new output directory becomes visible.
        stage.rename(directory)
    return scene


def safe_file(directory: Path, relative: str) -> Path:
    target = (directory / relative).resolve()
    if not target.is_relative_to(directory.resolve()):
        raise ValueError("Scene reference escapes the bundle directory.")
    return target


def load_scene(directory: Path) -> tuple[SkeletonScene, list[SkeletonGeometry]]:
    manifest = SceneManifest.model_validate_json(safe_file(directory, "manifest.json").read_bytes())
    for name, expected in [
        (manifest.scene_file, manifest.scene_sha256),
        (manifest.graph_path_file, manifest.graph_path_sha256),
    ]:
        if sha256(safe_file(directory, name)) != expected:
            raise ValueError(f"Scene integrity check failed: {name}.")
    scene = SkeletonScene.model_validate_json(
        safe_file(directory, manifest.scene_file).read_bytes()
    )
    graph_path = PathResult.model_validate_json(
        safe_file(directory, manifest.graph_path_file).read_bytes()
    )
    if graph_path != scene.path_result:
        raise ValueError("Scene and original graph path disagree.")
    load_context(directory, scene)
    geometries = []
    for reference in scene.neurons:
        path = safe_file(directory, reference.skeleton)
        if sha256(path) != reference.geometry_sha256:
            raise ValueError(f"Skeleton integrity check failed: {reference.skeleton}.")
        geometry = SkeletonGeometry.model_validate_json(path.read_bytes())
        if (
            geometry.neuron_id != reference.id
            or len(geometry.points) != reference.node_count
            or geometry.parents.count(None) != reference.root_count
        ):
            raise ValueError("Skeleton ID or node/root counts disagree with scene.")
        geometries.append(geometry)
    lower, upper = bounds([point for g in geometries for point in g.points])
    if any(
        not math.isclose(a, b, abs_tol=1e-9)
        for a, b in zip(lower + upper, scene.bounds_min + scene.bounds_max, strict=True)
    ):
        raise ValueError("Skeleton coordinates disagree with scene bounds.")
    return scene, geometries


def load_context(directory: Path, scene: SkeletonScene) -> list[ContextGeometry]:
    result = []
    for reference in scene.context:
        path = safe_file(directory, reference.geometry)
        if sha256(path) != reference.geometry_sha256:
            raise ValueError(f"Outline integrity check failed: {reference.geometry}.")
        geometry = ContextGeometry.model_validate_json(path.read_bytes())
        lower, upper = bounds(geometry.points)
        if (
            geometry.region_id != reference.region_id
            or len(geometry.points) != reference.vertex_count
            or len(geometry.triangles) != reference.triangle_count
            or any(
                not math.isclose(a, b, abs_tol=1e-9)
                for a, b in zip(
                    lower + upper, reference.bounds_min + reference.bounds_max, strict=True
                )
            )
        ):
            raise ValueError("Outline identity, counts or bounds disagree with scene.")
        result.append(geometry)
    return result
