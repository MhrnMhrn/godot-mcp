extends Node
## Godot MCP Camera Controller — injected as autoload to animate a camera along waypoints.
## Reads waypoints JSON from --waypoints-path.

var _waypoints: Array = []
var _duration: float = 5.0
var _elapsed: float = 0.0
var _camera: Camera3D = null
var _camera_node_path: String = ""
var _total_waypoint_time: float = 0.0
var _started: bool = false


func _ready() -> void:
	var args := _parse_args(OS.get_cmdline_user_args())
	_duration = float(args.get("camera-duration", "5.0"))
	_camera_node_path = str(args.get("camera-node-path", ""))
	var waypoints_path := str(args.get("waypoints-path", ""))

	if not waypoints_path.is_empty():
		var file := FileAccess.open(waypoints_path, FileAccess.READ)
		if file:
			var parsed: Variant = JSON.parse_string(file.get_as_text())
			if parsed is Array:
				_waypoints = parsed

	# Calculate total waypoint time.
	for wp in _waypoints:
		if wp is Dictionary and wp.has("time"):
			var t: float = float(wp["time"])
			if t > _total_waypoint_time:
				_total_waypoint_time = t

	if _total_waypoint_time <= 0.0 and _waypoints.size() > 0:
		_total_waypoint_time = _duration
		var count: int = _waypoints.size()
		for i in range(count):
			if _waypoints[i] is Dictionary:
				_waypoints[i]["time"] = (_duration * float(i)) / max(float(count - 1), 1.0)

	process_priority = -1000  # Run before everything else to position camera early.


func _process(delta: float) -> void:
	if not _started:
		_started = true
		_find_camera()
		if _camera != null and _waypoints.size() > 0:
			_apply_waypoint_at_time(0.0)
		return

	_elapsed += delta

	if _camera != null and _waypoints.size() > 0:
		_apply_waypoint_at_time(_elapsed)


func _find_camera() -> void:
	if not _camera_node_path.is_empty():
		var found := get_tree().root.get_node_or_null(_camera_node_path)
		if found is Camera3D:
			_camera = found
			_camera.current = true
			return

	# Search for any Camera3D in the scene.
	_camera = _find_camera_recursive(get_tree().root)
	if _camera != null:
		_camera.current = true


func _find_camera_recursive(node: Node) -> Camera3D:
	if node is Camera3D:
		return node
	for child in node.get_children():
		var found := _find_camera_recursive(child)
		if found != null:
			return found
	return null


func _apply_waypoint_at_time(t: float) -> void:
	if _waypoints.size() == 0 or _camera == null:
		return

	# With a single waypoint just hold it.
	if _waypoints.size() == 1:
		var wp: Dictionary = _waypoints[0]
		_camera.position = _dict_to_vector3(wp.get("position", {}))
		_camera.rotation_degrees = _dict_to_vector3(wp.get("rotation_degrees", {}))
		if wp.has("fov"):
			_camera.fov = float(wp["fov"])
		return

	# Remap global time with a single ease-in/out curve so the camera accelerates
	# from rest and decelerates to a stop at the end — applied once globally so
	# there are no velocity discontinuities at intermediate waypoints.
	var global_progress: float = clampf(t / _total_waypoint_time, 0.0, 1.0)
	var clamped_t: float = _smoothstep(global_progress) * _total_waypoint_time

	# Find segment index i such that waypoints[i].time <= clamped_t < waypoints[i+1].time.
	var seg: int = 0
	for i in range(_waypoints.size() - 1):
		if float(_waypoints[i].get("time", 0.0)) <= clamped_t:
			seg = i
		else:
			break

	var t0: float = float(_waypoints[seg].get("time", 0.0))
	var t1: float = float(_waypoints[seg + 1].get("time", 0.0))
	var local_t: float = 0.0
	if t1 > t0:
		local_t = clampf((clamped_t - t0) / (t1 - t0), 0.0, 1.0)

	# Catmull-Rom control point indices (clamped at boundaries).
	var i0: int = max(seg - 1, 0)
	var i1: int = seg
	var i2: int = seg + 1
	var i3: int = min(seg + 2, _waypoints.size() - 1)

	var p0 := _dict_to_vector3(_waypoints[i0].get("position", {}))
	var p1 := _dict_to_vector3(_waypoints[i1].get("position", {}))
	var p2 := _dict_to_vector3(_waypoints[i2].get("position", {}))
	var p3 := _dict_to_vector3(_waypoints[i3].get("position", {}))
	_camera.position = _catmull_rom_v3(p0, p1, p2, p3, local_t)

	var r0 := _dict_to_vector3(_waypoints[i0].get("rotation_degrees", {}))
	var r1 := _dict_to_vector3(_waypoints[i1].get("rotation_degrees", {}))
	var r2 := _dict_to_vector3(_waypoints[i2].get("rotation_degrees", {}))
	var r3 := _dict_to_vector3(_waypoints[i3].get("rotation_degrees", {}))
	_camera.rotation_degrees = _catmull_rom_v3(r0, r1, r2, r3, local_t)

	# Interpolate FOV if provided on either end of the segment.
	var wp1: Dictionary = _waypoints[i1]
	var wp2: Dictionary = _waypoints[i2]
	if wp1.has("fov") or wp2.has("fov"):
		var f0: float = float(_waypoints[i0].get("fov", _camera.fov))
		var f1: float = float(wp1.get("fov", _camera.fov))
		var f2: float = float(wp2.get("fov", _camera.fov))
		var f3: float = float(_waypoints[i3].get("fov", _camera.fov))
		_camera.fov = _catmull_rom_f(f0, f1, f2, f3, local_t)


## Catmull-Rom spline for Vector3 — produces a smooth curve through p1→p2
## with continuous velocity at each interior waypoint.
func _catmull_rom_v3(p0: Vector3, p1: Vector3, p2: Vector3, p3: Vector3, t: float) -> Vector3:
	var t2 := t * t
	var t3 := t2 * t
	return 0.5 * (
		2.0 * p1
		+ (-p0 + p2) * t
		+ (2.0 * p0 - 5.0 * p1 + 4.0 * p2 - p3) * t2
		+ (-p0 + 3.0 * p1 - 3.0 * p2 + p3) * t3
	)


## Catmull-Rom spline for a scalar (used for FOV).
func _catmull_rom_f(p0: float, p1: float, p2: float, p3: float, t: float) -> float:
	var t2 := t * t
	var t3 := t2 * t
	return 0.5 * (
		2.0 * p1
		+ (-p0 + p2) * t
		+ (2.0 * p0 - 5.0 * p1 + 4.0 * p2 - p3) * t2
		+ (-p0 + 3.0 * p1 - 3.0 * p2 + p3) * t3
	)


func _smoothstep(t: float) -> float:
	return t * t * (3.0 - 2.0 * t)


func _dict_to_vector3(d: Variant) -> Vector3:
	if d is Dictionary:
		return Vector3(
			float(d.get("x", 0.0)),
			float(d.get("y", 0.0)),
			float(d.get("z", 0.0))
		)
	if d is Array and d.size() == 3:
		return Vector3(float(d[0]), float(d[1]), float(d[2]))
	return Vector3.ZERO


func _parse_args(raw_args: PackedStringArray) -> Dictionary:
	var parsed := {}
	var i := 0
	while i < raw_args.size():
		var arg: String = raw_args[i]
		if arg.begins_with("--") and i + 1 < raw_args.size():
			parsed[arg.substr(2)] = raw_args[i + 1]
			i += 2
		else:
			i += 1
	return parsed
