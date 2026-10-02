extends VBoxContainer
## Async localhost controller. Python owns graph queries, provenance and scene export.

signal scene_selected(directory: String)
const MODES = ["hops", "normalized"]
var base_url := "http://127.0.0.1:8767"
var connected := false
var busy := false
var server_offline := false
var em_available := false
var active_job := ""
var latest_job: Dictionary = {}
var completed_scenes: Dictionary = {}
var chosen := {"sensory": {}, "motor": {}}
var rows := {"sensory": [], "motor": []}
var queries := {}
var body_parts := {}
var choices := {}
var searches := {}
var search_buttons := {}
var sent_queries := {}
var url_input: LineEdit
var connect_button: Button
var connection_label: Label
var message: Label
var comparison: Label
var mode: OptionButton
var threshold: SpinBox
var proofread: CheckBox
var downloads: CheckBox
var include_context: CheckBox
var compare: CheckBox
var find_button: Button
var health_http: HTTPRequest
var facets_http: HTTPRequest
var submit_http: HTTPRequest
var poll_http: HTTPRequest
var poll_timer: Timer


func label(text_value: String) -> Label:
	var result := Label.new()
	result.text = text_value
	result.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	result.add_theme_font_size_override("font_size", 14)
	return result


func http(callback: Callable) -> HTTPRequest:
	var request := HTTPRequest.new()
	request.timeout = 20.0
	request.body_size_limit = 1024 * 1024
	request.use_threads = true
	request.request_completed.connect(callback)
	add_child(request)
	return request


func _ready() -> void:
	add_theme_constant_override("separation", 5)
	var connect_row := HBoxContainer.new()
	add_child(connect_row)
	url_input = LineEdit.new()
	url_input.text = base_url
	url_input.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	connect_row.add_child(url_input)
	connect_button = Button.new()
	connect_button.text = "Connect"
	connect_button.pressed.connect(connect_api)
	connect_row.add_child(connect_button)
	connection_label = label("Local API disconnected. File viewing remains available.")
	add_child(connection_label)
	for kind in ["sensory", "motor"]:
		add_child(HSeparator.new())
		add_child(label("SOURCE  /  sensory" if kind == "sensory" else "TARGET  /  motor"))
		var query_row := HBoxContainer.new()
		add_child(query_row)
		var query := LineEdit.new()
		query.placeholder_text = "Name, nerve, body part or ID"
		query.max_length = 120
		query.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		query.add_theme_font_size_override("font_size", 14)
		queries[kind] = query
		query_row.add_child(query)
		query.text_changed.connect(func(_value: String): invalidate_kind(kind))
		query.text_submitted.connect(func(_value: String): search(kind))
		var search_button := Button.new()
		search_button.text = "Search"
		search_button.pressed.connect(func(): search(kind))
		search_buttons[kind] = search_button
		query_row.add_child(search_button)
		var part := OptionButton.new()
		part.clip_text = true
		part.fit_to_longest_item = false
		part.add_item("All body parts")
		part.item_selected.connect(func(_index: int): invalidate_kind(kind); search(kind))
		body_parts[kind] = part
		add_child(part)
		var choice := OptionButton.new()
		choice.clip_text = true
		choice.fit_to_longest_item = false
		choice.add_theme_font_size_override("font_size", 14)
		choice.add_item("Search and choose a neuron…")
		choice.item_selected.connect(func(index: int): choose(kind, index))
		choices[kind] = choice
		add_child(choice)
	proofread = CheckBox.new()
	proofread.text = "Proofread endpoints only"
	proofread.button_pressed = true
	proofread.toggled.connect(func(_value: bool):
		for kind in queries:
			invalidate_kind(kind)
			search(kind))
	add_child(proofread)
	add_child(HSeparator.new())
	var options := HBoxContainer.new()
	add_child(options)
	mode = OptionButton.new()
	mode.add_item("Minimum hops")
	mode.add_item("Normalized strength")
	mode.select(1)
	mode.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	mode.item_selected.connect(display_mode)
	options.add_child(mode)
	var threshold_label := label("Min synapses")
	threshold_label.autowrap_mode = TextServer.AUTOWRAP_OFF
	options.add_child(threshold_label)
	threshold = SpinBox.new()
	threshold.min_value = 1
	threshold.max_value = 100000
	threshold.value = 5
	threshold.value_changed.connect(func(_value: float): invalidate_results())
	options.add_child(threshold)
	compare = CheckBox.new()
	compare.text = "Calculate both modes for comparison"
	compare.button_pressed = true
	compare.toggled.connect(func(_value: bool): invalidate_results())
	add_child(compare)
	include_context = CheckBox.new()
	include_context.text = "Include brain / VNC outlines"
	include_context.tooltip_text = "Public neuropil context has separate provenance; not a v888 materialization asset."
	include_context.toggled.connect(func(_value: bool): invalidate_results())
	add_child(include_context)
	downloads = CheckBox.new()
	downloads.text = "Fetch missing scene assets"
	downloads.tooltip_text = "Only selected path neurons; at most 20 MB per SWC and 100 MB per exported scene. Optional outlines: two regions, six files, at most 5 MB per file. Core metadata and edges must already be cached."
	downloads.button_pressed = false
	add_child(downloads)
	find_button = Button.new()
	find_button.text = "Find path"
	find_button.custom_minimum_size.y = 40
	find_button.pressed.connect(find_paths)
	add_child(find_button)
	message = label("Start the service with: uv run --extra api banc-explorer serve")
	add_child(message)
	comparison = label("")
	add_child(comparison)
	add_child(label("New queries keep the current scene visible until the next bundle is verified. Inspect annotations in the Inspect tab."))
	health_http = http(_health_response)
	facets_http = http(_facets_response)
	submit_http = http(_submit_response)
	poll_http = http(_poll_response)
	for kind in queries:
		searches[kind] = http(func(result: int, code: int, _headers: PackedStringArray, body: PackedByteArray): _search_response(kind, result, code, body))
	poll_timer = Timer.new()
	poll_timer.wait_time = 0.4
	poll_timer.one_shot = true
	poll_timer.timeout.connect(poll_job)
	add_child(poll_timer)
	update_controls()


