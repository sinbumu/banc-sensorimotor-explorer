"""Portable PNG slice stacks with point, coordinate and per-range provenance."""

import math
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator

from banc_explorer import __version__
from banc_explorer.data.downloader import sha256
from banc_explorer.em.provider import EmProvider, RoiRequest
from banc_explorer.em.transport import BASE
from banc_explorer.models import Contract, NeuronId, SourceFile
from banc_explorer.morphology.export import load_scene, safe_file, staging_directory
from banc_explorer.morphology.models import Digest
from banc_explorer.morphology.transforms import Vector3

MORPHOLOGY_CONTEXT = "Morphology-point image context; not a verified synapse location."
SYNAPSE_CONTEXT = "Predicted-synapse image context; contact identity is not independently verified."


class MorphologyPoint(Contract):
    kind: Literal["swc_node"] = "swc_node"
    dataset: Literal["BANC"] = "BANC"
    materialization: Literal[888] = 888
    neuron_id: NeuronId
    swc_node_id: str = Field(pattern=r"^(0|[1-9][0-9]*)$")
    center_nm: Vector3
    skeleton_source: SourceFile


class SynapsePoint(Contract):
    kind: Literal["predicted_synapse"] = "predicted_synapse"
    dataset: Literal["BANC"] = "BANC"
    materialization: Literal[888] = 888
    connectivity_version: Literal["v2", "v3"]
    table: Literal["synapses_v2", "synapses_v3"]
    synapse_id: NeuronId
    pre: NeuronId
    post: NeuronId
    center_nm: Vector3
    coordinate_field: Literal["ctr_pt_position"] = "ctr_pt_position"
    evidence_sha256: Digest
    path_sha256: Digest
    query_source: SourceFile

    @model_validator(mode="after")
    def check_source(self):
        from banc_explorer.synapses.evidence import query_suffix
        from banc_explorer.synapses.transport import BASE as CAVE_BASE

        if (
            self.table != f"synapses_{self.connectivity_version}"
            or self.pre == self.post
            or self.query_source.url != CAVE_BASE + query_suffix(self.table)
        ):
            raise ValueError("Inconsistent synapse point source/version.")
        return self


class SliceReference(Contract):
    file: str = Field(pattern=r"^slices/[0-9]{3}\.png$")
    sha256: Digest


class RoiManifest(Contract):
    schema_version: Literal[1, 2] = 1
    artifact_type: Literal["em_roi"] = "em_roi"
    image_source: Literal[BASE] = BASE
    image_materialization: None = None
    request: RoiRequest
    point: MorphologyPoint | SynapsePoint = Field(discriminator="kind")
    origin_voxels: tuple[int, int, int]
    resolution_nm: Vector3
    scale_key: str
    array_order: Literal["zyx"] = "zyx"
    pixel_type: Literal["uint8"] = "uint8"
    image_encoding: Literal["jpeg-derived"] = "jpeg-derived"
    interpretation: Literal[MORPHOLOGY_CONTEXT, SYNAPSE_CONTEXT] = MORPHOLOGY_CONTEXT
    source_info: dict
    source_ranges: list[dict] = Field(min_length=1, max_length=200)
    downloaded_bytes: int = Field(ge=0, le=32_000_000)
    slices: list[SliceReference] = Field(min_length=1, max_length=64)
    created_at: datetime
    software_version: str

    @model_validator(mode="after")
    def check_coordinates(self):
        synapse = isinstance(self.point, SynapsePoint)
        if self.schema_version != (2 if synapse else 1) or self.interpretation != (
            SYNAPSE_CONTEXT if synapse else MORPHOLOGY_CONTEXT
        ):
            raise ValueError("EM schema/interpretation disagrees with point provenance.")
        resolution = (8 * 2**self.request.mip, 8 * 2**self.request.mip, 45)
        origin = tuple(
            math.floor(c / r) - n // 2
            for c, r, n in zip(
                self.request.center_nm, resolution, self.request.size_voxels, strict=True
            )
        )
        if (
            self.point.center_nm != self.request.center_nm
            or self.resolution_nm != resolution
            or self.origin_voxels != origin
            or self.scale_key != "_".join(map(str, resolution))
        ):
            raise ValueError("Inconsistent EM point/voxel transform.")
        if (
            any(v < 0 for v in origin)
            or len(self.slices) != self.request.size_voxels[2]
            or [s.file for s in self.slices]
            != [f"slices/{i:03d}.png" for i in range(len(self.slices))]
        ):
            raise ValueError("Invalid EM slice stack layout.")
        return self


