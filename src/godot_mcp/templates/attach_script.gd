extends SceneTree


func _init() -> void:
    var args := _parse_args(OS.get_cmdline_user_args())
    var scene_path := str(args.get("scene-path", "")).strip_edges()
    var node_path := str(args.get("node-path", ".")).strip_edges()
    var script_path := str(args.get("script-path", "")).strip_edges()

    if scene_path.is_empty():
        printerr("Missing required argument: --scene-path")
        quit(1)
        return
    if script_path.is_empty():
        printerr("Missing required argument: --script-path")
        quit(1)
        return

    var resource := ResourceLoader.load(scene_path)
    if resource == null or not (resource is PackedScene):
        printerr("Could not load PackedScene: %s" % scene_path)
        quit(1)
        return

    var packed_scene: PackedScene = resource
    var root := packed_scene.instantiate()
    if root == null or not (root is Node):
        printerr("PackedScene.instantiate did not return a Node root.")
        quit(1)
        return

    var target_node: Node = root
    if not node_path.is_empty() and node_path != ".":
        var found := root.get_node_or_null(node_path)
        if found == null or not (found is Node):
            printerr("Node was not found at path: %s" % node_path)
            quit(1)
            return
        target_node = found

    var loaded_script: Variant = ResourceLoader.load(script_path)
    if loaded_script == null or not (loaded_script is Script):
        printerr("Could not load Script: %s" % script_path)
        quit(1)
        return
    var script_resource: Script = loaded_script

    var previous_script_path := ""
    var previous_script: Variant = target_node.get_script()
    if previous_script != null and previous_script is Resource:
        previous_script_path = str(previous_script.resource_path)

    target_node.set_script(script_resource)

    var repacked := PackedScene.new()
    var pack_error := repacked.pack(root)
    if pack_error != OK:
        printerr("PackedScene.pack failed with code %s" % pack_error)
        quit(1)
        return

    var save_error := ResourceSaver.save(repacked, scene_path)
    if save_error != OK:
        printerr("ResourceSaver.save failed with code %s" % save_error)
        quit(1)
        return

    print(JSON.stringify({
        "scene_path": scene_path,
        "node_path": _scene_relative_path(root, target_node),
        "node_name": str(target_node.name),
        "node_type": target_node.get_class(),
        "script_path": script_path,
        "previous_script_path": previous_script_path,
    }))
    quit()


func _scene_relative_path(root: Node, node: Node) -> String:
    if node == root:
        return "."
    return str(root.get_path_to(node))


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
