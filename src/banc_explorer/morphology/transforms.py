from typing import Annotated, Literal

from pydantic import Field

from banc_explorer.models import Contract

Finite = Annotated[float, Field(allow_inf_nan=False)]
Vector3 = tuple[Finite, Finite, Finite]


class CoordinateTransform(Contract):
    source_units: Literal["nm"] = "nm"
    world_units: Literal["godot_unit"] = "godot_unit"
    nm_per_world_unit: float = Field(default=10000, gt=0)
    origin_nm: Vector3
    axis_map: Literal["(x, y, z) -> (x, -z, y)"] = "(x, y, z) -> (x, -z, y)"
    origin_policy: Literal["combined_skeleton_bbox_center"] = "combined_skeleton_bbox_center"

    def forward(self, xyz_nm: Vector3) -> Vector3:
        x, y, z = [
            (v - origin) / self.nm_per_world_unit
            for v, origin in zip(xyz_nm, self.origin_nm, strict=True)
        ]
        return x, -z, y

    def inverse(self, xyz_world: Vector3) -> Vector3:
        x, y, z = xyz_world
        return tuple(
            v * self.nm_per_world_unit + origin
            for v, origin in zip((x, z, -y), self.origin_nm, strict=True)
        )
