extends SceneTree


func _init() -> void:
    var args := _parse_args(OS.get_cmdline_user_args())
    var scene_path := str(args.get("scene-path", "")).strip_edges()
    var parent_path := str(args.get("parent-path", ".")).strip_edges()
    var node_type := str(args.get("node-type", "")).strip_edges()
    var node_name := str(args.get("node-name", "")).strip_edges()

    if scene_path.is_empty():
        printerr("Missing required argument: --scene-path")
        quit(1)
        return
    if node_type.is_empty():
        printerr("Missing required argument: --node-type")
        quit(1)
        return
    if node_name.is_empty():
        printerr("Missing required argument: --node-name")
        quit(1)
        return

    var resource := ResourceLoader.load(scene_path)
    if resource == null or not (resource is PackedScene):
        printerr("Could not load PackedScene: %s" % scene_path)
        quit(1)
        return

    if not ClassDB.class_exists(node_type):
        printerr("Unknown Godot class: %s" % node_type)
        quit(1)
        return
    if not ClassDB.can_instantiate(node_type):
        printerr("Class cannot be instantiated: %s" % node_type)
        quit(1)
        return

    var packed_scene: PackedScene = resource
    var root := packed_scene.instantiate()
    if root == null or not (root is Node):
        printerr("PackedScene.instantiate did not return a Node root.")
        quit(1)
        return

    var parent_node: Node = root
    if not parent_path.is_empty() and parent_path != ".":
        var found := root.get_node_or_null(parent_path)
        if found == null or not (found is Node):
            printerr("Parent node was not found at path: %s" % parent_path)
            quit(1)
            return
        parent_node = found

    for child in parent_node.get_children():
        if child.name == node_name:
            printerr("A child named %s already exists under %s." % [node_name, _scene_relative_path(root, parent_node)])
            quit(1)
            return

    var instantiated: Variant = ClassDB.instantiate(node_type)
    if instantiated == null or not (instantiated is Node):
        printerr("Class is not a Node: %s" % node_type)
        quit(1)
        return
    var new_node: Node = instantiated

    new_node.name = node_name
    parent_node.add_child(new_node)
    if new_node != root:
        new_node.owner = root

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
        "parent_path": _scene_relative_path(root, parent_node),
        "node_path": _scene_relative_path(root, new_node),
        "node_name": node_name,
        "node_type": node_type,
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
