extends Control

const Loader = preload("res://scripts/bundle_loader.gd")
const OrbitCamera = preload("res://scripts/orbit_camera.gd")
const ExplorerPanel = preload("res://scripts/explorer_panel.gd")
const EmPanel = preload("res://scripts/em_panel.gd")
const InterventionPanel = preload("res://scripts/intervention_panel.gd")
const COLORS = [Color("67e8f9"), Color("fbbf65"), Color("b4a0ff"), Color("7ee5a2"), Color("fb90b6")]
var loader := Loader.new()
var bundle: Dictionary = {}
var meshes: Array[MeshInstance3D] = []
var segments: Array[PackedVector3Array] = []
var isolated_points: Array[PackedVector3Array] = []
var selected := 0
var playing := false
var elapsed := 0.0
var seconds_per_neuron := 1.4
var drag_button := 0
var drag_distance := 0.0
var camera: Camera3D
var world: Node3D
var viewport: SubViewport
var view_container: SubViewportContainer
var summary: Label
var details: Label
var connection: Label
var status: Label
var stage: Label
var legend: Label
var items: ItemList
var play_button: Button
var previous_button: Button
var next_button: Button
var reset_button: Button
var show_all: CheckBox
var dialog: FileDialog
var last_error := ""
var explorer: VBoxContainer
var tabs: TabContainer
var context_meshes: Array[MeshInstance3D] = []
var context_toggle: CheckBox
var context_fit: Button
var context_label: Label
var em_panel: VBoxContainer
var point_marker: MeshInstance3D
var selected_node := 0
var intervention: VBoxContainer


func _ready() -> void:
	get_window().min_size = Vector2i(1100, 720)
	build_ui()
	var directory := ""
	var api_url := ""
	var args := OS.get_cmdline_user_args()
	for i in args.size() - 1:
		if args[i] == "--scene-dir":
			directory = args[i + 1]
		elif args[i] == "--api-url":
			api_url = args[i + 1]
	if directory.is_empty():
		var demo := ProjectSettings.globalize_path("res://../generated/scenes/phase3-demo")
		if FileAccess.file_exists(demo.path_join("manifest.json")):
			directory = demo
	if not directory.is_empty():
		load_directory(directory)
	else:
		status.text = "Open a scene's manifest.json to begin. Build a bundle with: banc-explorer scene export."
		update_controls()
	if not bundle.is_empty():
		explorer.seed_from_scene(bundle.scene.path_result)
	if not api_url.is_empty():
		tabs.current_tab = 0
		explorer.url_input.text = api_url
		explorer.connect_api()
	for i in args.size() - 1:
		if args[i] == "--em-dir":
			em_panel.load_directory(args[i + 1])
			tabs.current_tab = 2


func make_label(value: String, font_size := 16, color := Color("cbd5e1")) -> Label:
	var label := Label.new()
	label.text = value
	label.add_theme_font_size_override("font_size", font_size)
	label.add_theme_color_override("font_color", color)
	label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	return label


func make_button(value: String, callback: Callable) -> Button:
	var button := Button.new()
	button.text = value
	button.custom_minimum_size.y = 38
	button.pressed.connect(callback)
	return button


