extends VBoxContainer
## The backend resolves the exact cached SWC ID; the UI never invents a synapse.

const EmLoader = preload("res://scripts/em_loader.gd")
var explorer: VBoxContainer
var selected_point: Dictionary = {}
var submitted_point: Dictionary = {}
var bundle: Dictionary = {}
var busy := false
var job := ""
var api_url := ""
var point_label: Label
var message: Label
var image_label: Label
var image_view: TextureRect
var fetch_button: Button
var downloads: CheckBox
var slice_slider: HSlider
var http: HTTPRequest
var timer: Timer
var dialog: FileDialog


func text_label(value: String) -> Label:
	var label := Label.new()
	label.text = value
	label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	label.add_theme_font_size_override("font_size", 14)
	add_child(label)
	return label


func _ready() -> void:
	add_theme_constant_override("separation", 6)
	text_label("EM  /  POINT CONTEXT")
	point_label = text_label("Select a neuron or click a skeleton point.")
	text_label("Inspect point uses a morphology node.\nOpen stack also accepts predicted synapses.")
	downloads = CheckBox.new()
	downloads.text = "Fetch missing EM ranges"
	downloads.tooltip_text = "At most 32 MB per job; 256 × 256 × 32 voxels at 8 × 8 × 45 nm. No whole shard download."
	add_child(downloads)
	var actions := HBoxContainer.new()
	add_child(actions)
	fetch_button = Button.new()
	fetch_button.text = "Inspect point"
	fetch_button.pressed.connect(fetch_point)
	actions.add_child(fetch_button)
	var open_button := Button.new()
	open_button.text = "Open stack…"
	open_button.pressed.connect(func(): dialog.popup_centered_ratio(0.75))
	actions.add_child(open_button)
	message = text_label("Connect in Explore with the API and EM extras to fetch. Saved stacks open offline.")
	image_view = TextureRect.new()
	image_view.custom_minimum_size = Vector2(256, 256)
	image_view.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
	image_view.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_CENTERED
	image_view.texture_filter = CanvasItem.TEXTURE_FILTER_NEAREST
	add_child(image_view)
	slice_slider = HSlider.new()
	slice_slider.step = 1
	slice_slider.value_changed.connect(show_slice)
	add_child(slice_slider)
	image_label = text_label("No image stack loaded.")
	http = HTTPRequest.new()
	http.timeout = 20
	http.body_size_limit = 1000000
	http.use_threads = true
	http.request_completed.connect(response)
	add_child(http)
	timer = Timer.new()
	timer.one_shot = true
	timer.wait_time = 0.5
	timer.timeout.connect(func(): send("/em/" + job))
	add_child(timer)
	dialog = FileDialog.new()
	dialog.access = FileDialog.ACCESS_FILESYSTEM
	dialog.file_mode = FileDialog.FILE_MODE_OPEN_FILE
	dialog.filters = PackedStringArray(["roi.json ; EM stack manifest"])
	dialog.file_selected.connect(func(path: String): load_directory(path.get_base_dir()))
	add_child(dialog)
	update_controls()


func _process(_delta: float) -> void:
	update_controls()


func set_point(point: Dictionary, center_nm: Vector3) -> void:
	selected_point = point
	point_label.text = "Neuron %s · SWC node %s\nBANC nm  %.1f, %.1f, %.1f" % [point.neuron_id, point.swc_node_id, center_nm.x, center_nm.y, center_nm.z]
	# Keep the prior image labeled with its own point until a replacement validates.


func update_controls() -> void:
	var online: bool = explorer != null and explorer.connected
	fetch_button.disabled = busy or selected_point.is_empty() or not online or not explorer.em_available
	downloads.disabled = busy or not online or explorer.server_offline
	if online and explorer.server_offline:
		downloads.button_pressed = false
	slice_slider.editable = not bundle.is_empty()


func fetch_point() -> void:
	if fetch_button.disabled:
		return
	submitted_point = selected_point.duplicate(true)
	var payload := submitted_point.duplicate(true)
	payload.allow_downloads = downloads.button_pressed
	payload.size_voxels = [256, 256, 32]
	payload.mip = 0
	api_url = explorer.base_url
	busy = true
	job = ""
	message.text = "Preparing image context (maximum 32 MB transfer)…"
	send("/em", payload)


func send(path: String, payload: Variant = null) -> void:
	var result := http.request(api_url + path, PackedStringArray(["Content-Type: application/json"]), HTTPClient.METHOD_GET if payload == null else HTTPClient.METHOD_POST, "" if payload == null else JSON.stringify(payload))
	if result != OK:
		busy = false
		message.text = "Could not start EM request. Reconnect in Explore."


func response(result: int, code: int, _headers: PackedStringArray, body: PackedByteArray) -> void:
	var data: Dictionary = explorer.decode(result, code, body)
	if data.has("error"):
		busy = false
		message.text = data.error
		return
	if not data.get("id") is String or data.get("kind") != "em":
		busy = false
		message.text = "Invalid EM job response."
		return
	job = data.id
	message.text = str(data.get("message", "Reading image context…"))
	if data.get("status") == "complete":
		busy = false
		if not data.get("results") is Dictionary or not data.results.get("roi_directory") is String:
			message.text = "Missing EM output location."
			return
		load_directory(data.results.roi_directory, submitted_point)
	elif data.get("status") == "error":
		busy = false
	else:
		timer.start()


func load_directory(directory: String, expected: Dictionary = {}) -> bool:
	var loader := EmLoader.new()
	var loaded := loader.load_roi(directory)
	if loaded.is_empty():
		message.text = loader.error
		return false
	if not expected.is_empty() and (loaded.manifest.point.get("kind") != "swc_node" or loaded.manifest.point.get("neuron_id") != expected.neuron_id or loaded.manifest.point.get("swc_node_id") != expected.swc_node_id or loaded.manifest.point.skeleton_source.sha256 != expected.swc_sha256):
		message.text = "EM result does not match the submitted SWC point."
		return false
	bundle = loaded
	slice_slider.max_value = bundle.images.size() - 1
	slice_slider.value = bundle.images.size() / 2
	show_slice(slice_slider.value)
	message.text = "Image checksums checked · %d bytes fetched\n%s" % [bundle.manifest.downloaded_bytes, bundle.manifest.interpretation]
	return true


func show_slice(value: float) -> void:
	if bundle.is_empty():
		return
	var index := clampi(int(value), 0, bundle.images.size() - 1)
	var manifest: Dictionary = bundle.manifest
	image_view.texture = bundle.images[index]
	var identity: String
	if manifest.point.kind == "predicted_synapse":
		identity = "Predicted synapse %s · %s / v888\n%s → %s" % [manifest.point.synapse_id, manifest.point.connectivity_version, manifest.point.pre, manifest.point.post]
	else:
		identity = "%s / node %s" % [manifest.point.neuron_id, manifest.point.swc_node_id]
	image_label.text = "Image: %s\nXY %d / %d · z voxel %d · Δz %.0f nm\n%.0f × %.0f nm/px · X right, Y down" % [identity, index + 1, bundle.images.size(), manifest.origin_voxels[2] + index, manifest.resolution_nm[2], manifest.resolution_nm[0], manifest.resolution_nm[1]]
