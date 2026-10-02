extends SceneTree

const Loader = preload("res://scripts/bundle_loader.gd")


func _initialize() -> void:
	var args := OS.get_cmdline_user_args()
	if args.is_empty():
		printerr("Usage: --script res://tests/validate.gd -- <bundle-dir> [expected error]")
		quit(2)
		return
	var loader := Loader.new()
	var bundle: Dictionary = loader.load_bundle(args[0])
	var expected := "" if args.size() < 2 else args[1]
	if (expected.is_empty() and not bundle.is_empty()) or (not expected.is_empty() and bundle.is_empty() and expected in loader.error):
		print("GODOT_VALIDATE_OK: " + ("valid bundle" if expected.is_empty() else loader.error))
		quit(0)
	else:
		printerr("Unexpected loader result: " + loader.error)
		quit(1)
