extends RefCounted
## Offline reader for skeleton_scene v1/v2. Never converts root IDs to numbers.

const MAX_FILE_BYTES = 128 * 1024 * 1024
const MAX_BUNDLE_BYTES = 256 * 1024 * 1024
const MAX_POINTS = 1000000
var error := ""
var bytes_read := 0


func fail(message: String) -> Dictionary:
	error = message
	return {}


func read_json(path: String, digest: String = "", versions: Array = [1]) -> Dictionary:
	if not FileAccess.file_exists(path):
		return fail("Missing file: " + path)
	var file := FileAccess.open(path, FileAccess.READ)
	if file == null:
		return fail("Cannot read: " + path)
	var length := file.get_length()
	bytes_read += length
	if length > MAX_FILE_BYTES or bytes_read > MAX_BUNDLE_BYTES:
		return fail("Scene exceeds viewer file/bundle budget (128 / 256 MiB).")
	if not digest.is_empty() and FileAccess.get_sha256(path) != digest:
		return fail("SHA-256 mismatch: " + path + ". Re-export the scene from Python.")
	var parser := JSON.new()
	if parser.parse(file.get_as_text()) != OK or not parser.data is Dictionary:
		return fail("Invalid JSON object: " + path)
	var value: Dictionary = parser.data
	# JSON numbers are floats; Array.has uses stricter type matching than ==.
	if not integer(value.get("schema_version"), 1) or not versions.has(int(value.schema_version)):
		return fail("Unsupported schema_version in " + path + "; supported: " + str(versions))
	return value


func number(value: Variant) -> bool:
	return (value is float or value is int) and is_finite(float(value))


func integer(value: Variant, minimum: int = 0) -> bool:
	return number(value) and value >= minimum and value == floor(value)


func vector(value: Variant) -> bool:
	return value is Array and value.size() == 3 and number(value[0]) and number(value[1]) and number(value[2])


func point(value: Array) -> Vector3:
	return Vector3(value[0], value[1], value[2])


func decimal_id(value: Variant, allow_zero := false) -> bool:
	if not value is String or value.is_empty():
		return false
	if value == "0":
		return allow_zero
	if value.begins_with("0"):
		return false
	for character in value:
		if character < "0" or character > "9":
			return false
	return true


func load_bundle(directory: String) -> Dictionary:
	error = ""
	bytes_read = 0
	var manifest := read_json(directory.path_join("manifest.json"))
	if not error.is_empty():
		return {}
	if manifest.get("dataset") != "BANC" or manifest.get("materialization") != 888:
		return fail("Expected a BANC v888 scene manifest.")
	if manifest.get("scene_file") != "path.json" or manifest.get("graph_path_file") != "graph-path.json":
		return fail("Unexpected manifest file references. Re-export with the Python CLI.")
	for key in ["scene_sha256", "graph_path_sha256"]:
		if not manifest.get(key) is String or manifest[key].length() != 64:
			return fail("Missing manifest checksum: " + key)
	var scene := read_json(directory.path_join("path.json"), manifest.scene_sha256, [1, 2])
	if not error.is_empty():
		return {}
	var graph := read_json(directory.path_join("graph-path.json"), manifest.graph_path_sha256)
	if not error.is_empty():
		return {}
	if scene.get("artifact_type") != "skeleton_scene" or graph.get("artifact_type") != "graph_path":
		return fail("Expected skeleton_scene and graph_path artifacts.")
	if scene.get("path_result") != graph:
		return fail("Embedded path differs from graph-path.json.")
	if not validate_graph(graph):
		return fail("Invalid directed path, cost or provenance. Run Python scene validate.")
	if not scene.get("neurons") is Array or scene.neurons.size() != graph.neurons.size():
		return fail("Scene/path neuron count mismatch.")
	if not vector(scene.get("bounds_min")) or not vector(scene.get("bounds_max")):
		return fail("Invalid scene bounds.")
	var lower := point(scene.bounds_min)
	var upper := point(scene.bounds_max)
	if lower.x > upper.x or lower.y > upper.y or lower.z > upper.z:
		return fail("Reversed scene bounds.")
	var transform_data: Variant = scene.get("coordinate_transform")
	if not transform_data is Dictionary or transform_data.get("source_units") != "nm" or transform_data.get("world_units") != "godot_unit":
		return fail("Unsupported coordinate units.")
	if not vector(transform_data.get("origin_nm")) or not number(transform_data.get("nm_per_world_unit")) or transform_data.nm_per_world_unit <= 0:
		return fail("Invalid coordinate transform.")
	if transform_data.get("axis_map") != "(x, y, z) -> (x, -z, y)":
		return fail("Unsupported coordinate axis mapping.")
	var geometries: Array = []
	var total_points := 0
	for i in scene.neurons.size():
		var reference: Variant = scene.neurons[i]
		if not reference is Dictionary or reference.get("id") != graph.neurons[i].id or reference.get("order") != i:
			return fail("Scene neuron identity/order mismatch.")
		var expected: String = "skeletons/" + reference.id + ".json"
		if reference.get("skeleton") != expected:
			return fail("Unsafe or inconsistent skeleton path.")
		if reference.get("source_units") != "nm" or reference.get("source_materialization") != 888 or reference.get("provider") != "banc_v888_full_swc":
			return fail("Unsupported skeleton source/version.")
		if not reference.get("geometry_sha256") is String or reference.geometry_sha256.length() != 64:
			return fail("Missing skeleton checksum.")
		var geometry := read_json(directory.path_join(expected), reference.geometry_sha256)
		if not error.is_empty():
			return {}
		if not validate_geometry(geometry, reference, lower, upper):
			return fail("Invalid skeleton coordinates/topology: " + expected)
		total_points += geometry.points.size()
		if total_points > MAX_POINTS:
			return fail("Scene exceeds viewer budget of 1,000,000 points.")
		geometries.append(geometry)
	var context := load_context(directory, scene)
	if not error.is_empty():
		return {}
	return {"scene": scene, "geometries": geometries, "context": context, "directory": directory}


