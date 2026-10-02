extends SceneTree

const Loader = preload("res://scripts/em_loader.gd")


func _initialize() -> void:
	var args := OS.get_cmdline_user_args()
	var loader := Loader.new()
	var result := loader.load_roi(args[0])
	var expected: String = args[1] if args.size() > 1 else ""
	if (expected.is_empty() and not result.is_empty()) or (not expected.is_empty() and result.is_empty() and expected in loader.error):
		print("GODOT_EM_OK")
		quit(0)
	else:
		printerr("Unexpected EM loader result: " + loader.error)
		quit(1)