func seed_from_scene(graph: Dictionary) -> void:
	if connected or busy:
		return
	queries.sensory.text = graph.neurons[0].id
	queries.motor.text = graph.neurons[-1].id
	threshold.value = graph.manifest.min_synapse_count
	mode.select(MODES.find(graph.manifest.path_mode))


func connect_api() -> void:
	if busy:
		return
	var pattern := RegEx.new()
	pattern.compile("^http://(127\\.0\\.0\\.1|localhost):([0-9]{1,5})/?$")
	var match_url := pattern.search(url_input.text.strip_edges())
	if match_url == null or int(match_url.get_string(2)) < 1 or int(match_url.get_string(2)) > 65535:
		message.text = "Use a localhost URL such as http://127.0.0.1:8767."
		return
	base_url = url_input.text.strip_edges().trim_suffix("/")
	connected = false
	health_http.cancel_request()
	facets_http.cancel_request()
	for kind in queries:
		invalidate_kind(kind)
	update_controls()
	connection_label.text = "Connecting to local API…"
	request(health_http, "/health")


func request(client: HTTPRequest, path: String, payload: Variant = null) -> bool:
	var headers := PackedStringArray(["Content-Type: application/json"])
	var method := HTTPClient.METHOD_GET if payload == null else HTTPClient.METHOD_POST
	var result := client.request(base_url + path, headers, method, "" if payload == null else JSON.stringify(payload))
	if result != OK:
		message.text = "Could not start API request (error %d). Reconnect and try again." % result
		return false
	return true


func decode(result: int, code: int, body: PackedByteArray) -> Dictionary:
	if result != HTTPRequest.RESULT_SUCCESS:
		return {"error": "Local API unavailable or timed out. Start the service and click Connect."}
	var parsed: Variant = JSON.parse_string(body.get_string_from_utf8())
	if not parsed is Dictionary:
		return {"error": "Local API returned an invalid JSON response."}
	if code < 200 or code >= 300:
		return {"error": str(parsed.get("detail", "Request failed (%d)" % code)).left(400)}
	return parsed


func _health_response(result: int, code: int, _headers: PackedStringArray, body: PackedByteArray) -> void:
	var data := decode(result, code, body)
	if data.has("error"):
		connection_label.text = data.error
		return
	if data.get("service") != "banc-explorer" or data.get("api_version") != 1 or data.get("materialization") != 888 or data.get("connectivity_version") not in ["v2", "v3"]:
		connection_label.text = "Unsupported API service/version. Expected BANC v888 API v1."
		return
	connected = true
	server_offline = data.get("offline", true)
	em_available = data.get("em_available", false)
	if server_offline:
		downloads.button_pressed = false
	connection_label.text = "Connected · BANC v888 / %s%s" % [data.connectivity_version, " · cache only" if server_offline else ""]
	message.text = "Search by annotation or ID, then choose a sensory source and motor target."
	update_controls()
	request(facets_http, "/metadata/facets")


func _facets_response(result: int, code: int, _headers: PackedStringArray, body: PackedByteArray) -> void:
	var data := decode(result, code, body)
	if data.has("error"):
		message.text = data.error
		return
	for kind in queries:
		body_parts[kind].clear()
		body_parts[kind].add_item("All body parts")
		if data.get(kind) is Array:
			for part in data[kind]:
				body_parts[kind].add_item(str(part))
		body_parts[kind].select(0)
		search(kind)


func signature(kind: String) -> String:
	return "%s|%d|%s" % [queries[kind].text.strip_edges(), body_parts[kind].selected, proofread.button_pressed]


func invalidate_kind(kind: String) -> void:
	if searches.has(kind):
		searches[kind].cancel_request()
	chosen[kind] = {}
	rows[kind] = []
	choices[kind].clear()
	choices[kind].add_item("Search and choose a neuron…")
	invalidate_results()


func invalidate_results() -> void:
	completed_scenes.clear()
	if comparison != null:
		comparison.text = ""
	if find_button != null:
		update_controls()


