extends SceneTree


const MAX_SERIALIZE_DEPTH := 6
const SKIPPED_PARAMETER_NAMES := {
    "resource_local_to_scene": true,
    "resource_name": true,
    "resource_path": true,
    "resource_scene_unique_id": true,
    "script": true,
}


func _init() -> void:
    var args = _parse_args(OS.get_cmdline_user_args())
    var scene_path = str(args.get("scene-path", "")).strip_edges()
    var node_path = str(args.get("node-path", "")).strip_edges()
    var config_path = str(args.get("config-path", "")).strip_edges()

    if scene_path.is_empty():
        printerr("Missing required argument: --scene-path")
        quit(1)
        return
    if node_path.is_empty():
        printerr("Missing required argument: --node-path")
        quit(1)
        return
    if config_path.is_empty():
        printerr("Missing required argument: --config-path")
        quit(1)
        return

    var root = _load_scene_root(scene_path)
    if root == null:
        return

    var target = root.get_node_or_null(node_path)
    if target == null or not (target is MeshInstance3D):
        printerr("MeshInstance3D node was not found at path: %s" % node_path)
        quit(1)
        return
    var mesh_instance: MeshInstance3D = target

    var config_file = FileAccess.open(config_path, FileAccess.READ)
    if config_file == null:
        printerr("Could not open config file: %s" % config_path)
        quit(1)
        return

    var raw_config: Variant = JSON.parse_string(config_file.get_as_text())
    if raw_config == null or not (raw_config is Dictionary):
        printerr("Primitive mesh edit config must contain a JSON object.")
        quit(1)
        return
    var config: Dictionary = raw_config

    var requested_mesh_type = str(config.get("mesh_type", "")).strip_edges()
    var raw_mesh_parameters: Variant = config.get("mesh_parameters", {})
    if raw_mesh_parameters == null or not (raw_mesh_parameters is Dictionary):
        printerr("`mesh_parameters` must be a JSON object when provided.")
        quit(1)
        return
    var mesh_parameters: Dictionary = raw_mesh_parameters

    var mesh_before = mesh_instance.mesh
    var mesh_type_before = ""
    if mesh_before != null:
        mesh_type_before = mesh_before.get_class()

    var editable_mesh: PrimitiveMesh = null
    if not requested_mesh_type.is_empty():
        if not ClassDB.class_exists(requested_mesh_type):
            printerr("Unknown Godot class: %s" % requested_mesh_type)
            quit(1)
            return
        if not ClassDB.can_instantiate(requested_mesh_type):
            printerr("Class cannot be instantiated: %s" % requested_mesh_type)
            quit(1)
            return
        var mesh_value: Variant = ClassDB.instantiate(requested_mesh_type)
        if mesh_value == null or not (mesh_value is PrimitiveMesh):
            printerr("Class is not a PrimitiveMesh: %s" % requested_mesh_type)
            quit(1)
            return
        editable_mesh = mesh_value
    else:
        if mesh_before == null:
            printerr("The target MeshInstance3D does not currently have a mesh. Pass `mesh_type` to assign one.")
            quit(1)
            return
        if not (mesh_before is PrimitiveMesh):
            printerr("The target mesh is not a PrimitiveMesh. Pass `mesh_type` to replace it with a primitive mesh.")
            quit(1)
            return
        var duplicated: Variant = mesh_before.duplicate()
        if duplicated == null or not (duplicated is PrimitiveMesh):
            printerr("Could not duplicate the current PrimitiveMesh for editing.")
            quit(1)
            return
        editable_mesh = duplicated

    editable_mesh.resource_local_to_scene = true
    var updated_mesh_parameters = _apply_mesh_parameter_updates(editable_mesh, mesh_parameters)
    editable_mesh.request_update()
    mesh_instance.mesh = editable_mesh

    if not _save_scene(scene_path, root):
        return

    var mesh_details = _collect_mesh_details(editable_mesh)
    print(JSON.stringify({
        "scene_path": scene_path,
        "node_path": _scene_relative_path(root, mesh_instance),
        "node_name": str(mesh_instance.name),
        "node_type": mesh_instance.get_class(),
        "mesh_type_before": mesh_type_before,
        "mesh_type_after": editable_mesh.get_class(),
        "mesh_parameters": mesh_details.get("mesh_parameters", {}),
        "supported_mesh_parameters": mesh_details.get("supported_mesh_parameters", []),
        "updated_mesh_parameters": updated_mesh_parameters,
    }))
    quit()


