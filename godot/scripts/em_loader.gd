extends RefCounted
## Validates a small portable EM slice stack before it replaces the visible one.

const BundleLoader = preload("res://scripts/bundle_loader.gd")
const SOURCE = "https://storage.googleapis.com/seunglab_lee_fly_cns_001_alignment/aligned/v0"
var error := ""


func fail(message: String) -> Dictionary:
	error = message
	return {}


func load_roi(directory: String) -> Dictionary:
	error = ""
	var helper := BundleLoader.new()
	var file := FileAccess.open(directory.path_join("roi.json"), FileAccess.READ)
	if file == null or file.get_length() > 1000000:
		return fail("Missing or oversized EM manifest.")
	var manifest := helper.read_json(directory.path_join("roi.json"))
	if not helper.error.is_empty():
		return fail(helper.error)
	if manifest.get("artifact_type") != "em_roi" or manifest.get("image_source") != SOURCE or not manifest.has("image_materialization") or manifest.image_materialization != null or manifest.get("array_order") != "zyx" or manifest.get("pixel_type") != "uint8" or manifest.get("image_encoding") != "jpeg-derived":
		return fail("Unsupported EM source/contract.")
	var request: Variant = manifest.get("request")
	var point: Variant = manifest.get("point")
	if not request is Dictionary or not point is Dictionary or point.get("kind") != "swc_node" or point.get("dataset") != "BANC" or point.get("materialization") != 888 or not helper.decimal_id(point.get("neuron_id")) or not helper.decimal_id(point.get("swc_node_id"), true):
		return fail("Invalid EM morphology-point provenance.")
	if manifest.get("interpretation") != "Morphology-point image context; not a verified synapse location.":
		return fail("Missing EM interpretation.")
	if not point.get("skeleton_source") is Dictionary or not point.skeleton_source.get("sha256") is String or point.skeleton_source.sha256.length() != 64:
		return fail("Missing SWC source hash.")
	var dimensions: Variant = request.get("size_voxels")
	if not dimensions is Array or dimensions.size() != 3 or not helper.integer(request.get("mip")) or request.mip > 6:
		return fail("Invalid EM dimensions/scale.")
	for i in 3:
		if not helper.integer(dimensions[i], 1) or dimensions[i] > (64 if i == 2 else 256):
			return fail("EM dimensions exceed viewer budget.")
	var resolution := Vector3(8 * pow(2, request.mip), 8 * pow(2, request.mip), 45)
	if not helper.vector(manifest.get("resolution_nm")) or helper.point(manifest.resolution_nm) != resolution or not helper.vector(request.get("center_nm")) or request.center_nm != point.get("center_nm") or not helper.vector(manifest.get("origin_voxels")):
		return fail("Invalid EM coordinate transform.")
	for i in 3:
		if not helper.integer(manifest.origin_voxels[i]) or manifest.origin_voxels[i] != floor(request.center_nm[i] / resolution[i]) - int(dimensions[i]) / 2:
			return fail("EM voxel origin disagrees with selected point.")
	if manifest.get("scale_key") != "%d_%d_45" % [resolution.x, resolution.y] or not manifest.get("source_ranges") is Array or manifest.source_ranges.is_empty() or manifest.source_ranges.size() > 200:
		return fail("Missing EM image range provenance.")
	var slices: Variant = manifest.get("slices")
	if not slices is Array or slices.size() != dimensions[2]:
		return fail("EM slice count mismatch.")
	var images: Array[ImageTexture] = []
	for i in slices.size():
		var ref: Variant = slices[i]
		if not ref is Dictionary or ref.get("file") != "slices/%03d.png" % i or not ref.get("sha256") is String or ref.sha256.length() != 64:
			return fail("Unsafe or invalid EM slice reference.")
		var path: String = directory.path_join(ref.file)
		var png := FileAccess.open(path, FileAccess.READ)
		if png == null or png.get_length() > 1000000 or png.get_length() < 33 or FileAccess.get_sha256(path) != ref.sha256:
			return fail("EM slice checksum/size failure.")
		var header := png.get_buffer(33)
		# Validate IHDR dimensions before decompressing any image.
		if header.slice(0, 8).hex_encode() != "89504e470d0a1a0a" or header.slice(12, 16).get_string_from_ascii() != "IHDR" or be32(header, 16) != dimensions[0] or be32(header, 20) != dimensions[1] or header[24] != 8 or header[25] != 0:
			return fail("Unsupported PNG dimensions or pixel format.")
		var image := Image.new()
		if image.load(path) != OK or image.get_width() != dimensions[0] or image.get_height() != dimensions[1]:
			return fail("Cannot decode EM slice.")
		images.append(ImageTexture.create_from_image(image))
	return {"manifest": manifest, "images": images, "directory": directory}


func be32(data: PackedByteArray, offset: int) -> int:
	return (int(data[offset]) << 24) | (int(data[offset + 1]) << 16) | (int(data[offset + 2]) << 8) | int(data[offset + 3])