func build_ui() -> void:
	theme = Theme.new()
	theme.default_font_size = 16
	for state_name in ["normal", "hover", "pressed", "focus", "disabled"]:
		var style := StyleBoxFlat.new()
		style.bg_color = Color("26374b") if state_name == "hover" else Color("152236")
		style.set_border_width_all(1)
		style.border_color = Color("67e8f9") if state_name == "focus" else Color("2c415b")
		style.set_corner_radius_all(6)
		style.content_margin_left = 14
		style.content_margin_right = 14
		theme.set_stylebox(state_name, "Button", style)
	var margin := MarginContainer.new()
	margin.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	for edge in ["left", "right", "top", "bottom"]:
		margin.add_theme_constant_override("margin_" + edge, 22)
	add_child(margin)
	var column := VBoxContainer.new()
	column.add_theme_constant_override("separation", 12)
	margin.add_child(column)
	var header := HBoxContainer.new()
	column.add_child(header)
	var titles := VBoxContainer.new()
	titles.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	header.add_child(titles)
	titles.add_child(make_label("BANC  /  SENSORIMOTOR EXPLORER", 27, Color("edf6ff")))
	titles.add_child(make_label("Reconstructed morphology  ·  Directed structural paths  ·  Local v888 snapshot", 15, Color("8ca6bf")))
	header.add_child(make_button("Open scene…", func(): dialog.popup_centered_ratio(0.75)))
	header.add_child(make_button("Fit path", fit_path))
	var body := HBoxContainer.new()
	body.size_flags_vertical = Control.SIZE_EXPAND_FILL
	body.add_theme_constant_override("separation", 22)
	column.add_child(body)
	var view_column := VBoxContainer.new()
	view_column.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	body.add_child(view_column)
	summary = make_label("No scene loaded", 17, Color("edf6ff"))
	view_column.add_child(summary)
	view_container = SubViewportContainer.new()
	view_container.size_flags_vertical = Control.SIZE_EXPAND_FILL
	view_container.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	view_container.stretch = true
	view_container.mouse_filter = Control.MOUSE_FILTER_STOP
	view_container.focus_mode = Control.FOCUS_ALL
	view_container.gui_input.connect(view_input)
	view_column.add_child(view_container)
	viewport = SubViewport.new()
	viewport.own_world_3d = true
	viewport.render_target_update_mode = SubViewport.UPDATE_ALWAYS
	viewport.msaa_3d = Viewport.MSAA_4X
	view_container.add_child(viewport)
	world = Node3D.new()
	viewport.add_child(world)
	point_marker = MeshInstance3D.new()
	var marker_mesh := SphereMesh.new()
	marker_mesh.radius = 0.12
	marker_mesh.height = 0.24
	point_marker.mesh = marker_mesh
	var marker_material := StandardMaterial3D.new()
	marker_material.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	marker_material.albedo_color = Color("ffffff")
	point_marker.material_override = marker_material
	point_marker.visible = false
	world.add_child(point_marker)
	camera = OrbitCamera.new()
	world.add_child(camera)
	camera.current = true
	view_container.resized.connect(func(): camera.resize_view(view_container.size))
	camera.resize_view(Vector2(960, 600))
	legend = make_label("Each color is one neuron. Select a line or a neuron in the list.", 14, Color("8ca6bf"))
	view_column.add_child(legend)
	var context_row := HBoxContainer.new()
	view_column.add_child(context_row)
	context_toggle = CheckBox.new()
	context_toggle.text = "Neuropil outlines"
	context_toggle.button_pressed = true
	context_toggle.toggled.connect(func(value: bool):
		for mesh in context_meshes:
			mesh.visible = value)
	context_row.add_child(context_toggle)
	context_fit = make_button("Fit context", fit_context)
	context_row.add_child(context_fit)
	context_label = make_label("Optional brain / VNC spatial context", 12, Color("8ca6bf"))
	context_label.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	context_row.add_child(context_label)
	context_toggle.disabled = true
	context_fit.disabled = true
	view_column.add_child(make_label("Drag: orbit  ·  Right drag: pan  ·  Wheel: zoom  ·  Click: select  ·  F: fit", 14, Color("8ca6bf")))
	tabs = TabContainer.new()
	tabs.custom_minimum_size.x = 400
	body.add_child(tabs)
	var explore_scroll := ScrollContainer.new()
	explore_scroll.name = "Explore"
	explore_scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	tabs.add_child(explore_scroll)
	explorer = ExplorerPanel.new()
	explorer.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	explore_scroll.add_child(explorer)
	explorer.scene_selected.connect(func(directory: String):
		if not load_directory(directory):
			explorer.message.text = "Scene validation failed: " + last_error)
	var scroll := ScrollContainer.new()
	scroll.name = "Inspect"
	scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	tabs.add_child(scroll)
	tabs.current_tab = 1
	var side := VBoxContainer.new()
	side.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	side.add_theme_constant_override("separation", 10)
	scroll.add_child(side)
	side.add_child(make_label("PATH NEURONS", 14, Color("67e8f9")))
	items = ItemList.new()
	items.custom_minimum_size = Vector2(365, 115)
	items.auto_height = false
	items.add_theme_constant_override("v_separation", 10)
	items.item_selected.connect(func(index: int): pause(); select_neuron(index))
	side.add_child(items)
	show_all = CheckBox.new()
	show_all.text = "Equal brightness for all neurons"
	show_all.toggled.connect(func(_value: bool): refresh_colors())
	side.add_child(show_all)
	side.add_child(HSeparator.new())
	side.add_child(make_label("SELECTED NEURON", 14, Color("67e8f9")))
	details = make_label("Select a neuron to inspect its annotations.", 14)
	side.add_child(details)
	side.add_child(HSeparator.new())
	side.add_child(make_label("INCOMING CONNECTION", 14, Color("67e8f9")))
	connection = make_label("—", 14)
	side.add_child(connection)
	var em_scroll := ScrollContainer.new()
	em_scroll.name = "EM"
	em_scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	tabs.add_child(em_scroll)
	em_panel = EmPanel.new()
	em_panel.explorer = explorer
	em_panel.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	em_scroll.add_child(em_panel)
	var intervention_scroll := ScrollContainer.new()
	intervention_scroll.name = "Intervene"
	intervention_scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	tabs.add_child(intervention_scroll)
	intervention = InterventionPanel.new()
	intervention.viewer = self
	intervention.explorer = explorer
	intervention.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	intervention.scene_selected.connect(func(directory: String):
		if not load_directory(directory):
			intervention.message.text = "Scene rejected: " + loader.error)
	intervention_scroll.add_child(intervention)
	column.add_child(HSeparator.new())
	var playback := HBoxContainer.new()
	playback.add_theme_constant_override("separation", 12)
	column.add_child(playback)
	play_button = make_button("Play", toggle_playback)
	playback.add_child(play_button)
	previous_button = make_button("← Previous", func(): step(-1))
	playback.add_child(previous_button)
	next_button = make_button("Next →", func(): step(1))
	playback.add_child(next_button)
	reset_button = make_button("Reset", reset_playback)
	playback.add_child(reset_button)
	stage = make_label("Illustrative path activation", 16, Color("edf6ff"))
	stage.autowrap_mode = TextServer.AUTOWRAP_OFF
	stage.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	playback.add_child(stage)
	var speed_label := make_label("Seconds / neuron", 14)
	speed_label.autowrap_mode = TextServer.AUTOWRAP_OFF
	playback.add_child(speed_label)
	var speed := SpinBox.new()
	speed.min_value = 0.4
	speed.max_value = 5.0
	speed.step = 0.2
	speed.value = seconds_per_neuron
	speed.value_changed.connect(func(value: float): seconds_per_neuron = value)
	playback.add_child(speed)
	column.add_child(make_label("Graph-theoretic paths, not established information-flow routes. Normalized input is not a transmission probability. Playback timing is illustrative.", 13, Color("c8ad7d")))
	status = make_label("", 13, Color("8ca6bf"))
	column.add_child(status)
	dialog = FileDialog.new()
	dialog.access = FileDialog.ACCESS_FILESYSTEM
	dialog.file_mode = FileDialog.FILE_MODE_OPEN_FILE
	dialog.filters = PackedStringArray(["*.json ; Scene manifest / path JSON"])
	dialog.title = "Open a Python-exported scene's manifest.json"
	dialog.file_selected.connect(func(path: String): load_directory(path.get_base_dir()))
	add_child(dialog)


