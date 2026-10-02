extends SceneTree
## End-to-end HTTP test: UI search -> Python job -> two validated Godot scenes.

const Viewer = preload("res://scripts/viewer.gd")
var failures: Array[String] = []
var checks := 0


func check(value: bool, explanation: String) -> void:
	checks += 1
	if not value:
		failures.append(explanation)
		printerr("FAIL: " + explanation)


func _initialize() -> void:
	call_deferred("run")


func wait_until(condition: Callable, timeout_ms := 60000) -> bool:
	var deadline := Time.get_ticks_msec() + timeout_ms
	while not condition.call() and Time.get_ticks_msec() < deadline:
		await process_frame
	return condition.call()


func run() -> void:
	var args := OS.get_cmdline_user_args()
	var source_id := ""
	var target_id := ""
	var screenshot := ""
	for i in args.size() - 1:
		match args[i]:
			"--source-id": source_id = args[i + 1]
			"--target-id": target_id = args[i + 1]
			"--screenshot": screenshot = args[i + 1]
	var app := Viewer.new()
	app.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	root.add_child(app)
	var panel: VBoxContainer = app.explorer
	check(await wait_until(func(): return panel.connected, 15000), "Connect to BANC API: " + panel.connection_label.text)
	if not panel.connected:
		finish()
		return
	check(panel.server_offline and panel.downloads.disabled, "Offline server disables fetching")
	panel.queries.sensory.text = source_id
	panel.queries.motor.text = target_id
	panel.search("sensory")
	panel.search("motor")
	check(await wait_until(func(): return not panel.rows.sensory.is_empty() and not panel.rows.motor.is_empty(), 15000), "Search both endpoint classes")
	for kind in ["sensory", "motor"]:
		var expected: String = source_id if kind == "sensory" else target_id
		var index := -1
		for i in panel.rows[kind].size():
			if panel.rows[kind][i].id == expected:
				index = i + 1
		check(index > 0, "Exact endpoint ID from API: " + expected)
		if index <= 0:
			finish()
			return
		panel.choices[kind].select(index)
		panel.choices[kind].item_selected.emit(index)
	check(not panel.find_button.disabled, "Two explicit endpoint choices enable Find path")
	panel.mode.select(1)
	panel.compare.button_pressed = true
	panel.find_button.pressed.emit()
	check(panel.busy and panel.find_button.disabled and not panel.queries.sensory.editable, "Job keeps inputs stable while running")
	check(await wait_until(func(): return not panel.busy), "Job completes within test deadline")
	check(panel.latest_job.get("status") == "complete", "Python job succeeds: " + panel.message.text)
	if panel.latest_job.get("status") != "complete":
		finish()
		return
	check(panel.completed_scenes.has("hops") and panel.completed_scenes.has("normalized"), "Both modes returned")
	check(not app.bundle.is_empty(), "New scene passes Godot bundle validation")
	if app.bundle.is_empty():
		finish()
		return
	check(app.bundle.scene.path_result.neurons[0].id == source_id and app.bundle.scene.path_result.neurons[-1].id == target_id, "Rendered scene matches chosen endpoints without rounding")
	check(app.bundle.scene.path_result.manifest.path_mode == "normalized", "Initial display matches selected mode")
	panel.mode.select(0)
	panel.mode.item_selected.emit(0)
	check(app.bundle.scene.path_result.manifest.path_mode == "hops", "Mode switch loads minimum-hop scene")
	panel.mode.select(1)
	panel.mode.item_selected.emit(1)
	check(app.bundle.scene.path_result.manifest.path_mode == "normalized", "Switch back loads normalized-strength scene")
	check("cost definition" in panel.comparison.text, "Comparison labels distinct cost definitions")
	check(app.meshes.size() == panel.completed_scenes.normalized.neuron_ids.size(), "Geometry count follows computed route")
	if not screenshot.is_empty():
		check(DisplayServer.get_name() != "headless", "Screenshot uses real renderer")
		if DisplayServer.get_name() != "headless":
			app.show_all.button_pressed = true
			app.tabs.current_tab = 0
			await process_frame
			await process_frame
			await RenderingServer.frame_post_draw
			check(root.get_texture().get_image().save_png(screenshot) == OK, "Capture integrated explorer")
	var displayed: Dictionary = app.bundle
	panel.threshold.value += 1
	check(panel.completed_scenes.is_empty() and app.bundle == displayed, "Changed query invalidates mode results but retains current scene")
	panel.queries.sensory.text = "changed query"
	panel.queries.sensory.text_changed.emit("changed query")
	check(panel.chosen.sensory.is_empty() and panel.find_button.disabled, "Edited search clears stale selected ID")
	print("EXPLORER_SMOKE: %d checks; job %s" % [checks, panel.active_job])
	app.queue_free()
	await process_frame
	finish()


func finish() -> void:
	if failures.is_empty():
		print("GODOT_EXPLORER_OK")
		quit(0)
	else:
		printerr("GODOT_EXPLORER_FAILED: " + str(failures))
		quit(1)
