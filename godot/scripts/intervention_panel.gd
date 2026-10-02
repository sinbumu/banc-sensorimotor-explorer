extends VBoxContainer
## Pin a verified API baseline and compare structural interventions in one viewport.

signal scene_selected(directory: String)
var viewer: Control
var explorer: VBoxContainer
var baseline: Dictionary = {}
var results: Dictionary = {}
var busy := false
var job := ""
var api_url := ""
var selected_neuron: Dictionary = {}
var baseline_label: Label
var selected_label: Label
var displayed_label: Label
var comparison: Label
var message: Label
var pin_button: Button
var excluded: LineEdit
var cell_type: LineEdit
var side: OptionButton
var threshold: SpinBox
var downloads: CheckBox
var apply_button: Button
var before_button: Button
var after_button: Button
var http: HTTPRequest
var timer: Timer
var latest_job: Dictionary = {}
var all_buttons: Array[Button] = []


func label(value: String) -> Label:
	var item := Label.new()
	item.text = value
	item.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	item.add_theme_font_size_override("font_size", 14)
	add_child(item)
	return item


func button(value: String, action: Callable, parent: Node = null) -> Button:
	var item := Button.new()
	item.text = value
	item.pressed.connect(action)
	(parent if parent != null else self).add_child(item)
	all_buttons.append(item)
	return item


func _ready() -> void:
	add_theme_constant_override("separation", 6)
	label("GRAPH INTERVENTION  /  BEFORE AND AFTER")
	label("Structural graph comparison; no phenotype prediction.")
	pin_button = button("Use displayed path as baseline", pin_baseline)
	baseline_label = label("Calculate a path in Explore, then pin its displayed mode.")
	selected_label = label("No neuron selected.")
	selected_label.visible = false
	var row := HBoxContainer.new()
	add_child(row)
	excluded = LineEdit.new()
	excluded.placeholder_text = "Excluded neuron IDs, comma-separated"
	excluded.tooltip_text = excluded.placeholder_text
	excluded.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	excluded.max_length = 900
	excluded.text_changed.connect(func(_v: String): invalidate())
	row.add_child(excluded)
	button("Add selected", exclude_selected, row)
	button("Clear", func(): excluded.text = ""; invalidate(), row)
	var type_row := HBoxContainer.new()
	add_child(type_row)
	cell_type = LineEdit.new()
	cell_type.placeholder_text = "Exclude type (exact)"
	cell_type.tooltip_text = "Exclude all neurons with this exact cell_type label. Empty means no type filter."
	cell_type.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	cell_type.max_length = 120
	cell_type.text_changed.connect(func(_v: String): invalidate())
	type_row.add_child(cell_type)
	button("Selected type", func(): cell_type.text = str(selected_neuron.get("cell_type", "")) if selected_neuron.get("cell_type") != null else ""; invalidate(), type_row)
	var options := HBoxContainer.new()
	add_child(options)
	side = OptionButton.new()
	for title in ["All sides", "Left only", "Right only"]:
		side.add_item(title)
	side.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	side.tooltip_text = "Side applies to all neurons, including endpoints. Unknown side is excluded."
	side.item_selected.connect(func(_i: int): invalidate())
	options.add_child(side)
	threshold = SpinBox.new()
	threshold.custom_minimum_size.x = 140
	threshold.prefix = "Count ≥ "
	threshold.min_value = 1
	threshold.max_value = 100000
	threshold.value = 5
	threshold.value_changed.connect(func(_v: float): invalidate())
	options.add_child(threshold)
	downloads = CheckBox.new()
	downloads.text = "Fetch missing scene assets"
	downloads.tooltip_text = "Selected after-path SWCs only; graph comparison still works if morphology is unavailable."
	add_child(downloads)
	apply_button = button("Recalculate and compare", submit)
	message = label("Pin a baseline to begin.")
	var views := HBoxContainer.new()
	add_child(views)
	before_button = button("Show before", func(): show_result(false), views)
	after_button = button("Show after", func(): show_result(true), views)
	displayed_label = label("")
	comparison = label("")
	http = HTTPRequest.new()
	http.timeout = 20
	http.body_size_limit = 1000000
	http.use_threads = true
	http.request_completed.connect(response)
	add_child(http)
	timer = Timer.new()
	timer.one_shot = true
	timer.wait_time = 0.5
	timer.timeout.connect(func(): send("/interventions/" + job))
	add_child(timer)
	update_controls()


func _process(_delta: float) -> void:
	update_controls()


func pin_baseline() -> void:
	if busy or viewer.bundle.is_empty():
		return
	var graph: Dictionary = viewer.bundle.scene.path_result
	var mode: String = graph.manifest.path_mode
	var candidate: Dictionary = explorer.latest_job
	if candidate.get("status") != "complete" or not candidate.get("results", {}).has(mode) or candidate.results[mode].scene_directory.replace("\\", "/").simplify_path() != str(viewer.bundle.directory).replace("\\", "/").simplify_path():
		message.text = "Calculate and display a fresh path in Explore before pinning."
		return
	baseline = {"job_id": candidate.id, "mode": mode, "directory": viewer.bundle.directory, "graph": graph}
	api_url = explorer.base_url
	excluded.text = ""
	cell_type.text = ""
	side.select(0)
	threshold.value = graph.manifest.min_synapse_count
	baseline_label.text = "%s · %d hops · cost %.4f\n%s → %s" % ["Minimum hops" if mode == "hops" else "Normalized strength", graph.hop_count, graph.total_cost, graph.neurons[0].id, graph.neurons[-1].id]
	invalidate()
	message.text = "Baseline pinned. Choose exclusions or change threshold/side."


