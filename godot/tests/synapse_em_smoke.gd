extends SceneTree
## Synthetic predicted-synapse stack: UI labeling, slider and failure recovery.

const EmPanel = preload("res://scripts/em_panel.gd")
var failures: Array[String] = []


func check(condition: bool, message: String) -> void:
	if not condition:
		failures.append(message)
		printerr(message)


func _initialize() -> void:
	call_deferred("run")


func run() -> void:
	var args := OS.get_cmdline_user_args()
	root.size = Vector2i(720, 900)
	var background := ColorRect.new()
	background.color = Color("17222f")
	background.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	root.add_child(background)
	var panel := EmPanel.new()
	panel.position = Vector2(28, 70)
	panel.size = Vector2(640, 800)
	root.add_child(panel)
	var label := Label.new()
	label.text = "SYNTHETIC TEST DATA · NOT A REAL BANC SYNAPSE"
	label.position = Vector2(28, 22)
	root.add_child(label)
	await process_frame
	check(panel.load_directory(args[0]), "Load predicted-synapse stack")
	if panel.bundle.is_empty():
		quit(1)
		return
	check(panel.image_label.text.contains("9007199254740993"), "Exact synapse ID in label")
	check(panel.image_label.text.contains("v3 / v888"), "Detector and snapshot in label")
	check(panel.message.text.contains("not independently verified"), "Scientific interpretation")
	check(panel.fetch_button.disabled, "No credential/API needed for saved stack")
	panel.slice_slider.value = 0
	check(panel.image_label.text.contains("XY 1 /"), "First slice via slider")
	panel.slice_slider.value = panel.slice_slider.max_value
	check(panel.image_view.texture == panel.bundle.images[-1], "Last slice via slider")
	check(not panel.load_directory(args[0] + "-missing"), "Reject missing stack")
	check(panel.image_label.text.contains("9007199254740993"), "Prior stack keeps its identity")
	check(panel.load_directory(args[0]), "Recover and reopen stack")
	if args.size() > 1:
		await process_frame
		await RenderingServer.frame_post_draw
		check(root.get_texture().get_image().save_png(args[1]) == OK, "Save screenshot")
	if failures.is_empty():
		print("GODOT_SYNAPSE_EM_OK")
	quit(0 if failures.is_empty() else 1)
