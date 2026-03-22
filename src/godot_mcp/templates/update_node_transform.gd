extends SceneTree


const NODE2D_FIELDS := ["position", "rotation", "rotation_degrees", "scale", "skew"]
const NODE3D_FIELDS := ["position", "rotation", "rotation_degrees", "scale"]
const CONTROL_FIELDS := ["position", "size", "rotation", "scale", "pivot_offset"]


func _init() -> void:
    var args := _parse_args(OS.get_cmdline_user_args())
    var scene_path := str(args.get("scene-path", "")).strip_edges()
    var node_path := str(args.get("node-path", ".")).strip_edges()
    var updates_path := str(args.get("updates-path", "")).strip_edges()

    if scene_path.is_empty():
        printerr("Missing required argument: --scene-path")
        quit(1)
        return
    if updates_path.is_empty():
        printerr("Missing required argument: --updates-path")
        quit(1)
        return

    var root := _load_scene_root(scene_path)
    if root == null:
        return

    var target := _resolve_target_node(root, node_path)
    if target == null:
        return

    var transform_kind := _detect_transform_kind(target)
    if transform_kind.is_empty():
        printerr("Transform editing is only supported for Node2D, Node3D, and Control nodes.")
        quit(1)
        return

    var file := FileAccess.open(updates_path, FileAccess.READ)
    if file == null:
        printerr("Could not open updates file: %s" % updates_path)
        quit(1)
        return

    var raw_updates: Variant = JSON.parse_string(file.get_as_text())
    if raw_updates == null or not (raw_updates is Dictionary):
        printerr("Transform updates file must contain a JSON object.")
        quit(1)
        return
    var updates: Dictionary = raw_updates

    var supported_fields := _supported_fields(transform_kind)
    var updated_fields := []
    for raw_key in updates.keys():
        var field_name := str(raw_key)
        if not supported_fields.has(field_name):
            printerr("Unsupported transform field for %s: %s" % [transform_kind, field_name])
            quit(1)
            return
        updated_fields.append(field_name)

    _apply_transform_updates(target, transform_kind, updates)

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
        "node_path": _scene_relative_path(root, target),
        "node_name": str(target.name),
        "node_type": target.get_class(),
        "transform_kind": transform_kind,
        "supported_fields": supported_fields,
        "updated_fields": updated_fields,
        "transform": _serialize_transform(target, transform_kind),
    }))
    quit()


func _load_scene_root(scene_path: String) -> Node:
    var resource := ResourceLoader.load(scene_path)
    if resource == null or not (resource is PackedScene):
        printerr("Could not load PackedScene: %s" % scene_path)
        quit(1)
        return null

    var packed_scene: PackedScene = resource
    var root := packed_scene.instantiate()
    if root == null or not (root is Node):
        printerr("PackedScene.instantiate did not return a Node root.")
        quit(1)
        return null
    return root


func _resolve_target_node(root: Node, node_path: String) -> Node:
    if node_path.is_empty() or node_path == ".":
        return root

    var found := root.get_node_or_null(node_path)
    if found == null or not (found is Node):
        printerr("Node was not found at path: %s" % node_path)
        quit(1)
        return null
    return found


func _detect_transform_kind(node: Node) -> String:
    if node is Node3D:
        return "node3d"
    if node is Control:
        return "control"
    if node is Node2D:
        return "node2d"
    return ""


func _supported_fields(transform_kind: String) -> Array:
    if transform_kind == "node2d":
        return NODE2D_FIELDS.duplicate()
    if transform_kind == "node3d":
        return NODE3D_FIELDS.duplicate()
    if transform_kind == "control":
        return CONTROL_FIELDS.duplicate()
    return []


