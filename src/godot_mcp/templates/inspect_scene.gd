extends SceneTree


func _init() -> void:
    var args := _parse_args(OS.get_cmdline_user_args())
    var scene_path := str(args.get("scene-path", "")).strip_edges()
    if scene_path.is_empty():
        printerr("Missing required argument: --scene-path")
        quit(1)
        return

    var resource := ResourceLoader.load(scene_path)
    if resource == null or not (resource is PackedScene):
        printerr("Could not load PackedScene: %s" % scene_path)
        quit(1)
        return

    var packed_scene: PackedScene = resource
    var state := packed_scene.get_state()

    var nodes := []
    for index in range(state.get_node_count()):
        var is_placeholder := state.is_node_instance_placeholder(index)
        nodes.append({
            "index": index,
            "name": str(state.get_node_name(index)),
            "type": str(state.get_node_type(index)),
            "path": _node_path_to_string(state.get_node_path(index), "."),
            "parent_path": _node_path_to_string(state.get_node_path(index, true), ""),
            "owner_path": _node_path_to_string(state.get_node_owner_path(index), ""),
            "groups": state.get_node_groups(index),
            "child_index": state.get_node_index(index),
            "instance_placeholder": is_placeholder,
            "instance_scene_path": _node_path_to_string(
                state.get_node_instance_placeholder(index),
                ""
            ) if is_placeholder else "",
        })

    var connections := []
    for index in range(state.get_connection_count()):
        connections.append({
            "source_path": _node_path_to_string(state.get_connection_source(index), ""),
            "signal_name": str(state.get_connection_signal(index)),
            "target_path": _node_path_to_string(state.get_connection_target(index), ""),
            "method_name": str(state.get_connection_method(index)),
            "flags": int(state.get_connection_flags(index)),
            "binds": state.get_connection_binds(index),
            "unbinds": int(state.get_connection_unbinds(index)),
        })

    print(JSON.stringify({
        "scene_path": scene_path,
        "nodes": nodes,
        "connections": connections,
    }))
    quit()


func _node_path_to_string(path: Variant, empty_value: String) -> String:
    var text := str(path)
    return empty_value if text.is_empty() else text


func _parse_args(argv: PackedStringArray) -> Dictionary:
    var parsed := {}
    var index := 0
    while index < argv.size():
        var key := argv[index]
        if not key.begins_with("--"):
            index += 1
            continue

        var name := key.substr(2)
        var value := "true"
        if index + 1 < argv.size() and not argv[index + 1].begins_with("--"):
            value = argv[index + 1]
            index += 1

        parsed[name] = value
        index += 1

    return parsed