func load_context(directory: String, scene: Dictionary) -> Array:
	var references: Variant = scene.get("context", [])
	if not references is Array or (scene.schema_version == 1 and not references.is_empty()) or (scene.schema_version == 2 and references.size() != 2):
		fail("Invalid context for scene schema version.")
		return []
	var outlines: Array = []
	for i in references.size():
		var ref: Variant = references[i]
		var id := str(i + 3)
		var expected := "context/" + id + ".json"
		var label := "BANC_brain_neuropil" if i == 0 else "BANC_vnc_neuropil"
		if not ref is Dictionary or ref.get("region_id") != id or ref.get("label") != label or ref.get("geometry") != expected:
			fail("Unsafe or inconsistent outline reference.")
			return []
		if ref.get("provider") != "banc_public_region_outlines" or ref.get("source_units") != "nm" or not ref.has("source_materialization") or ref.source_materialization != null:
			fail("Outline must retain its independent, unversioned source provenance.")
			return []
		if not ref.get("sources") is Array or ref.sources.size() != 4:
			fail("Missing outline source receipts.")
			return []
		for source in ref.sources:
			if not source is Dictionary or not source.get("url") is String or not source.get("sha256") is String or source.sha256.length() != 64 or not integer(source.get("bytes"), 1):
				fail("Invalid outline source receipt.")
				return []
		if not ref.get("geometry_sha256") is String or ref.geometry_sha256.length() != 64:
			fail("Missing outline checksum.")
			return []
		var geometry := read_json(directory.path_join(expected), ref.geometry_sha256)
		if not error.is_empty():
			return []
		if not validate_context(geometry, ref):
			fail("Invalid outline geometry, indices or bounds.")
			return []
		outlines.append(geometry)
	return outlines


func validate_context(geometry: Dictionary, ref: Dictionary) -> bool:
	if geometry.get("artifact_type") != "neuropil_outline" or geometry.get("region_id") != ref.region_id or geometry.get("units") != "godot_unit":
		return false
	if not integer(ref.get("vertex_count"), 3) or ref.vertex_count > 100000 or not integer(ref.get("triangle_count"), 1) or ref.triangle_count > 200000:
		return false
	if not geometry.get("points") is Array or geometry.points.size() != ref.vertex_count or not geometry.get("triangles") is Array or geometry.triangles.size() != ref.triangle_count:
		return false
	if not vector(ref.get("bounds_min")) or not vector(ref.get("bounds_max")):
		return false
	var lower := Vector3(INF, INF, INF)
	var upper := -lower
	for value in geometry.points:
		if not vector(value):
			return false
		lower = lower.min(point(value))
		upper = upper.max(point(value))
	if not lower.is_equal_approx(point(ref.bounds_min)) or not upper.is_equal_approx(point(ref.bounds_max)):
		return false
	for face in geometry.triangles:
		if not face is Array or face.size() != 3:
			return false
		for index in face:
			if not integer(index) or index >= ref.vertex_count:
				return false
		if face[0] == face[1] or face[1] == face[2] or face[0] == face[2]:
			return false
	return true