func load_directory(directory: String) -> bool:
	var loaded := loader.load_bundle(directory)
	if loaded.is_empty():
		last_error = loader.error
		status.text = "Cannot load scene: " + last_error
		status.add_theme_color_override("font_color", Color("ffada5"))
		return false
	# Only replace a displayed scene after the entire new bundle passes validation.
	pause()
	for mesh in meshes:
		mesh.free()
	meshes.clear()
	segments.clear()
	isolated_points.clear()
	items.clear()
	bundle = loaded
	last_error = ""
	var branch_count := 0
	for i in bundle.geometries.size():
		var geometry: Dictionary = bundle.geometries[i]
		var vertices := PackedVector3Array()
		var has_child := {}
		for j in geometry.points.size():
			if geometry.parents[j] != null:
				has_child[int(geometry.parents[j])] = true
				vertices.append(loader.point(geometry.points[j]))
				vertices.append(loader.point(geometry.points[int(geometry.parents[j])]))
		var isolated := PackedVector3Array()
		for j in geometry.points.size():
			if geometry.parents[j] == null and not has_child.has(j):
				isolated.append(loader.point(geometry.points[j]))
		isolated_points.append(isolated)
		segments.append(vertices)
		branch_count += vertices.size() / 2
		var instance := MeshInstance3D.new()
		var mesh := ArrayMesh.new()
		if not vertices.is_empty():
			var arrays := []
			arrays.resize(Mesh.ARRAY_MAX)
			arrays[Mesh.ARRAY_VERTEX] = vertices
			mesh.add_surface_from_arrays(Mesh.PRIMITIVE_LINES, arrays)
		if not isolated.is_empty():
			var arrays := []
			arrays.resize(Mesh.ARRAY_MAX)
			arrays[Mesh.ARRAY_VERTEX] = isolated
			mesh.add_surface_from_arrays(Mesh.PRIMITIVE_POINTS, arrays)
		instance.mesh = mesh
		var material := StandardMaterial3D.new()
		material.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
		# Point-size mode changes line rendering on Compatibility; only enable it
		# for a skeleton made entirely of isolated roots.
		material.use_point_size = vertices.is_empty()
		material.point_size = 5.0
		instance.material_override = material
		instance.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
		world.add_child(instance)
		meshes.append(instance)
		var neuron: Dictionary = bundle.scene.path_result.neurons[i]
		items.add_item("%02d   %s" % [i + 1, annotation(neuron, "cell_type")])
		items.set_item_custom_fg_color(i, neuron_color(i))
		items.set_item_tooltip(i, neuron.id)
	var graph: Dictionary = bundle.scene.path_result
	var run: Dictionary = graph.manifest
	var mode := "Minimum-hop path" if run.path_mode == "hops" else "Normalized-strength path"
	summary.text = "BANC v888  /  %s  /  %s\n%d neurons · %d hops · count ≥ %d · total cost %.4f" % [run.connectivity_version, mode, meshes.size(), graph.hop_count, run.min_synapse_count, graph.total_cost]
	legend.text = "%s → %s  |  %s branches\n1 world unit = %.2f µm · Y-up display frame · fixed-width skeleton lines" % [annotation(graph.neurons[0], "cell_type"), annotation(graph.neurons[-1], "cell_type"), branch_count, bundle.scene.coordinate_transform.nm_per_world_unit / 1000.0]
	build_context()
	fit_path()
	status.text = "Verified scene: " + directory.replace("\\", "/")
	status.add_theme_color_override("font_color", Color("8ca6bf"))
	dialog.current_dir = directory
	select_neuron(0)
	return true