func _apply_transform_updates(node: Node, transform_kind: String, updates: Dictionary) -> void:
    if transform_kind == "node2d":
        var node2d: Node2D = node
        if updates.has("position"):
            node2d.position = _merge_vector2(node2d.position, updates["position"], "position")
        if updates.has("rotation"):
            node2d.rotation = float(updates["rotation"])
        if updates.has("rotation_degrees"):
            node2d.rotation_degrees = float(updates["rotation_degrees"])
        if updates.has("scale"):
            node2d.scale = _merge_vector2(node2d.scale, updates["scale"], "scale")
        if updates.has("skew"):
            node2d.skew = float(updates["skew"])
        return

    if transform_kind == "node3d":
        var node3d: Node3D = node
        if updates.has("position"):
            node3d.position = _merge_vector3(node3d.position, updates["position"], "position")
        if updates.has("rotation"):
            node3d.rotation = _merge_vector3(node3d.rotation, updates["rotation"], "rotation")
        if updates.has("rotation_degrees"):
            node3d.rotation_degrees = _merge_vector3(
                node3d.rotation_degrees,
                updates["rotation_degrees"],
                "rotation_degrees"
            )
        if updates.has("scale"):
            node3d.scale = _merge_vector3(node3d.scale, updates["scale"], "scale")
        return

    var control: Control = node
    if updates.has("position"):
        control.position = _merge_vector2(control.position, updates["position"], "position")
    if updates.has("size"):
        control.size = _merge_vector2(control.size, updates["size"], "size")
    if updates.has("rotation"):
        control.rotation = float(updates["rotation"])
    if updates.has("scale"):
        control.scale = _merge_vector2(control.scale, updates["scale"], "scale")
    if updates.has("pivot_offset"):
        control.pivot_offset = _merge_vector2(control.pivot_offset, updates["pivot_offset"], "pivot_offset")


func _serialize_transform(node: Node, transform_kind: String) -> Dictionary:
    if transform_kind == "node2d":
        var node2d: Node2D = node
        return {
            "position": _vector2_to_dict(node2d.position),
            "rotation": node2d.rotation,
            "rotation_degrees": node2d.rotation_degrees,
            "scale": _vector2_to_dict(node2d.scale),
            "skew": node2d.skew,
        }

    if transform_kind == "node3d":
        var node3d: Node3D = node
        return {
            "position": _vector3_to_dict(node3d.position),
            "rotation": _vector3_to_dict(node3d.rotation),
            "rotation_degrees": _vector3_to_dict(node3d.rotation_degrees),
            "scale": _vector3_to_dict(node3d.scale),
        }

    var control: Control = node
    return {
        "position": _vector2_to_dict(control.position),
        "size": _vector2_to_dict(control.size),
        "rotation": control.rotation,
        "scale": _vector2_to_dict(control.scale),
        "pivot_offset": _vector2_to_dict(control.pivot_offset),
    }


func _merge_vector2(current: Vector2, update: Variant, field_name: String) -> Vector2:
    if update is Array:
        var values: Array = update
        if values.size() != 2:
            printerr("Transform field %s must contain exactly 2 values." % field_name)
            quit(1)
            return current
        return Vector2(float(values[0]), float(values[1]))

    if update is Dictionary:
        var values: Dictionary = update
        return Vector2(
            float(values.get("x", current.x)),
            float(values.get("y", current.y))
        )

    printerr("Transform field %s must be a dictionary or a 2-item array." % field_name)
    quit(1)
    return current


func _merge_vector3(current: Vector3, update: Variant, field_name: String) -> Vector3:
    if update is Array:
        var values: Array = update
        if values.size() != 3:
            printerr("Transform field %s must contain exactly 3 values." % field_name)
            quit(1)
            return current
        return Vector3(float(values[0]), float(values[1]), float(values[2]))

    if update is Dictionary:
        var values: Dictionary = update
        return Vector3(
            float(values.get("x", current.x)),
            float(values.get("y", current.y)),
            float(values.get("z", current.z))
        )

    printerr("Transform field %s must be a dictionary or a 3-item array." % field_name)
    quit(1)
    return current


func _vector2_to_dict(value: Vector2) -> Dictionary:
    return {"x": value.x, "y": value.y}


func _vector3_to_dict(value: Vector3) -> Dictionary:
    return {"x": value.x, "y": value.y, "z": value.z}


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