func invalidate() -> void:
	results.clear()
	if comparison != null:
		comparison.text = ""


func set_selected(neuron: Dictionary) -> void:
	selected_neuron = neuron
	selected_label.text = "Selected: %s · %s" % [neuron.id, str(neuron.get("cell_type", ""))]
	for item in all_buttons:
		if item.text in ["Add selected", "Selected type"]:
			item.tooltip_text = selected_label.text


func exclude_selected() -> void:
	if busy or selected_neuron.is_empty():
		return
	var ids := excluded.text.replace(" ", "").split(",", false)
	if selected_neuron.id not in ids:
		ids.append(selected_neuron.id)
	excluded.text = ",".join(ids)
	invalidate()


func update_controls() -> void:
	for item in all_buttons:
		item.disabled = busy
	pin_button.disabled = busy or not explorer.connected
	apply_button.disabled = busy or baseline.is_empty() or not explorer.connected or explorer.base_url != api_url
	excluded.editable = not busy
	cell_type.editable = not busy
	side.disabled = busy
	threshold.editable = not busy
	downloads.disabled = busy or explorer.server_offline
	if explorer.server_offline:
		downloads.button_pressed = false
	before_button.disabled = busy or baseline.is_empty()
	after_button.disabled = busy or results.get("after_scene_directory") == null
	if not viewer.bundle.is_empty() and not baseline.is_empty():
		var directory: String = viewer.bundle.directory
		displayed_label.text = "Showing: " + ("before" if directory == baseline.directory else ("after" if directory == results.get("after_scene_directory") else "another scene"))


func submit() -> void:
	if apply_button.disabled:
		return
	var ids := excluded.text.replace(" ", "").split(",", false)
	var helper = viewer.loader
	for id in ids:
		if not helper.decimal_id(id):
			message.text = "Use comma-separated decimal neuron IDs."
			return
	if ids.size() > 40:
		message.text = "At most 40 explicit neuron exclusions."
		return
	var payload := {"baseline_job_id": baseline.job_id, "mode": baseline.mode, "min_synapse_count": int(threshold.value), "excluded_neurons": Array(ids), "excluded_cell_types": [] if cell_type.text.is_empty() else [cell_type.text], "side": null if side.selected == 0 else ("left" if side.selected == 1 else "right"), "allow_downloads": downloads.button_pressed}
	invalidate()
	latest_job = {}
	busy = true
	message.text = "Recalculating the same endpoints and path objective…"
	send("/interventions/path", payload)


func send(path: String, payload: Variant = null) -> void:
	var error := http.request(api_url + path, PackedStringArray(["Content-Type: application/json"]), HTTPClient.METHOD_GET if payload == null else HTTPClient.METHOD_POST, "" if payload == null else JSON.stringify(payload))
	if error != OK:
		busy = false
		message.text = "Could not start intervention request."


func response(result: int, code: int, _headers: PackedStringArray, body: PackedByteArray) -> void:
	var data: Dictionary = explorer.decode(result, code, body)
	if data.has("error") or not data.get("id") is String or data.get("kind") != "intervention":
		busy = false
		message.text = str(data.get("error", "Invalid intervention response."))
		return
	job = data.id
	latest_job = data
	message.text = str(data.get("message", "Working…"))
	if data.get("status") == "error":
		busy = false
	elif data.get("status") == "complete":
		busy = false
		results = data.get("results", {})
		if not results.has_all(["before_hops", "before_cost", "reachable", "removed_ids", "added_ids"]):
			message.text = "Incomplete comparison result."
			results.clear()
			return
		comparison.text = "Before: %d hops · cost %.4f\n" % [results.before_hops, results.before_cost]
		if results.reachable:
			comparison.text += "After: %d hops · cost %.4f\nRemoved from route: %s\nAdded to route: %s" % [results.after_hops, results.after_cost, ", ".join(results.removed_ids), ", ".join(results.added_ids)]
			if results.after_ids == results.before_ids:
				comparison.text += "\nSame neuron sequence."
		else:
			comparison.text += "After: no directed path (%s)." % results.no_path_reason
		comparison.text += "\n%d neuron%s filtered. Same objective and input totals." % [results.filtered_neuron_count, "" if results.filtered_neuron_count == 1 else "s"]
		if results.get("after_scene_error") != null:
			message.text = "Graph result saved; after morphology unavailable: " + str(results.after_scene_error).left(180)
		show_result(results.get("after_scene_directory") != null)
	else:
		timer.start()


func show_result(after: bool) -> void:
	var directory: String = str(results.get("after_scene_directory", "")) if after else str(baseline.get("directory", ""))
	if not directory.is_empty():
		scene_selected.emit(directory)