func _load_scene_root(scene_path: String) -> Node:
    var resource = ResourceLoader.load(scene_path)
    if resource == null or not (resource is PackedScene):
        printerr("Could not load PackedScene: %s" % scene_path)
        quit(1)
        return null

    var packed_scene: PackedScene = resource
    var root = packed_scene.instantiate()
    if root == null or not (root is Node):
        printerr("PackedScene.instantiate did not return a Node root.")
        quit(1)
        return null
    return root


func _save_scene(scene_path: String, root: Node) -> bool:
    var repacked = PackedScene.new()
    var pack_error = repacked.pack(root)
    if pack_error != OK:
        printerr("PackedScene.pack failed with code %s" % pack_error)
        quit(1)
        return false

    var save_error = ResourceSaver.save(repacked, scene_path)
    if save_error != OK:
        printerr("ResourceSaver.save failed with code %s" % save_error)
        quit(1)
        return false
    return true


func _collect_mesh_details(mesh: PrimitiveMesh) -> Dictionary:
    var supported = []
    var values = {}
    for raw_entry in mesh.get_property_list():
        if not (raw_entry is Dictionary):
            continue
        var entry: Dictionary = raw_entry
        if not _is_supported_mesh_property(entry):
            continue

        var name = str(entry.get("name", "")).strip_edges()
        var property_type = int(entry.get("type", TYPE_NIL))
        supported.append({
            "name": name,
            "class_name": str(entry.get("class_name", "")),
            "type": property_type,
            "type_name": type_string(property_type),
            "hint": int(entry.get("hint", 0)),
            "hint_string": str(entry.get("hint_string", "")),
            "usage": int(entry.get("usage", 0)),
            "settable_from_json": _is_settable_from_json(property_type),
        })
        values[name] = _serialize_variant(mesh.get(name), 0)

    supported.sort_custom(func(a: Dictionary, b: Dictionary) -> bool: return str(a.get("name", "")) < str(b.get("name", "")))
    return {
        "mesh_parameters": values,
        "supported_mesh_parameters": supported,
    }


func _apply_mesh_parameter_updates(mesh: PrimitiveMesh, updates: Dictionary) -> Array:
    var property_map = {}
    for raw_entry in mesh.get_property_list():
        if not (raw_entry is Dictionary):
            continue
        var entry: Dictionary = raw_entry
        if not _is_supported_mesh_property(entry):
            continue
        property_map[str(entry.get("name", ""))] = entry

    var updated_names = []
    for raw_key in updates.keys():
        var property_name = str(raw_key)
        if not property_map.has(property_name):
            printerr("Unsupported primitive mesh parameter: %s" % property_name)
            quit(1)
            return []

        var entry: Dictionary = property_map[property_name]
        var property_type = int(entry.get("type", TYPE_NIL))
        if not _is_settable_from_json(property_type):
            printerr("Primitive mesh parameter %s is not currently settable from JSON." % property_name)
            quit(1)
            return []

        var converted = _convert_json_to_property_value(
            updates[raw_key],
            property_type,
            mesh.get(property_name),
            property_name
        )
        mesh.set(property_name, converted)
        updated_names.append(property_name)

    updated_names.sort()
    return updated_names


func _is_supported_mesh_property(entry: Dictionary) -> bool:
    var name = str(entry.get("name", "")).strip_edges()
    if name.is_empty() or SKIPPED_PARAMETER_NAMES.has(name):
        return false

    var usage = int(entry.get("usage", 0))
    if usage & (PROPERTY_USAGE_GROUP | PROPERTY_USAGE_CATEGORY | PROPERTY_USAGE_SUBGROUP):
        return false
    if usage & PROPERTY_USAGE_READ_ONLY:
        return false
    if (usage & PROPERTY_USAGE_STORAGE) == 0 and (usage & PROPERTY_USAGE_EDITOR) == 0:
        return false
    return true


func _is_settable_from_json(property_type: int) -> bool:
    return property_type in [
        TYPE_NIL,
        TYPE_BOOL,
        TYPE_INT,
        TYPE_FLOAT,
        TYPE_STRING,
        TYPE_STRING_NAME,
        TYPE_NODE_PATH,
        TYPE_VECTOR2,
        TYPE_VECTOR2I,
        TYPE_VECTOR3,
        TYPE_VECTOR3I,
        TYPE_VECTOR4,
        TYPE_VECTOR4I,
        TYPE_RECT2,
        TYPE_RECT2I,
        TYPE_COLOR,
        TYPE_QUATERNION,
        TYPE_AABB,
        TYPE_BASIS,
        TYPE_TRANSFORM2D,
        TYPE_TRANSFORM3D,
        TYPE_DICTIONARY,
        TYPE_ARRAY,
        TYPE_PACKED_STRING_ARRAY,
    ]


