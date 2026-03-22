extends SceneTree


func _init() -> void:
    var args := _parse_args(OS.get_cmdline_user_args())
    var scene_path := str(args.get("scene-path", "")).strip_edges()
    var root_type := str(args.get("root-type", "Node2D")).strip_edges()
    var root_name := str(args.get("root-name", "Main")).strip_edges()
    var set_main_scene := str(args.get("set-main-scene", "false")).to_lower() == "true"

    if scene_path.is_empty():
        printerr("Missing required argument: --scene-path")
        quit(1)
        return

    if not ClassDB.class_exists(root_type):
        printerr("Unknown Godot class: %s" % root_type)
        quit(1)
        return

    if not ClassDB.can_instantiate(root_type):
        printerr("Class cannot be instantiated: %s" % root_type)
        quit(1)
        return

    var root = ClassDB.instantiate(root_type)
    if root == null or not (root is Node):
        printerr("Class is not a Node: %s" % root_type)
        quit(1)
        return

    root.name = root_name

    var packed_scene := PackedScene.new()
    var pack_error := packed_scene.pack(root)
    if pack_error != OK:
        printerr("PackedScene.pack failed with code %s" % pack_error)
        quit(1)
        return

    var save_error := ResourceSaver.save(packed_scene, scene_path)
    if save_error != OK:
        printerr("ResourceSaver.save failed with code %s" % save_error)
        quit(1)
        return

    if set_main_scene:
        ProjectSettings.set_setting("application/run/main_scene", scene_path)
        var settings_error := ProjectSettings.save()
        if settings_error != OK:
            printerr("ProjectSettings.save failed with code %s" % settings_error)
            quit(1)
            return

    print(JSON.stringify({
        "scene_path": scene_path,
        "root_type": root_type,
        "root_name": root_name,
        "set_main_scene": set_main_scene,
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

