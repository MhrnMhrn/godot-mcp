extends Node
## Godot MCP Profiler — injected as an autoload to collect Performance metrics.
## Writes a JSON report to the path given by --output-path, then quits.

var _duration: float = 5.0
var _elapsed: float = 0.0
var _output_path: String = ""
var _samples: Array = []
var _sample_interval: float = 0.0
var _time_since_last_sample: float = 0.0
var _started: bool = false


func _ready() -> void:
	var args := _parse_args(OS.get_cmdline_user_args())
	_duration = float(args.get("duration", "5.0"))
	_output_path = args.get("output-path", "")
	_sample_interval = float(args.get("sample-interval", "0.0"))
	if _output_path.is_empty():
		_output_path = ProjectSettings.globalize_path("res://.godot-mcp/profiler_results.json")
	# Run after everything else so metrics reflect the full frame.
	process_priority = 1000


func _process(delta: float) -> void:
	_elapsed += delta
	_time_since_last_sample += delta

	if not _started:
		_started = true
		return

	if _sample_interval > 0.0 and _time_since_last_sample < _sample_interval:
		if _elapsed < _duration:
			return

	_time_since_last_sample = 0.0

	var sample := {}
	sample["time"] = snappedf(_elapsed, 0.0001)
	sample["delta"] = snappedf(delta, 0.000001)

	sample["frame_time_ms"] = snappedf(delta * 1000.0, 0.001)
	sample["process_time_ms"] = snappedf(Performance.get_monitor(Performance.TIME_PROCESS) * 1000.0, 0.001)
	sample["physics_time_ms"] = snappedf(Performance.get_monitor(Performance.TIME_PHYSICS_PROCESS) * 1000.0, 0.001)
	sample["physics_frame_time_ms"] = snappedf((1000.0 / max(Engine.physics_ticks_per_second, 1)), 0.001)
	sample["navigation_process_ms"] = snappedf(Performance.get_monitor(Performance.TIME_NAVIGATION_PROCESS) * 1000.0, 0.001)
	sample["fps"] = Performance.get_monitor(Performance.TIME_FPS)

	sample["audio_output_latency_ms"] = snappedf(Performance.get_monitor(Performance.AUDIO_OUTPUT_LATENCY) * 1000.0, 0.001)

	sample["memory_static_bytes"] = Performance.get_monitor(Performance.MEMORY_STATIC)
	sample["memory_static_max_bytes"] = Performance.get_monitor(Performance.MEMORY_STATIC_MAX)
	sample["memory_msg_buffer_max_bytes"] = Performance.get_monitor(Performance.MEMORY_MESSAGE_BUFFER_MAX)

	sample["object_count"] = int(Performance.get_monitor(Performance.OBJECT_COUNT))
	sample["resource_count"] = int(Performance.get_monitor(Performance.OBJECT_RESOURCE_COUNT))
	sample["node_count"] = int(Performance.get_monitor(Performance.OBJECT_NODE_COUNT))
	sample["orphan_node_count"] = int(Performance.get_monitor(Performance.OBJECT_ORPHAN_NODE_COUNT))

	sample["render_objects_in_frame"] = int(Performance.get_monitor(Performance.RENDER_TOTAL_OBJECTS_IN_FRAME))
	sample["render_primitives_in_frame"] = int(Performance.get_monitor(Performance.RENDER_TOTAL_PRIMITIVES_IN_FRAME))
	sample["render_draw_calls_in_frame"] = int(Performance.get_monitor(Performance.RENDER_TOTAL_DRAW_CALLS_IN_FRAME))
	sample["render_video_mem_bytes"] = Performance.get_monitor(Performance.RENDER_VIDEO_MEM_USED)

	sample["physics_2d_active_objects"] = int(Performance.get_monitor(Performance.PHYSICS_2D_ACTIVE_OBJECTS))
	sample["physics_2d_collision_pairs"] = int(Performance.get_monitor(Performance.PHYSICS_2D_COLLISION_PAIRS))
	sample["physics_2d_island_count"] = int(Performance.get_monitor(Performance.PHYSICS_2D_ISLAND_COUNT))

	sample["physics_3d_active_objects"] = int(Performance.get_monitor(Performance.PHYSICS_3D_ACTIVE_OBJECTS))
	sample["physics_3d_collision_pairs"] = int(Performance.get_monitor(Performance.PHYSICS_3D_COLLISION_PAIRS))
	sample["physics_3d_island_count"] = int(Performance.get_monitor(Performance.PHYSICS_3D_ISLAND_COUNT))

	sample["navigation_active_maps"] = int(Performance.get_monitor(Performance.NAVIGATION_ACTIVE_MAPS))
	sample["navigation_region_count"] = int(Performance.get_monitor(Performance.NAVIGATION_REGION_COUNT))
	sample["navigation_agent_count"] = int(Performance.get_monitor(Performance.NAVIGATION_AGENT_COUNT))
	sample["navigation_link_count"] = int(Performance.get_monitor(Performance.NAVIGATION_LINK_COUNT))

	_samples.append(sample)

	if _elapsed >= _duration:
		_write_results()
		get_tree().quit()


func _write_results() -> void:
	var results := {
		"duration_seconds": snappedf(_elapsed, 0.001),
		"sample_count": _samples.size(),
		"samples": _samples,
	}

	var dir_path := _output_path.get_base_dir()
	if not dir_path.is_empty():
		DirAccess.make_dir_recursive_absolute(dir_path)

	var file := FileAccess.open(_output_path, FileAccess.WRITE)
	if file:
		file.store_string(JSON.stringify(results, "\t"))
		file.close()
	else:
		push_error("GodotMcpProfiler: Failed to write results to %s" % _output_path)


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