def point_from_scene(directory: Path, neuron_id: int, node_id: str) -> MorphologyPoint:
    scene, geometries = load_scene(directory)
    for ref, geometry in zip(scene.neurons, geometries, strict=True):
        if ref.id == neuron_id:
            if node_id not in geometry.node_ids:
                raise ValueError("SWC node ID is not present in the selected scene neuron.")
            return MorphologyPoint(
                neuron_id=neuron_id,
                swc_node_id=node_id,
                center_nm=scene.coordinate_transform.inverse(
                    geometry.points[geometry.node_ids.index(node_id)]
                ),
                skeleton_source=ref.source,
            )
    raise ValueError("Neuron is not present in this scene.")


def point_from_evidence(directory: Path, synapse_id: str) -> SynapsePoint:
    from banc_explorer.models import parse_id
    from banc_explorer.synapses.evidence import load_evidence

    evidence = load_evidence(directory)
    selected_id = parse_id(synapse_id)
    for row in evidence.rows:
        if row.id == selected_id:
            return SynapsePoint(
                connectivity_version=evidence.connectivity_version,
                table=evidence.table,
                synapse_id=row.id,
                pre=evidence.pre,
                post=evidence.post,
                center_nm=row.center_nm,
                evidence_sha256=sha256(directory / "evidence.json"),
                path_sha256=evidence.path_sha256,
                query_source=evidence.receipts[-1],
            )
    raise ValueError("Synapse ID is not present in the validated evidence subset.")


def export_roi(
    provider: EmProvider,
    point: MorphologyPoint | SynapsePoint,
    directory: Path,
    *,
    size_voxels=(256, 256, 32),
    mip=0,
) -> RoiManifest:
    try:
        from PIL import Image
    except ImportError:
        raise ValueError("Install optional EM support: uv sync --extra api --extra em") from None
    if directory.exists():
        raise ValueError("EM output already exists; choose a new directory.")
    request = RoiRequest(center_nm=point.center_nm, size_voxels=size_voxels, mip=mip)
    volume = provider.fetch_roi(request)
    if (
        volume.voxels.shape != tuple(reversed(request.size_voxels))
        or str(volume.voxels.dtype) != "uint8"
    ):
        raise ValueError("EM provider returned an unexpected volume layout.")
    directory.parent.mkdir(parents=True, exist_ok=True)
    with staging_directory(directory.parent) as stage:
        (stage / "slices").mkdir()
        slices = []
        for i, pixels in enumerate(volume.voxels):
            name = f"slices/{i:03d}.png"
            Image.fromarray(pixels).save(stage / name)
            slices.append(SliceReference(file=name, sha256=sha256(stage / name)))
        manifest = RoiManifest(
            schema_version=2 if isinstance(point, SynapsePoint) else 1,
            interpretation=SYNAPSE_CONTEXT
            if isinstance(point, SynapsePoint)
            else MORPHOLOGY_CONTEXT,
            request=request,
            point=point,
            origin_voxels=volume.origin_voxels,
            resolution_nm=volume.resolution_nm,
            scale_key=volume.scale_key,
            source_info=volume.source_info,
            source_ranges=volume.receipts,
            downloaded_bytes=volume.downloaded_bytes,
            slices=slices,
            created_at=datetime.now(UTC),
            software_version=__version__,
        )
        (stage / "roi.json").write_text(manifest.model_dump_json(indent=2) + "\n", encoding="utf-8")
        load_roi(stage)
        stage.rename(directory)
    return manifest


def load_roi(directory: Path) -> RoiManifest:
    from PIL import Image

    path = safe_file(directory, "roi.json")
    if path.stat().st_size > 1_000_000:
        raise ValueError("EM manifest exceeds the 1 MB budget.")
    manifest = RoiManifest.model_validate_json(path.read_bytes())
    for ref in manifest.slices:
        path = safe_file(directory, ref.file)
        if path.stat().st_size > 1_000_000 or sha256(path) != ref.sha256:
            raise ValueError("EM slice integrity check failed.")
        with Image.open(path) as image:
            if (
                image.format != "PNG"
                or image.mode != "L"
                or image.size != manifest.request.size_voxels[:2]
            ):
                raise ValueError("Invalid EM PNG dimensions/type.")
            image.verify()
    return manifest