func fit_path() -> void:
	if not bundle.is_empty():
		camera.fit_bounds(loader.point(bundle.scene.bounds_min), loader.point(bundle.scene.bounds_max))


func fit_context() -> void:
	if bundle.is_empty() or context_meshes.is_empty():
		return
	context_toggle.button_pressed = true
	var lower := loader.point(bundle.scene.bounds_min)
	var upper := loader.point(bundle.scene.bounds_max)
	for ref in bundle.scene.context:
		lower = lower.min(loader.point(ref.bounds_min))
		upper = upper.max(loader.point(ref.bounds_max))
	camera.fit_bounds(lower, upper)


func build_context() -> void:
	for instance in context_meshes:
		instance.free()
	context_meshes.clear()
	for i in bundle.context.size():
		var geometry: Dictionary = bundle.context[i]
		var vertices := PackedVector3Array()
		var indices := PackedInt32Array()
		for value in geometry.points:
			vertices.append(loader.point(value))
		for face in geometry.triangles:
			for index in face:
				indices.append(int(index))
		var arrays := []
		arrays.resize(Mesh.ARRAY_MAX)
		arrays[Mesh.ARRAY_VERTEX] = vertices
		arrays[Mesh.ARRAY_INDEX] = indices
		var mesh := ArrayMesh.new()
		mesh.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, arrays)
		var material := StandardMaterial3D.new()
		material.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
		material.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
		material.cull_mode = BaseMaterial3D.CULL_DISABLED
		material.albedo_color = Color(0.35, 0.60, 0.75, 0.08) if i == 0 else Color(0.50, 0.60, 0.72, 0.08)
		var instance := MeshInstance3D.new()
		instance.mesh = mesh
		instance.material_override = material
		instance.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
		instance.visible = context_toggle.button_pressed
		world.add_child(instance)
		context_meshes.append(instance)
	context_toggle.disabled = context_meshes.is_empty()
	context_fit.disabled = context_meshes.is_empty()
	context_label.text = "Brain + VNC neuropil\nPublic context · independent of v888" if not context_meshes.is_empty() else "No outlines in this bundle\nExport with --include-context"


