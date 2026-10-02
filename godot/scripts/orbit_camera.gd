extends Camera3D
## Orthographic orbit camera. Coordinates arrive already transformed by Python.

var center := Vector3.ZERO
var home_center := Vector3.ZERO
var radius := 1.0
var half_extent := Vector3.ONE
var yaw := 0.0
var pitch := -0.78
var zoom_factor := 1.0
var view_size := Vector2(1000, 700)


func fit_bounds(lower: Vector3, upper: Vector3) -> void:
	home_center = (lower + upper) * 0.5
	half_extent = (upper - lower) * 0.5
	radius = maxf((upper - lower).length() * 0.5, 0.01)
	reset_view()


func reset_view() -> void:
	center = home_center
	yaw = 0.0
	pitch = -0.78
	zoom_factor = 1.0
	update_view()


func resize_view(dimensions: Vector2) -> void:
	view_size = dimensions.max(Vector2.ONE)
	update_view()


func orbit(delta: Vector2) -> void:
	yaw -= delta.x * 0.006
	pitch = clampf(pitch - delta.y * 0.006, -1.48, 1.48)
	update_view()


func pan(delta: Vector2) -> void:
	center += (-global_basis.x * delta.x + global_basis.y * delta.y) * size / view_size.y
	update_view()


func zoom(amount: float) -> void:
	zoom_factor = clampf(zoom_factor * exp(amount), 0.06, 12.0)
	update_view()


func update_view() -> void:
	projection = Camera3D.PROJECTION_ORTHOGONAL
	keep_aspect = Camera3D.KEEP_HEIGHT
	near = maxf(radius * 0.001, 0.00001)
	far = radius * 12.0
	position = center + Vector3(sin(yaw) * cos(pitch), sin(pitch), cos(yaw) * cos(pitch)) * radius * 4.0
	look_at(center, Vector3.UP)
	# Fit the projected bounding box, including portrait viewports, without clipping.
	var projected_height := 2.0 * global_basis.y.abs().dot(half_extent)
	var projected_width := 2.0 * global_basis.x.abs().dot(half_extent)
	size = maxf(maxf(projected_height, projected_width * view_size.y / view_size.x), 0.02) * 1.15 * zoom_factor
