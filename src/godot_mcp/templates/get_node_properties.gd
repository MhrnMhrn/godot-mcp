extends SceneTree


const MAX_SERIALIZE_DEPTH := 6


func _init() -> void:
    var args := _parse_args(OS.get_cmdline_user_args())
    var scene_path := str(args.get("scene-path", "")).strip_edges()
    var node_path := str(args.get("node-path", ".")).strip_edges()

    if scene_path.is_empty():
        printerr("Missing required argument: --scene-path")
        quit(1)
        return

    var root := _load_scene_root(scene_path)
    if root == null:
        return

    var target := _resolve_target_node(root, node_path)
    if target == null:
        return

    var properties := []
    for raw_entry in target.get_property_list():
        if not (raw_entry is Dictionary):
            continue

        var entry: Dictionary = raw_entry
        var property_name := str(entry.get("name", "")).strip_edges()
        if property_name.is_empty():
            continue

        var usage := int(entry.get("usage", 0))
        if usage & (PROPERTY_USAGE_GROUP | PROPERTY_USAGE_CATEGORY | PROPERTY_USAGE_SUBGROUP):
            continue

        properties.append({
            "name": property_name,
            "class_name": str(entry.get("class_name", "")),
            "type": int(entry.get("type", TYPE_NIL)),
            "type_name": type_string(int(entry.get("type", TYPE_NIL))),
            "hint": int(entry.get("hint", 0)),
            "hint_string": str(entry.get("hint_string", "")),
            "usage": usage,
            "value": _serialize_variant(target.get(property_name), 0),
        })

    print(JSON.stringify({
        "scene_path": scene_path,
        "node_path": _scene_relative_path(root, target),
        "node_name": str(target.name),
        "node_type": target.get_class(),
        "property_count": properties.size(),
        "properties": properties,
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


func _serialize_variant(value: Variant, depth: int) -> Variant:
    if depth >= MAX_SERIALIZE_DEPTH:
        return {
            "__type": type_string(typeof(value)),
            "truncated": true,
        }

    var value_type := typeof(value)
    match value_type:
        TYPE_NIL, TYPE_BOOL, TYPE_INT, TYPE_FLOAT, TYPE_STRING:
            return value
        TYPE_STRING_NAME, TYPE_NODE_PATH:
            return str(value)
        TYPE_VECTOR2, TYPE_VECTOR2I:
            return {"x": value.x, "y": value.y}
        TYPE_VECTOR3, TYPE_VECTOR3I:
            return {"x": value.x, "y": value.y, "z": value.z}
        TYPE_VECTOR4, TYPE_VECTOR4I:
            return {"x": value.x, "y": value.y, "z": value.z, "w": value.w}
        TYPE_RECT2, TYPE_RECT2I:
            return {
                "position": _serialize_variant(value.position, depth + 1),
                "size": _serialize_variant(value.size, depth + 1),
            }
        TYPE_COLOR:
            return {"r": value.r, "g": value.g, "b": value.b, "a": value.a}
        TYPE_QUATERNION:
            return {"x": value.x, "y": value.y, "z": value.z, "w": value.w}
        TYPE_PLANE:
            return {
                "normal": _serialize_variant(value.normal, depth + 1),
                "d": value.d,
            }
        TYPE_AABB:
            return {
                "position": _serialize_variant(value.position, depth + 1),
                "size": _serialize_variant(value.size, depth + 1),
            }
        TYPE_BASIS:
            return {
                "x": _serialize_variant(value.x, depth + 1),
                "y": _serialize_variant(value.y, depth + 1),
                "z": _serialize_variant(value.z, depth + 1),
            }
        TYPE_TRANSFORM2D:
            return {
                "x": _serialize_variant(value.x, depth + 1),
                "y": _serialize_variant(value.y, depth + 1),
                "origin": _serialize_variant(value.origin, depth + 1),
            }
        TYPE_TRANSFORM3D:
            return {
                "basis": _serialize_variant(value.basis, depth + 1),
                "origin": _serialize_variant(value.origin, depth + 1),
            }
        TYPE_PROJECTION:
            return {
                "__type": "Projection",
                "value": var_to_str(value),
            }
        TYPE_DICTIONARY:
            return _serialize_dictionary(value, depth + 1)
        TYPE_ARRAY:
            return _serialize_array(value, depth + 1)
        TYPE_OBJECT:
            return _serialize_object(value)
        TYPE_CALLABLE, TYPE_SIGNAL, TYPE_RID:
            return {
                "__type": type_string(value_type),
                "value": var_to_str(value),
            }
        TYPE_PACKED_BYTE_ARRAY, TYPE_PACKED_INT32_ARRAY, TYPE_PACKED_INT64_ARRAY, TYPE_PACKED_FLOAT32_ARRAY, TYPE_PACKED_FLOAT64_ARRAY, TYPE_PACKED_STRING_ARRAY, TYPE_PACKED_VECTOR2_ARRAY, TYPE_PACKED_VECTOR3_ARRAY, TYPE_PACKED_COLOR_ARRAY, TYPE_PACKED_VECTOR4_ARRAY:
            return {
                "__type": type_string(value_type),
                "values": _serialize_array(Array(value), depth + 1),
            }
        _:
            return {
                "__type": type_string(value_type),
                "value": var_to_str(value),
            }


func _serialize_array(values: Array, depth: int) -> Array:
    var serialized := []
    for item in values:
        serialized.append(_serialize_variant(item, depth))
    return serialized


func _serialize_dictionary(values: Dictionary, depth: int) -> Variant:
    var can_use_object := true
    for raw_key in values.keys():
        var key_type := typeof(raw_key)
        if key_type not in [TYPE_STRING, TYPE_STRING_NAME, TYPE_INT, TYPE_FLOAT, TYPE_BOOL, TYPE_NODE_PATH]:
            can_use_object = false
            break

    if can_use_object:
        var serialized := {}
        for raw_key in values.keys():
            serialized[str(raw_key)] = _serialize_variant(values[raw_key], depth)
        return serialized

    var entries := []
    for raw_key in values.keys():
        entries.append({
            "key": _serialize_variant(raw_key, depth),
            "value": _serialize_variant(values[raw_key], depth),
        })
    return {
        "__type": "Dictionary",
        "entries": entries,
    }


func _serialize_object(value: Variant) -> Variant:
    if value == null:
        return null
    if value is Node:
        var node: Node = value
        return {
            "__type": "Node",
            "class_name": node.get_class(),
            "name": str(node.name),
            "path": str(node.get_path()),
        }
    if value is Resource:
        var resource: Resource = value
        return {
            "__type": "Resource",
            "class_name": resource.get_class(),
            "resource_path": resource.resource_path,
        }

    var object_value: Object = value
    return {
        "__type": "Object",
        "class_name": object_value.get_class(),
        "instance_id": int(object_value.get_instance_id()),
    }


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