func annotation(neuron: Dictionary, key: String) -> String:
	var value: Variant = neuron.get(key)
	return "Unannotated" if value == null or str(value).is_empty() else str(value)


func select_neuron(index: int) -> void:
	if bundle.is_empty():
		return
	selected = clampi(index, 0, meshes.size() - 1)
	items.select(selected)
	items.ensure_current_is_visible()
	var neuron: Dictionary = bundle.scene.path_result.neurons[selected]
	var reference: Dictionary = bundle.scene.neurons[selected]
	intervention.set_selected(neuron)
	select_point(int(bundle.geometries[selected].points.size() / 2))
	details.text = "%s\nID  %s\nClass  %s\nRegion  %s · %s\nSensory part  %s\nEffector part  %s\nProofread  %s · %d SWC points · %d roots" % [annotation(neuron, "cell_type"), neuron.id, annotation(neuron, "super_class"), annotation(neuron, "region"), annotation(neuron, "side"), annotation(neuron, "body_part_sensory"), annotation(neuron, "body_part_effector"), annotation(neuron, "proofread"), reference.node_count, reference.root_count]
	if selected == 0:
		connection.text = "Source neuron. No incoming path edge."
	else:
		var edge: Dictionary = bundle.scene.path_result.edges[selected - 1]
		connection.text = "%s →\n%s\n%d synapses / %d target inputs\nNormalized input  %.8f\nSource table norm  %.6f\nEdge cost  %.6f" % [edge.pre, edge.post, edge.count, edge.post_count, edge.normalized_input, edge.norm, edge.cost]
	stage.text = "Illustrative path activation\nNeuron %d / %d · graph step %d / %d" % [selected + 1, meshes.size(), selected, meshes.size() - 1]
	refresh_colors()
	update_controls()


func select_point(index: int) -> void:
	if bundle.is_empty():
		return
	var geometry: Dictionary = bundle.geometries[selected]
	selected_node = clampi(index, 0, geometry.points.size() - 1)
	var position := loader.point(geometry.points[selected_node])
	point_marker.position = position
	point_marker.visible = true
	var transform_data: Dictionary = bundle.scene.coordinate_transform
	var nm: Vector3 = loader.point(transform_data.origin_nm) + Vector3(position.x, position.z, -position.y) * transform_data.nm_per_world_unit
	em_panel.set_point({"neuron_id": geometry.neuron_id, "swc_node_id": geometry.node_ids[selected_node], "swc_sha256": bundle.scene.neurons[selected].source.sha256}, nm)


func nearest_node(screen_position: Vector2) -> int:
	var closest := INF
	var index := 0
	for i in bundle.geometries[selected].points.size():
		var distance := screen_position.distance_squared_to(camera.unproject_position(loader.point(bundle.geometries[selected].points[i])))
		if distance < closest:
			closest = distance
			index = i
	return index


func refresh_colors() -> void:
	for i in meshes.size():
		var color := neuron_color(i)
		if not show_all.button_pressed and i != selected:
			color = color.darkened(0.62)
		meshes[i].material_override.albedo_color = color