func search(kind: String) -> void:
	if not connected or busy:
		return
	invalidate_kind(kind)
	sent_queries[kind] = signature(kind)
	var path := "/neurons/search?kind=%s&q=%s&proofread_only=%s&limit=50" % [kind, queries[kind].text.strip_edges().uri_encode(), "true" if proofread.button_pressed else "false"]
	if body_parts[kind].selected > 0:
		path += "&body_part=" + body_parts[kind].get_item_text(body_parts[kind].selected).uri_encode()
	choices[kind].set_item_text(0, "Searching…")
	request(searches[kind], path)


func _search_response(kind: String, result: int, code: int, body: PackedByteArray) -> void:
	if sent_queries.get(kind) != signature(kind):
		return
	var data := decode(result, code, body)
	if data.has("error") or not data.get("neurons") is Array:
		message.text = data.get("error", "Invalid neuron search response.")
		choices[kind].set_item_text(0, "Search failed — retry")
		return
	rows[kind] = data.neurons
	choices[kind].clear()
	choices[kind].add_item("Choose a neuron (%d / %d shown)" % [rows[kind].size(), data.get("total", 0)])
	for neuron in rows[kind]:
		var title := str(neuron.get("cell_type") if neuron.get("cell_type") != null else "Unannotated")
		choices[kind].add_item("%s · %s" % [title, str(neuron.get("id", ""))])
		choices[kind].get_popup().set_item_tooltip(choices[kind].item_count - 1, str(neuron))
	choices[kind].select(0)
	update_controls()


func choose(kind: String, index: int) -> void:
	chosen[kind] = rows[kind][index - 1] if index > 0 and index <= rows[kind].size() else {}
	invalidate_results()


func update_controls() -> void:
	connect_button.disabled = busy
	url_input.editable = not busy
	for kind in queries:
		queries[kind].editable = not busy
		body_parts[kind].disabled = busy or not connected
		choices[kind].disabled = busy or not connected or rows[kind].is_empty()
		search_buttons[kind].disabled = busy or not connected
	mode.disabled = busy
	threshold.editable = not busy
	proofread.disabled = busy
	compare.disabled = busy
	downloads.disabled = busy or server_offline
	include_context.disabled = busy
	find_button.disabled = busy or not connected or chosen.sensory.is_empty() or chosen.motor.is_empty()
	find_button.text = "Working…" if busy else "Find path"


func find_paths() -> void:
	if find_button.disabled:
		return
	invalidate_results()
	busy = true
	latest_job = {}
	update_controls()
	message.text = "Submitting selected endpoints…"
	var payload := {"source_id": chosen.sensory.id, "target_id": chosen.motor.id, "min_synapse_count": int(threshold.value), "modes": MODES if compare.button_pressed else [MODES[mode.selected]], "proofread_endpoints": proofread.button_pressed, "allow_downloads": downloads.button_pressed, "include_context": include_context.button_pressed}
	if not request(submit_http, "/paths", payload):
		busy = false
		update_controls()


func _submit_response(result: int, code: int, _headers: PackedStringArray, body: PackedByteArray) -> void:
	var data := decode(result, code, body)
	if data.has("error") or not data.get("id") is String:
		job_failed(data.get("error", "Invalid path job response."))
		return
	active_job = data.id
	poll_timer.start()


func poll_job() -> void:
	if busy and not active_job.is_empty():
		if not request(poll_http, "/paths/" + active_job.uri_encode()):
			job_failed("Could not poll job. Reconnect; the server may still be working.")


func _poll_response(result: int, code: int, _headers: PackedStringArray, body: PackedByteArray) -> void:
	var data := decode(result, code, body)
	if data.has("error"):
		job_failed(data.error)
		return
	if data.get("id") != active_job:
		job_failed("Unexpected path job ID.")
		return
	latest_job = data
	message.text = str(data.get("message", "Working…"))
	match data.get("status"):
		"complete":
			busy = false
			completed_scenes = data.get("results", {})
			update_controls()
			var lines := PackedStringArray()
			for key in MODES:
				if completed_scenes.has(key):
					var item: Dictionary = completed_scenes[key]
					lines.append("%s: %d hops · cost %.4f" % ["Minimum hops" if key == "hops" else "Normalized strength", item.hop_count, item.total_cost])
			if completed_scenes.has("hops") and completed_scenes.has("normalized"):
				lines.append("Same neuron sequence." if completed_scenes.hops.neuron_ids == completed_scenes.normalized.neuron_ids else "Different neuron sequences; switch modes to inspect.")
			lines.append("Each mode uses its own cost definition.")
			comparison.text = "\n".join(lines)
			display_mode(mode.selected)
		"error": job_failed(message.text)
		"queued", "running": poll_timer.start()
		_: job_failed("Unsupported path job status.")


func display_mode(index: int) -> void:
	var key: String = MODES[index]
	if completed_scenes.has(key):
		scene_selected.emit(completed_scenes[key].scene_directory)
	elif not completed_scenes.is_empty():
		message.text = "This mode was not calculated. Click Find path again."


func job_failed(reason: String) -> void:
	busy = false
	poll_timer.stop()
	message.text = reason + " Current scene retained."
	update_controls()
