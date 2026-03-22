extends SceneTree


func _init() -> void:
    var args := _parse_args(OS.get_cmdline_user_args())
    var scene_path := str(args.get("scene-path", "")).strip_edges()

    if scene_path.is_empty():
        printerr("Missing required argument: --scene-path")
        quit(1)
        return

    var loaded: Variant = ResourceLoader.load(scene_path)
    if loaded == null:
        print(JSON.stringify({
            "scene_path": scene_path,
            "valid": false,
            "message": "Godot could not parse the scene resource.",
            "resource_type": "",
            "node_count": 0,
            "root_node_name": "",
            "root_node_type": "",
            "connection_count": 0,
        }))
        quit()
        return

    if not (loaded is PackedScene):
        var resource: Resource = loaded
        print(JSON.stringify({
            "scene_path": scene_path,
            "valid": false,
            "message": "The file loaded, but it is not a PackedScene resource.",
            "resource_type": resource.get_class(),
            "node_count": 0,
            "root_node_name": "",
            "root_node_type": "",
            "connection_count": 0,
        }))
        quit()
        return

    var packed_scene: PackedScene = loaded
    var state := packed_scene.get_state()
    if state == null:
        print(JSON.stringify({
            "scene_path": scene_path,
            "valid": false,
            "message": "Godot loaded the scene, but it did not expose a valid scene state.",
            "resource_type": packed_scene.get_class(),
            "node_count": 0,
            "root_node_name": "",
            "root_node_type": "",
            "connection_count": 0,
        }))
        quit()
        return

    var node_count := state.get_node_count()
    print(JSON.stringify({
        "scene_path": scene_path,
        "valid": true,
        "message": "Scene parsed successfully.",
        "resource_type": packed_scene.get_class(),
        "node_count": node_count,
        "root_node_name": str(state.get_node_name(0)) if node_count > 0 else "",
        "root_node_type": str(state.get_node_type(0)) if node_count > 0 else "",
        "connection_count": state.get_connection_count(),
    }))
    quit()


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