func validate_graph(graph: Dictionary) -> bool:
	var run: Variant = graph.get("manifest")
	if not run is Dictionary or run.get("dataset") != "BANC" or run.get("materialization") != 888:
		return false
	if run.get("connectivity_version") not in ["v2", "v3"] or run.get("path_mode") not in ["hops", "normalized"]:
		return false
	var definition := "1 per directed edge" if run.path_mode == "hops" else "-log(max(count/post_count, epsilon))"
	if run.get("cost_definition") != definition or not integer(run.get("min_synapse_count"), 1):
		return false
	if not number(run.get("epsilon")) or run.epsilon <= 0 or run.epsilon > 1:
		return false
	if not graph.get("neurons") is Array or graph.neurons.is_empty() or not graph.get("edges") is Array:
		return false
	if graph.get("hop_count") != graph.neurons.size() - 1 or graph.edges.size() != graph.hop_count:
		return false
	var ids: Array = []
	for neuron in graph.neurons:
		if not neuron is Dictionary or not decimal_id(neuron.get("id")) or neuron.id in ids:
			return false
		ids.append(neuron.id)
	if run.get("source_ids") != [ids[0]] or run.get("target_ids") != [ids[-1]] or not run.get("excluded_neurons") is Array:
		return false
	for excluded in run.excluded_neurons:
		if excluded in ids:
			return false
	var total := 0.0
	for i in graph.edges.size():
		var edge: Variant = graph.edges[i]
		if not edge is Dictionary or edge.get("pre") != ids[i] or edge.get("post") != ids[i + 1]:
			return false
		for key in ["count", "pre_count", "post_count"]:
			if not integer(edge.get(key), 1):
				return false
		if edge.count < run.min_synapse_count or edge.count > min(edge.pre_count, edge.post_count):
			return false
		var ratio: float = edge.count / edge.post_count
		var cost: float = 1.0 if run.path_mode == "hops" else -log(max(ratio, run.epsilon))
		for key in ["norm", "normalized_input", "cost"]:
			if not number(edge.get(key)):
				return false
		if abs(edge.normalized_input - ratio) > 1e-12 or abs(edge.norm - ratio) > 5.1e-5 or abs(edge.cost - cost) > 1e-9:
			return false
		total += cost
	return number(graph.get("total_cost")) and abs(graph.total_cost - total) < 1e-8


func validate_geometry(geometry: Dictionary, reference: Dictionary, lower: Vector3, upper: Vector3) -> bool:
	if geometry.get("neuron_id") != reference.id or geometry.get("units") != "godot_unit":
		return false
	if not integer(reference.get("node_count"), 1) or reference.node_count > MAX_POINTS or not integer(reference.get("root_count"), 1):
		return false
	var count: int = int(reference.node_count)
	for key in ["points", "parents", "node_ids", "labels", "radii"]:
		if not geometry.get(key) is Array or geometry[key].size() != count:
			return false
	var ids := {}
	var roots := 0
	var parents := PackedInt32Array()
	parents.resize(count)
	for i in count:
		var node_id: Variant = geometry.node_ids[i]
		if not decimal_id(node_id, true) or ids.has(node_id) or not vector(geometry.points[i]):
			return false
		ids[node_id] = true
		if not integer(geometry.labels[i]) or not number(geometry.radii[i]) or geometry.radii[i] < 0:
			return false
		var position := point(geometry.points[i])
		for axis in 3:
			if position[axis] < lower[axis] - 0.0001 or position[axis] > upper[axis] + 0.0001:
				return false
		var parent: Variant = geometry.parents[i]
		if parent == null:
			parents[i] = -1
			roots += 1
		elif not integer(parent) or parent >= count or parent == i:
			return false
		else:
			parents[i] = int(parent)
	if roots != reference.root_count:
		return false
	# Iterative forest validation handles long chains without recursion overflow.
	var states := PackedByteArray()
	states.resize(count)
	for start in count:
		var cursor := start
		var trail := PackedInt32Array()
		while cursor != -1 and states[cursor] == 0:
			states[cursor] = 1
			trail.append(cursor)
			cursor = parents[cursor]
		if cursor != -1 and states[cursor] == 1:
			return false
		for index in trail:
			states[index] = 2
	return true