func neuron_color(index: int) -> Color:
	return COLORS[index] if index < COLORS.size() else Color.from_hsv(fmod(index * 0.618034, 1.0), 0.5, 0.95)


func update_controls() -> void:
	play_button.disabled = meshes.size() < 2
	previous_button.disabled = meshes.is_empty() or selected == 0
	next_button.disabled = meshes.is_empty() or selected == meshes.size() - 1
	reset_button.disabled = meshes.is_empty()
	play_button.text = "Pause" if playing else "Play"


func pause() -> void:
	playing = false
	elapsed = 0.0
	update_controls()


func toggle_playback() -> void:
	if meshes.size() < 2:
		return
	if playing:
		pause()
	else:
		if selected == meshes.size() - 1:
			select_neuron(0)
		playing = true
		elapsed = 0.0
		update_controls()


func reset_playback() -> void:
	pause()
	select_neuron(0)


func step(direction: int) -> void:
	pause()
	select_neuron(selected + direction)


func _process(delta: float) -> void:
	advance_playback(delta)


func advance_playback(delta: float) -> void:
	if not playing:
		return
	elapsed += delta
	while elapsed >= seconds_per_neuron and playing:
		elapsed -= seconds_per_neuron
		if selected < meshes.size() - 1:
			select_neuron(selected + 1)
		else:
			pause()


func view_input(event: InputEvent) -> void:
	if event is InputEventMouseButton:
		if event.pressed:
			view_container.grab_focus()
		if event.pressed and event.button_index == MOUSE_BUTTON_WHEEL_UP:
			camera.zoom(-0.12)
		elif event.pressed and event.button_index == MOUSE_BUTTON_WHEEL_DOWN:
			camera.zoom(0.12)
		elif event.button_index in [MOUSE_BUTTON_LEFT, MOUSE_BUTTON_RIGHT, MOUSE_BUTTON_MIDDLE]:
			if event.pressed:
				drag_button = event.button_index
				drag_distance = 0.0
			else:
				if drag_button == MOUSE_BUTTON_LEFT and drag_distance < 5.0:
					var index := pick_neuron(event.position)
					if index >= 0:
						pause()
						select_neuron(index)
						select_point(nearest_node(event.position))
						tabs.current_tab = 1
				drag_button = 0
	elif event is InputEventMouseMotion and drag_button != 0:
		# Releasing outside the viewport must not leave a stuck drag.
		var mask := MOUSE_BUTTON_MASK_LEFT if drag_button == MOUSE_BUTTON_LEFT else (MOUSE_BUTTON_MASK_RIGHT if drag_button == MOUSE_BUTTON_RIGHT else MOUSE_BUTTON_MASK_MIDDLE)
		if not event.button_mask & mask:
			drag_button = 0
			return
		drag_distance += event.relative.length()
		if drag_button == MOUSE_BUTTON_LEFT:
			camera.orbit(event.relative)
		else:
			camera.pan(event.relative)


func pick_neuron(screen_position: Vector2) -> int:
	var best := 9.0 * 9.0
	var chosen := -1
	for i in segments.size():
		for position in isolated_points[i]:
			var distance := screen_position.distance_squared_to(camera.unproject_position(position))
			if distance < best:
				best = distance
				chosen = i
		var vertices: PackedVector3Array = segments[i]
		for j in range(0, vertices.size(), 2):
			var a := camera.unproject_position(vertices[j])
			var b := camera.unproject_position(vertices[j + 1])
			var ab := b - a
			var t := clampf((screen_position - a).dot(ab) / maxf(ab.length_squared(), 0.00001), 0, 1)
			var distance := screen_position.distance_squared_to(a + ab * t)
			if distance < best:
				best = distance
				chosen = i
	return chosen


func _unhandled_key_input(event: InputEvent) -> void:
	if event is InputEventKey and event.pressed and not event.echo and not dialog.visible:
		match event.keycode:
			KEY_F: camera.reset_view()
			KEY_SPACE: toggle_playback()
			KEY_LEFT: step(-1)
			KEY_RIGHT: step(1)
			KEY_HOME: reset_playback()
