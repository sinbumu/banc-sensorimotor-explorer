from datetime import datetime
from typing import Annotated, Literal

from pydantic import Field, model_validator

from banc_explorer.models import Contract, NeuronId, PathResult, SourceFile
from banc_explorer.morphology.context import MAX_TRIANGLES, MAX_VERTICES, REGIONS
from banc_explorer.morphology.swc import validate_parents
from banc_explorer.morphology.transforms import CoordinateTransform, Vector3

Index = Annotated[int, Field(strict=True, ge=0)]
Digest = Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]


class SkeletonGeometry(Contract):
    schema_version: Literal[1] = 1
    neuron_id: NeuronId
    units: Literal["godot_unit"] = "godot_unit"
    node_ids: list[str] = Field(min_length=1)
    labels: list[Index]
    points: list[Vector3]
    radii: list[Annotated[float, Field(ge=0)]]
    parents: list[Index | None]

    @model_validator(mode="after")
    def check_topology(self):
        n = len(self.node_ids)
        if any(len(values) != n for values in [self.points, self.radii, self.parents, self.labels]):
            raise ValueError("Skeleton arrays must have the same length.")
        if len(set(self.node_ids)) != n or any(
            not value.isascii() or not value.isdecimal() or str(int(value)) != value
            for value in self.node_ids
        ):
            raise ValueError("SWC node IDs must be unique canonical nonnegative decimal strings.")
        validate_parents(list(range(n)), self.parents)
        return self


class SkeletonReference(Contract):
    id: NeuronId
    order: Index
    skeleton: str = Field(pattern=r"^skeletons/[0-9]+\.json$")
    geometry_sha256: Digest
    node_count: int = Field(gt=0)
    root_count: int = Field(gt=0)
    source: SourceFile
    source_units: Literal["nm"] = "nm"
    source_materialization: Literal[888] = 888
    provider: Literal["banc_v888_full_swc"] = "banc_v888_full_swc"


class ContextGeometry(Contract):
    schema_version: Literal[1] = 1
    artifact_type: Literal["neuropil_outline"] = "neuropil_outline"
    region_id: Literal["3", "4"]
    units: Literal["godot_unit"] = "godot_unit"
    points: list[Vector3] = Field(min_length=3, max_length=MAX_VERTICES)
    triangles: list[tuple[Index, Index, Index]] = Field(min_length=1, max_length=MAX_TRIANGLES)

    @model_validator(mode="after")
    def check_indices(self):
        if any(max(face) >= len(self.points) or len(set(face)) != 3 for face in self.triangles):
            raise ValueError("Invalid outline triangle indices.")
        return self


class ContextReference(Contract):
    region_id: Literal["3", "4"]
    label: str
    geometry: str = Field(pattern=r"^context/[34]\.json$")
    geometry_sha256: Digest
    vertex_count: int = Field(ge=3, le=MAX_VERTICES)
    triangle_count: int = Field(ge=1, le=MAX_TRIANGLES)
    bounds_min: Vector3
    bounds_max: Vector3
    source_units: Literal["nm"] = "nm"
    source_materialization: None = None
    provider: Literal["banc_public_region_outlines"] = "banc_public_region_outlines"
    sources: list[SourceFile] = Field(min_length=4, max_length=4)

    @model_validator(mode="after")
    def check_reference(self):
        if (
            self.label != REGIONS[self.region_id]
            or self.geometry != f"context/{self.region_id}.json"
        ):
            raise ValueError("Outline identity/label/reference mismatch.")
        if any(a > b for a, b in zip(self.bounds_min, self.bounds_max, strict=True)):
            raise ValueError("Invalid outline bounds.")
        return self


class SkeletonScene(Contract):
    schema_version: Literal[1, 2] = 1
    artifact_type: Literal["skeleton_scene"] = "skeleton_scene"
    path_result: PathResult
    neurons: list[SkeletonReference] = Field(min_length=1)
    coordinate_transform: CoordinateTransform
    bounds_min: Vector3
    bounds_max: Vector3
    simplification: Literal["none"] = "none"
    context: list[ContextReference] = Field(default_factory=list, max_length=2)

    @model_validator(mode="after")
    def check_references(self):
        if self.schema_version == 1 and self.context:
            raise ValueError("Context requires scene schema version 2.")
        if self.schema_version == 2 and [c.region_id for c in self.context] != ["3", "4"]:
            raise ValueError(
                "Scene version 2 requires the brain and VNC outlines in catalog order."
            )
        if [n.id for n in self.neurons] != [n.id for n in self.path_result.neurons]:
            raise ValueError("Scene neuron order must match graph path.")
        for order, neuron in enumerate(self.neurons):
            if neuron.order != order or neuron.skeleton != f"skeletons/{neuron.id}.json":
                raise ValueError("Scene skeleton reference/order is inconsistent.")
        if any(a > b for a, b in zip(self.bounds_min, self.bounds_max, strict=True)):
            raise ValueError("Invalid scene bounds.")
        return self


class SceneManifest(Contract):
    schema_version: Literal[1] = 1
    dataset: Literal["BANC"] = "BANC"
    materialization: Literal[888] = 888
    scene_file: Literal["path.json"] = "path.json"
    scene_sha256: Digest
    graph_path_file: Literal["graph-path.json"] = "graph-path.json"
    graph_path_sha256: Digest
    created_at: datetime
    software_version: str
