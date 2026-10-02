"""Resolve exact cached SWC nodes before allowing bounded EM jobs."""

from pydantic import Field

from banc_explorer.em.export import MorphologyPoint, export_roi
from banc_explorer.em.provider import PublicEmProvider, RoiSize
from banc_explorer.em.transport import RangeCache
from banc_explorer.models import Contract, NeuronId
from banc_explorer.morphology.models import Digest
from banc_explorer.morphology.provider import fetch_skeleton
from banc_explorer.provenance import source_file


class EmRequest(Contract):
    neuron_id: NeuronId
    swc_node_id: str = Field(pattern=r"^(0|[1-9][0-9]{0,12})$")
    swc_sha256: Digest
    size_voxels: RoiSize = (256, 256, 32)
    mip: int = Field(default=0, ge=0, le=6, strict=True)
    allow_downloads: bool = False


def build_em_scene(request: EmRequest, cache, directory, offline):
    skeleton, receipt = fetch_skeleton(request.neuron_id, cache, offline=True)
    if receipt["sha256"] != request.swc_sha256:
        raise ValueError("Scene SWC hash differs from the API cache. Re-export/reload the scene.")
    node = next((n for n in skeleton.nodes if str(n.id) == request.swc_node_id), None)
    if node is None:
        raise ValueError("Selected SWC node does not exist in the verified skeleton.")
    point = MorphologyPoint(
        neuron_id=request.neuron_id,
        swc_node_id=request.swc_node_id,
        center_nm=node.xyz_nm,
        skeleton_source=source_file(receipt),
    )
    transport = RangeCache(cache, offline=offline or not request.allow_downloads)
    return export_roi(
        PublicEmProvider(transport),
        point,
        directory,
        size_voxels=request.size_voxels,
        mip=request.mip,
    )