func _convert_json_to_property_value(value: Variant, property_type: int, current: Variant, property_name: String) -> Variant:
    if value == null:
        if property_type in [TYPE_NIL, TYPE_OBJECT]:
            return null
        printerr("Primitive mesh parameter %s cannot be set to null." % property_name)
        quit(1)
        return current

    match property_type:
        TYPE_NIL:
            return value
        TYPE_BOOL:
            if value is bool:
                return value
            if value is int or value is float:
                return bool(value)
            if value is String:
                var lowered = String(value).to_lower()
                if lowered in ["true", "1", "yes", "on"]:
                    return true
                if lowered in ["false", "0", "no", "off"]:
                    return false
            printerr("Primitive mesh parameter %s must be a boolean." % property_name)
            quit(1)
            return current
        TYPE_INT:
            return int(value)
        TYPE_FLOAT:
            return float(value)
        TYPE_STRING:
            return str(value)
        TYPE_STRING_NAME:
            return StringName(str(value))
        TYPE_NODE_PATH:
            return NodePath(str(value))
        TYPE_VECTOR2:
            return _merge_vector2(current if current is Vector2 else Vector2.ZERO, value, property_name)
        TYPE_VECTOR2I:
            return _merge_vector2i(current if current is Vector2i else Vector2i.ZERO, value, property_name)
        TYPE_VECTOR3:
            return _merge_vector3(current if current is Vector3 else Vector3.ZERO, value, property_name)
        TYPE_VECTOR3I:
            return _merge_vector3i(current if current is Vector3i else Vector3i.ZERO, value, property_name)
        TYPE_VECTOR4:
            return _merge_vector4(current if current is Vector4 else Vector4.ZERO, value, property_name)
        TYPE_VECTOR4I:
            return _merge_vector4i(current if current is Vector4i else Vector4i.ZERO, value, property_name)
        TYPE_RECT2:
            return _merge_rect2(current if current is Rect2 else Rect2(), value, property_name)
        TYPE_RECT2I:
            return _merge_rect2i(current if current is Rect2i else Rect2i(), value, property_name)
        TYPE_COLOR:
            return _merge_color(current if current is Color else Color.WHITE, value, property_name)
        TYPE_QUATERNION:
            return _merge_quaternion(current if current is Quaternion else Quaternion.IDENTITY, value, property_name)
        TYPE_AABB:
            return _merge_aabb(current if current is AABB else AABB(), value, property_name)
        TYPE_BASIS:
            return _merge_basis(current if current is Basis else Basis.IDENTITY, value, property_name)
        TYPE_TRANSFORM2D:
            return _merge_transform2d(current if current is Transform2D else Transform2D.IDENTITY, value, property_name)
        TYPE_TRANSFORM3D:
            return _merge_transform3d(current if current is Transform3D else Transform3D.IDENTITY, value, property_name)
        TYPE_DICTIONARY:
            if value is Dictionary:
                return value
        TYPE_ARRAY:
            if value is Array:
                return value
        TYPE_PACKED_STRING_ARRAY:
            if value is Array:
                var items = PackedStringArray()
                for item in value:
                    items.append(str(item))
                return items

    printerr("Primitive mesh parameter %s uses a JSON shape that could not be converted." % property_name)
    quit(1)
    return current


func _serialize_variant(value: Variant, depth: int) -> Variant:
    if depth >= MAX_SERIALIZE_DEPTH:
        return {
            "__type": type_string(typeof(value)),
            "truncated": true,
        }

    var value_type = typeof(value)
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
        TYPE_DICTIONARY:
            var serialized_dict = {}
            for raw_key in value.keys():
                serialized_dict[str(raw_key)] = _serialize_variant(value[raw_key], depth + 1)
            return serialized_dict
        TYPE_ARRAY, TYPE_PACKED_STRING_ARRAY:
            var serialized_array = []
            for item in Array(value):
                serialized_array.append(_serialize_variant(item, depth + 1))
            return serialized_array
        TYPE_OBJECT:
            if value == null:
                return null
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
        _:
            return {
                "__type": type_string(value_type),
                "value": var_to_str(value),
            }


