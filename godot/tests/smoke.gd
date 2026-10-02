extends SceneTree
## Run against a Python-generated bundle. No network or credential access.

const Viewer = preload("res://scripts/viewer.gd")
var failures: Array[String] = []
var checks := 0


func check(condition: bool, message: String) -> void:
	checks += 1
	if not condition:
		failures.append(message)
		printerr("FAIL: " + message)


func _initialize() -> void:
	call_deferred("run")


func run() -> void:
	var app := Viewer.new()
	app.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	root.add_child(app)
	app.set_process(false)
	await process_frame
	await process_frame
	check(not app.bundle.is_empty(), "Load scene: " + app.last_error)
	if app.bundle.is_empty():
		finish()
		return
	var size: int = app.meshes.size()
	check(app.view_container.size.y > 400, "3D viewport retains usable height")
	check(app.play_button.size.y < 80, "Playback controls do not expand from wrapped labels")
	check(size == app.bundle.scene.path_result.neurons.size(), "One mesh node per neuron")
	var total_branches := 0
	for i in size:
		var geometry: Dictionary = app.bundle.geometries[i]
		var expected: int = geometry.points.size() - int(app.bundle.scene.neurons[i].root_count)
		total_branches += expected
		check(app.segments[i].size() == expected * 2, "Preserve all parent-child branches")
		check(app.bundle.scene.path_result.neurons[i].id is String, "Exact string root ID")
		if expected > 0:
			check(app.meshes[i].mesh.surface_get_primitive_type(0) == Mesh.PRIMITIVE_LINES, "Batched line surface")
		else:
			check(app.meshes[i].mesh.surface_get_primitive_type(0) == Mesh.PRIMITIVE_POINTS, "Isolated SWC roots remain visible")
	app.reset_button.pressed.emit()
	check(app.selected == 0 and not app.playing, "Reset to source")
	check("No incoming" in app.connection.text, "Source has no fabricated connection")
	if size > 1:
		app.next_button.pressed.emit()
		check(app.selected == 1 and "synapses" in app.connection.text, "Next displays edge evidence")
		app.previous_button.pressed.emit()
		check(app.selected == 0, "Previous")
		app.play_button.pressed.emit()
		app.advance_playback(app.seconds_per_neuron + 0.001)
		check(app.selected == 1 and app.playing, "Timed illustrative activation advances")
		app.play_button.pressed.emit()
		app.advance_playback(100.0)
		check(app.selected == 1 and not app.playing, "Pause freezes activation")
		app.reset_playback()
		app.toggle_playback()
		app.advance_playback(app.seconds_per_neuron * (size + 1))
		check(app.selected == size - 1 and not app.playing, "Playback stops at target")
		app.toggle_playback()
		check(app.selected == 0 and app.playing, "Replay from target starts at source")
		app.pause()
		app.items.item_selected.emit(size - 1)
		check(app.selected == size - 1 and app.bundle.scene.path_result.neurons[-1].id in app.details.text, "List selection preserves full ID")
		check(app.meshes[-1].material_override.albedo_color != app.meshes[0].material_override.albedo_color, "Distinct neuron colors")
	var old_basis: Basis = app.camera.basis
	var press := InputEventMouseButton.new()
	press.button_index = MOUSE_BUTTON_LEFT
	press.pressed = true
	app.view_container.gui_input.emit(press)
	var motion := InputEventMouseMotion.new()
	motion.relative = Vector2(60, -25)
	motion.button_mask = MOUSE_BUTTON_MASK_LEFT
	app.view_container.gui_input.emit(motion)
	press.pressed = false
	app.view_container.gui_input.emit(press)
	check(not app.camera.basis.is_equal_approx(old_basis), "Viewport drag orbits camera")
	var old_center: Vector3 = app.camera.center
	press.button_index = MOUSE_BUTTON_RIGHT
	press.pressed = true
	app.view_container.gui_input.emit(press)
	motion.button_mask = MOUSE_BUTTON_MASK_RIGHT
	app.view_container.gui_input.emit(motion)
	press.pressed = false
	app.view_container.gui_input.emit(press)
	check(not app.camera.center.is_equal_approx(old_center), "Right drag pans camera")
	var old_size: float = app.camera.size
	press.button_index = MOUSE_BUTTON_WHEEL_UP
	press.pressed = true
	app.view_container.gui_input.emit(press)
	check(app.camera.size < old_size, "Wheel zoom")
	app.camera.reset_view()
	check(app.camera.center.is_equal_approx(app.camera.home_center), "Fit restores center")
	check(app.camera.basis.is_equal_approx(old_basis), "Fit restores orientation")
	if size == 1:
		check(app.play_button.disabled, "Zero-hop path cannot play transitions")
		if not app.isolated_points[0].is_empty():
			check(app.pick_neuron(app.camera.unproject_position(app.isolated_points[0][0])) == 0, "Isolated root is pickable")
	# Project actual geometry, click through the same input handler, verify selection.
	for i in size:
		if app.segments[i].is_empty():
			continue
		var screen: Vector2 = app.camera.unproject_position(app.segments[i][0])
		var picked: int = app.pick_neuron(screen)
		check(picked >= 0, "Skeleton screen-space picking")
		press.button_index = MOUSE_BUTTON_LEFT
		press.position = screen
		press.pressed = true
		app.view_container.gui_input.emit(press)
		press.pressed = false
		app.view_container.gui_input.emit(press)
		check(app.selected == picked, "Viewport click selects picked neuron")
		break
	var active_bundle: Dictionary = app.bundle
	check(not app.load_directory(app.bundle.directory.path_join("missing-bundle")), "Missing bundle rejected")
	check(app.bundle == active_bundle and app.meshes.size() == size, "Failed load preserves displayed scene")
	check("Missing file" in app.last_error, "Actionable missing-file error")
	check(app.load_directory(active_bundle.directory), "Reload valid bundle")
	app.items.item_selected.emit(mini(1, size - 1))
	app.show_all.button_pressed = true
	check(app.meshes[0].material_override.albedo_color.is_equal_approx(app.neuron_color(0)), "Equal-brightness toggle restores neuron color")
	app.show_all.button_pressed = false
	if size > 1:
		check(not app.meshes[0].material_override.albedo_color.is_equal_approx(app.neuron_color(0)), "Highlight toggle dims other neurons")
	var screenshot := ""
	var args := OS.get_cmdline_user_args()
	for i in args.size() - 1:
		if args[i] == "--screenshot":
			screenshot = args[i + 1]
	if not screenshot.is_empty():
		if DisplayServer.get_name() == "headless":
			check(false, "Screenshots require a display renderer")
		else:
			app.show_all.button_pressed = true
			await process_frame
			await process_frame
			await RenderingServer.frame_post_draw
			check(root.get_texture().get_image().save_png(screenshot) == OK, "Save rendered screenshot")
	print("SCENE_SMOKE: %d neurons, %d branches, %d checks" % [size, total_branches, checks])
	app.queue_free()
	await process_frame
	finish()


func finish() -> void:
	if failures.is_empty():
		print("GODOT_SMOKE_OK")
		quit(0)
	else:
		printerr("GODOT_SMOKE_FAILED: " + str(failures))
		quit(1)
