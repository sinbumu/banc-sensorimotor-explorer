from datetime import datetime
from typing import Annotated, Literal

from pydantic import Field, model_validator

from banc_explorer.models import Contract, NeuronId, PathResult, SourceFile
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


class SkeletonScene(Contract):
    schema_version: Literal[1] = 1
    artifact_type: Literal["skeleton_scene"] = "skeleton_scene"
    path_result: PathResult
    neurons: list[SkeletonReference] = Field(min_length=1)
    coordinate_transform: CoordinateTransform
    bounds_min: Vector3
    bounds_max: Vector3
    simplification: Literal["none"] = "none"

    @model_validator(mode="after")
    def check_references(self):
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