func _merge_vector2(current: Vector2, update: Variant, field_name: String) -> Vector2:
    if update is Array:
        var values: Array = update
        if values.size() != 2:
            printerr("Primitive mesh parameter %s must contain exactly 2 values." % field_name)
            quit(1)
            return current
        return Vector2(float(values[0]), float(values[1]))
    if update is Dictionary:
        var values: Dictionary = update
        return Vector2(float(values.get("x", current.x)), float(values.get("y", current.y)))

    printerr("Primitive mesh parameter %s must be a dictionary or 2-item array." % field_name)
    quit(1)
    return current


func _merge_vector2i(current: Vector2i, update: Variant, field_name: String) -> Vector2i:
    if update is Array:
        var values: Array = update
        if values.size() != 2:
            printerr("Primitive mesh parameter %s must contain exactly 2 values." % field_name)
            quit(1)
            return current
        return Vector2i(int(values[0]), int(values[1]))
    if update is Dictionary:
        var values: Dictionary = update
        return Vector2i(int(values.get("x", current.x)), int(values.get("y", current.y)))

    printerr("Primitive mesh parameter %s must be a dictionary or 2-item array." % field_name)
    quit(1)
    return current


func _merge_vector3(current: Vector3, update: Variant, field_name: String) -> Vector3:
    if update is Array:
        var values: Array = update
        if values.size() != 3:
            printerr("Primitive mesh parameter %s must contain exactly 3 values." % field_name)
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

    printerr("Primitive mesh parameter %s must be a dictionary or 3-item array." % field_name)
    quit(1)
    return current


func _merge_vector3i(current: Vector3i, update: Variant, field_name: String) -> Vector3i:
    if update is Array:
        var values: Array = update
        if values.size() != 3:
            printerr("Primitive mesh parameter %s must contain exactly 3 values." % field_name)
            quit(1)
            return current
        return Vector3i(int(values[0]), int(values[1]), int(values[2]))
    if update is Dictionary:
        var values: Dictionary = update
        return Vector3i(
            int(values.get("x", current.x)),
            int(values.get("y", current.y)),
            int(values.get("z", current.z))
        )

    printerr("Primitive mesh parameter %s must be a dictionary or 3-item array." % field_name)
    quit(1)
    return current


func _merge_vector4(current: Vector4, update: Variant, field_name: String) -> Vector4:
    if update is Array:
        var values: Array = update
        if values.size() != 4:
            printerr("Primitive mesh parameter %s must contain exactly 4 values." % field_name)
            quit(1)
            return current
        return Vector4(float(values[0]), float(values[1]), float(values[2]), float(values[3]))
    if update is Dictionary:
        var values: Dictionary = update
        return Vector4(
            float(values.get("x", current.x)),
            float(values.get("y", current.y)),
            float(values.get("z", current.z)),
            float(values.get("w", current.w))
        )

    printerr("Primitive mesh parameter %s must be a dictionary or 4-item array." % field_name)
    quit(1)
    return current


func _merge_vector4i(current: Vector4i, update: Variant, field_name: String) -> Vector4i:
    if update is Array:
        var values: Array = update
        if values.size() != 4:
            printerr("Primitive mesh parameter %s must contain exactly 4 values." % field_name)
            quit(1)
            return current
        return Vector4i(int(values[0]), int(values[1]), int(values[2]), int(values[3]))
    if update is Dictionary:
        var values: Dictionary = update
        return Vector4i(
            int(values.get("x", current.x)),
            int(values.get("y", current.y)),
            int(values.get("z", current.z)),
            int(values.get("w", current.w))
        )

    printerr("Primitive mesh parameter %s must be a dictionary or 4-item array." % field_name)
    quit(1)
    return current


func _merge_color(current: Color, update: Variant, field_name: String) -> Color:
    if update is Array:
        var values: Array = update
        if values.size() < 3 or values.size() > 4:
            printerr("Primitive mesh parameter %s color arrays must contain 3 or 4 values." % field_name)
            quit(1)
            return current
        return Color(
            float(values[0]),
            float(values[1]),
            float(values[2]),
            float(values[3]) if values.size() > 3 else current.a
        )
    if update is Dictionary:
        var values: Dictionary = update
        return Color(
            float(values.get("r", current.r)),
            float(values.get("g", current.g)),
            float(values.get("b", current.b)),
            float(values.get("a", current.a))
        )

    printerr("Primitive mesh parameter %s must be a dictionary or 3/4-item array." % field_name)
    quit(1)
    return current


func _merge_quaternion(current: Quaternion, update: Variant, field_name: String) -> Quaternion:
    if update is Array:
        var values: Array = update
        if values.size() != 4:
            printerr("Primitive mesh parameter %s must contain exactly 4 values." % field_name)
            quit(1)
            return current
        return Quaternion(float(values[0]), float(values[1]), float(values[2]), float(values[3]))
    if update is Dictionary:
        var values: Dictionary = update
        return Quaternion(
            float(values.get("x", current.x)),
            float(values.get("y", current.y)),
            float(values.get("z", current.z)),
            float(values.get("w", current.w))
        )

    printerr("Primitive mesh parameter %s must be a dictionary or 4-item array." % field_name)
    quit(1)
    return current


func _merge_rect2(current: Rect2, update: Variant, field_name: String) -> Rect2:
    if update is Dictionary:
        var values: Dictionary = update
        return Rect2(
            _merge_vector2(current.position, values.get("position", {}), field_name + ".position"),
            _merge_vector2(current.size, values.get("size", {}), field_name + ".size")
        )

    printerr("Primitive mesh parameter %s must be an object with position and size." % field_name)
    quit(1)
    return current


func _merge_rect2i(current: Rect2i, update: Variant, field_name: String) -> Rect2i:
    if update is Dictionary:
        var values: Dictionary = update
        return Rect2i(
            _merge_vector2i(current.position, values.get("position", {}), field_name + ".position"),
            _merge_vector2i(current.size, values.get("size", {}), field_name + ".size")
        )

    printerr("Primitive mesh parameter %s must be an object with position and size." % field_name)
    quit(1)
    return current


func _merge_aabb(current: AABB, update: Variant, field_name: String) -> AABB:
    if update is Dictionary:
        var values: Dictionary = update
        return AABB(
            _merge_vector3(current.position, values.get("position", {}), field_name + ".position"),
            _merge_vector3(current.size, values.get("size", {}), field_name + ".size")
        )

    printerr("Primitive mesh parameter %s must be an object with position and size." % field_name)
    quit(1)
    return current


func _merge_basis(current: Basis, update: Variant, field_name: String) -> Basis:
    if update is Dictionary:
        var values: Dictionary = update
        return Basis(
            _merge_vector3(current.x, values.get("x", {}), field_name + ".x"),
            _merge_vector3(current.y, values.get("y", {}), field_name + ".y"),
            _merge_vector3(current.z, values.get("z", {}), field_name + ".z")
        )

    printerr("Primitive mesh parameter %s must be an object with x, y, and z vectors." % field_name)
    quit(1)
    return current


func _merge_transform2d(current: Transform2D, update: Variant, field_name: String) -> Transform2D:
    if update is Dictionary:
        var values: Dictionary = update
        return Transform2D(
            _merge_vector2(current.x, values.get("x", {}), field_name + ".x"),
            _merge_vector2(current.y, values.get("y", {}), field_name + ".y"),
            _merge_vector2(current.origin, values.get("origin", {}), field_name + ".origin")
        )

    printerr("Primitive mesh parameter %s must be an object with x, y, and origin vectors." % field_name)
    quit(1)
    return current


func _merge_transform3d(current: Transform3D, update: Variant, field_name: String) -> Transform3D:
    if update is Dictionary:
        var values: Dictionary = update
        return Transform3D(
            _merge_basis(current.basis, values.get("basis", {}), field_name + ".basis"),
            _merge_vector3(current.origin, values.get("origin", {}), field_name + ".origin")
        )

    printerr("Primitive mesh parameter %s must be an object with basis and origin." % field_name)
    quit(1)
    return current


func _scene_relative_path(root: Node, node: Node) -> String:
    if node == root:
        return "."
    return str(root.get_path_to(node))


func _parse_args(argv: PackedStringArray) -> Dictionary:
    var parsed = {}
    var index = 0
    while index < argv.size():
        var key = argv[index]
        if not key.begins_with("--"):
            index += 1
            continue

        var name = key.substr(2)
        var value = "true"
        if index + 1 < argv.size() and not argv[index + 1].begins_with("--"):
            value = argv[index + 1]
            index += 1

        parsed[name] = value
        index += 1

    return parsed
