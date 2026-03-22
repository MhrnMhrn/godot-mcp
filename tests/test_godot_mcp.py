from __future__ import annotations

import json
import stat
import sys
import tempfile
import textwrap
import time
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from godot_mcp.godot import GodotController, normalize_project_subdir, pascal_case_name, snake_case_name
from godot_mcp.server import GodotMcpServer


FAKE_GODOT = textwrap.dedent(
    """\
    #!/usr/bin/env python3
    import json
    import pathlib
    import sys
    import time


    def scene_meta_path(scene_file):
        return scene_file.with_suffix(scene_file.suffix + ".meta.json")


    def load_scene_meta(scene_file):
        meta_file = scene_meta_path(scene_file)
        if not meta_file.exists():
            return {"nodes": [], "connections": []}
        return json.loads(meta_file.read_text(encoding="utf-8"))


    def save_scene_meta(scene_file, meta):
        scene_meta_path(scene_file).write_text(json.dumps(meta), encoding="utf-8")


    def scene_file_from_resource(project_dir, resource_path):
        return project_dir / resource_path.replace("res://", "", 1)


    def settings_store_path(project_dir):
        return project_dir / ".godot_mcp_fake_project_settings.json"


    def load_project_settings(project_dir):
        store = settings_store_path(project_dir)
        if not store.exists():
            return {}
        return json.loads(store.read_text(encoding="utf-8"))


    def save_project_settings(project_dir, settings):
        settings_store_path(project_dir).write_text(json.dumps(settings), encoding="utf-8")


    def detect_transform_kind(node_type):
        lowered = node_type.lower()
        if node_type == "Control" or lowered.endswith("container") or lowered in {"control", "panel", "button", "label"}:
            return "control"
        if node_type.endswith("3D") or node_type in {"Node3D"}:
            return "node3d"
        if node_type.endswith("2D") or node_type in {"Node2D", "Sprite2D"}:
            return "node2d"
        return ""


    def default_transform(node_type):
        transform_kind = detect_transform_kind(node_type)
        if transform_kind == "node2d":
            return {
                "transform_kind": "node2d",
                "transform": {
                    "position": {"x": 0.0, "y": 0.0},
                    "rotation": 0.0,
                    "rotation_degrees": 0.0,
                    "scale": {"x": 1.0, "y": 1.0},
                    "skew": 0.0,
                },
            }
        if transform_kind == "node3d":
            return {
                "transform_kind": "node3d",
                "transform": {
                    "position": {"x": 0.0, "y": 0.0, "z": 0.0},
                    "rotation": {"x": 0.0, "y": 0.0, "z": 0.0},
                    "rotation_degrees": {"x": 0.0, "y": 0.0, "z": 0.0},
                    "scale": {"x": 1.0, "y": 1.0, "z": 1.0},
                },
            }
        if transform_kind == "control":
            return {
                "transform_kind": "control",
                "transform": {
                    "position": {"x": 0.0, "y": 0.0},
                    "size": {"x": 0.0, "y": 0.0},
                    "rotation": 0.0,
                    "scale": {"x": 1.0, "y": 1.0},
                    "pivot_offset": {"x": 0.0, "y": 0.0},
                },
            }
        return {"transform_kind": "", "transform": {}}


    def supported_transform_fields(transform_kind):
        if transform_kind == "node2d":
            return ["position", "rotation", "rotation_degrees", "scale", "skew"]
        if transform_kind == "node3d":
            return ["position", "rotation", "rotation_degrees", "scale"]
        if transform_kind == "control":
            return ["position", "size", "rotation", "scale", "pivot_offset"]
        return []


    def merge_vector(current, update):
        if isinstance(update, list):
            if len(update) != len(current):
                raise ValueError("wrong vector size")
            return {key: float(update[index]) for index, key in enumerate(current.keys())}
        if isinstance(update, dict):
            merged = dict(current)
            for key in current:
                if key in update:
                    merged[key] = float(update[key])
            return merged
        raise ValueError("wrong vector payload")


    def apply_transform_update(node, updates):
        transform_kind = node.get("transform_kind", "")
        transform = dict(node.get("transform", {}))
        supported = supported_transform_fields(transform_kind)
        for key in updates:
            if key not in supported:
                raise ValueError(f"unsupported transform field {key}")

        if transform_kind == "node2d":
            if "position" in updates:
                transform["position"] = merge_vector(transform["position"], updates["position"])
            if "rotation" in updates:
                transform["rotation"] = float(updates["rotation"])
            if "rotation_degrees" in updates:
                transform["rotation_degrees"] = float(updates["rotation_degrees"])
            if "scale" in updates:
                transform["scale"] = merge_vector(transform["scale"], updates["scale"])
            if "skew" in updates:
                transform["skew"] = float(updates["skew"])
        elif transform_kind == "node3d":
            if "position" in updates:
                transform["position"] = merge_vector(transform["position"], updates["position"])
            if "rotation" in updates:
                transform["rotation"] = merge_vector(transform["rotation"], updates["rotation"])
            if "rotation_degrees" in updates:
                transform["rotation_degrees"] = merge_vector(transform["rotation_degrees"], updates["rotation_degrees"])
            if "scale" in updates:
                transform["scale"] = merge_vector(transform["scale"], updates["scale"])
        elif transform_kind == "control":
            if "position" in updates:
                transform["position"] = merge_vector(transform["position"], updates["position"])
            if "size" in updates:
                transform["size"] = merge_vector(transform["size"], updates["size"])
            if "rotation" in updates:
                transform["rotation"] = float(updates["rotation"])
            if "scale" in updates:
                transform["scale"] = merge_vector(transform["scale"], updates["scale"])
            if "pivot_offset" in updates:
                transform["pivot_offset"] = merge_vector(transform["pivot_offset"], updates["pivot_offset"])
        else:
            raise ValueError("unsupported transform kind")

        node["transform"] = transform
        return node


    def find_scene_node(meta, node_path):
        for node in meta["nodes"]:
            if node["path"] == node_path:
                return node
        return None


    def is_in_subtree(candidate_path, root_path):
        return candidate_path == root_path or candidate_path.startswith(root_path + "/")


    def user_parent_path(node):
        if node["path"] == ".":
            return ""
        return "." if not node["parent_path"] else node["parent_path"]


    def replace_path_prefix(value, old_prefix, new_prefix):
        if value == old_prefix:
            return new_prefix
        if value.startswith(old_prefix + "/"):
            return new_prefix + value[len(old_prefix):]
        return value


    def recalculate_child_indexes(meta):
        counts = {}
        for node in meta["nodes"]:
            parent_path = node["parent_path"]
            child_index = counts.get(parent_path, 0)
            node["child_index"] = child_index
            counts[parent_path] = child_index + 1


    def fake_property_entry(name, type_id, type_name, value, class_name=""):
        return {
            "name": name,
            "class_name": class_name,
            "type": type_id,
            "type_name": type_name,
            "hint": 0,
            "hint_string": "",
            "usage": 8199,
            "value": value,
        }


    def build_fake_properties(node):
        properties = [
            fake_property_entry("name", 4, "String", node["name"]),
            fake_property_entry(
                "script",
                24,
                "Object",
                None
                if not node.get("script_path")
                else {
                    "__type": "Resource",
                    "class_name": "GDScript",
                    "resource_path": node["script_path"],
                },
                class_name="Script" if node.get("script_path") else "",
            ),
        ]

        if node.get("mesh_type"):
            properties.append(
                fake_property_entry(
                    "mesh",
                    24,
                    "Object",
                    {
                        "__type": "Resource",
                        "class_name": node["mesh_type"],
                        "resource_path": "",
                    },
                    class_name=node["mesh_type"],
                )
            )

        transform_kind = node.get("transform_kind", "")
        transform = node.get("transform", {})
        for field in supported_transform_fields(transform_kind):
            value = transform.get(field)
            if isinstance(value, dict) and set(value.keys()) == {"x", "y"}:
                type_name = "Vector2"
                type_id = 5
            elif isinstance(value, dict) and set(value.keys()) == {"x", "y", "z"}:
                type_name = "Vector3"
                type_id = 9
            else:
                type_name = "float"
                type_id = 3
            properties.append(fake_property_entry(field, type_id, type_name, value))

        return properties


    def primitive_mesh_defaults(mesh_type):
        if mesh_type == "BoxMesh":
            return {
                "size": {"x": 1.0, "y": 1.0, "z": 1.0},
                "subdivide_depth": 0,
                "subdivide_height": 0,
                "subdivide_width": 0,
            }
        if mesh_type == "CylinderMesh":
            return {
                "bottom_radius": 0.5,
                "cap_bottom": True,
                "cap_top": True,
                "height": 2.0,
                "radial_segments": 64,
                "rings": 4,
                "top_radius": 0.5,
            }
        if mesh_type == "SphereMesh":
            return {
                "height": 1.0,
                "is_hemisphere": False,
                "radial_segments": 32,
                "radius": 0.5,
                "rings": 16,
            }
        if mesh_type == "CapsuleMesh":
            return {
                "height": 2.0,
                "mid_height": 1.0,
                "radial_segments": 64,
                "rings": 8,
                "radius": 0.5,
            }
        if mesh_type == "PlaneMesh":
            return {
                "center_offset": {"x": 0.0, "y": 0.0, "z": 0.0},
                "orientation": 1,
                "size": {"x": 2.0, "y": 2.0},
                "subdivide_depth": 0,
                "subdivide_width": 0,
            }
        if mesh_type == "PrismMesh":
            return {
                "left_to_right": 0.5,
                "size": {"x": 1.0, "y": 1.0, "z": 1.0},
                "subdivide_depth": 0,
                "subdivide_height": 0,
                "subdivide_width": 0,
            }
        if mesh_type == "QuadMesh":
            return {
                "center_offset": {"x": 0.0, "y": 0.0, "z": 0.0},
                "orientation": 1,
                "size": {"x": 1.0, "y": 1.0},
            }
        if mesh_type == "TorusMesh":
            return {
                "inner_radius": 0.5,
                "outer_radius": 1.0,
                "ring_segments": 32,
                "rings": 64,
            }
        return {}


    def primitive_mesh_supported_parameters(mesh_type, mesh_parameters):
        defaults = primitive_mesh_defaults(mesh_type)
        combined = dict(defaults)
        combined.update(mesh_parameters)
        supported = []
        for name, value in sorted(combined.items()):
            if isinstance(value, dict) and set(value.keys()) == {"x", "y", "z"}:
                type_id = 9
                type_name = "Vector3"
            elif isinstance(value, dict) and set(value.keys()) == {"x", "y"}:
                type_id = 5
                type_name = "Vector2"
            elif isinstance(value, bool):
                type_id = 1
                type_name = "bool"
            elif isinstance(value, int):
                type_id = 2
                type_name = "int"
            elif isinstance(value, float):
                type_id = 3
                type_name = "float"
            else:
                type_id = 4
                type_name = "String"
            supported.append(
                {
                    "name": name,
                    "class_name": "",
                    "type": type_id,
                    "type_name": type_name,
                    "hint": 0,
                    "hint_string": "",
                    "usage": 8199,
                    "settable_from_json": True,
                }
            )
        return supported


    def apply_mesh_parameter_updates(mesh_type, mesh_parameters, updates):
        supported_names = set(primitive_mesh_defaults(mesh_type).keys())
        if not supported_names:
            raise ValueError(f"unsupported primitive mesh type {mesh_type}")

        merged = json.loads(json.dumps(mesh_parameters))
        for key, value in updates.items():
            if key not in supported_names:
                raise ValueError(f"unsupported primitive mesh parameter {key}")
            current = merged.get(key)
            if isinstance(current, dict) and set(current.keys()) in ({"x", "y"}, {"x", "y", "z"}):
                merged[key] = merge_vector(current, value)
            elif isinstance(current, bool):
                merged[key] = bool(value)
            elif isinstance(current, int):
                merged[key] = int(value)
            elif isinstance(current, float):
                merged[key] = float(value)
            else:
                merged[key] = value
        return merged


    def fake_validate_scene(scene_file):
        if not scene_file.exists():
            return {
                "valid": False,
                "message": "Scene file was not found.",
                "resource_type": "",
                "node_count": 0,
                "root_node_name": "",
                "root_node_type": "",
                "connection_count": 0,
                "error": "ERROR: Fake missing scene file",
            }

        text = scene_file.read_text(encoding="utf-8")
        node_index = text.find("[node")
        sub_resource_index = text.find("[sub_resource")
        if not text.startswith("[gd_scene") or (
            node_index != -1 and sub_resource_index != -1 and sub_resource_index > node_index
        ):
            return {
                "valid": False,
                "message": "Fake scene parser rejected the file.",
                "resource_type": "",
                "node_count": 0,
                "root_node_name": "",
                "root_node_type": "",
                "connection_count": 0,
                "error": "ERROR: Fake invalid scene structure",
            }

        meta = load_scene_meta(scene_file)
        root = find_scene_node(meta, ".")
        return {
            "valid": True,
            "message": "Scene parsed successfully.",
            "resource_type": "PackedScene",
            "node_count": len(meta["nodes"]),
            "root_node_name": "" if root is None else root["name"],
            "root_node_type": "" if root is None else root["type"],
            "connection_count": len(meta.get("connections", [])),
            "error": "",
        }


    args = sys.argv[1:]
    if "--version" in args:
        print("4.5.stable.fake")
        raise SystemExit(0)

    if "--dump-extension-api-with-docs" in args:
        docs = {
            "header": {"version_full_name": "4.5.stable.fake"},
            "classes": [
                {
                    "name": "Node",
                    "inherits": "Object",
                    "brief_description": "Base class for all scene objects.",
                    "description": "Nodes are arranged in a tree. Use add_child to attach a child node.",
                    "methods": [
                        {
                            "name": "add_child",
                            "arguments": [{"name": "node", "type": "Node", "meta": "required"}],
                            "description": "Adds a child node to the current node.",
                            "hash": 0,
                            "hash_compatibility": [],
                            "is_const": False,
                            "is_static": False,
                            "is_vararg": False,
                            "is_virtual": False,
                        }
                    ],
                    "properties": [
                        {
                            "name": "name",
                            "type": "String",
                            "setter": "set_name",
                            "getter": "get_name",
                            "description": "The node name.",
                        }
                    ],
                    "signals": [
                        {
                            "name": "ready",
                            "description": "Emitted when the node is ready.",
                        }
                    ],
                    "constants": [
                        {
                            "name": "NOTIFICATION_READY",
                            "value": 13,
                            "description": "Notification emitted when the node is ready.",
                        }
                    ],
                    "enums": [],
                    "api_type": "core",
                    "is_instantiable": True,
                    "is_refcounted": False,
                },
                {
                    "name": "Timer",
                    "inherits": "Node",
                    "brief_description": "Countdown timer node.",
                    "description": "Timer can start, stop, and emit timeout when it finishes.",
                    "methods": [
                        {
                            "name": "start",
                            "arguments": [{"name": "time_sec", "type": "float", "default_value": "0.0"}],
                            "description": "Starts the timer.",
                            "hash": 0,
                            "hash_compatibility": [],
                            "is_const": False,
                            "is_static": False,
                            "is_vararg": False,
                            "is_virtual": False,
                        }
                    ],
                    "properties": [],
                    "signals": [],
                    "constants": [],
                    "enums": [],
                    "api_type": "core",
                    "is_instantiable": True,
                    "is_refcounted": False,
                },
                {
                    "name": "Sprite2D",
                    "inherits": "Node2D",
                    "brief_description": "2D sprite node.",
                    "description": "Displays a 2D texture.",
                    "methods": [],
                    "properties": [],
                    "signals": [],
                    "constants": [],
                    "enums": [],
                    "api_type": "core",
                    "is_instantiable": True,
                    "is_refcounted": False,
                },
            ],
            "builtin_classes": [],
            "builtin_class_member_offsets": [],
            "builtin_class_sizes": [],
            "global_constants": [],
            "global_enums": [],
            "native_structures": [],
            "singletons": [],
            "utility_functions": [],
        }
        pathlib.Path("extension_api.json").write_text(json.dumps(docs), encoding="utf-8")
        raise SystemExit(0)

    if "--log-file" not in args:
        print("missing --log-file", file=sys.stderr)
        raise SystemExit(2)

    if "-s" in args:
        script_name = pathlib.Path(args[args.index("-s") + 1]).name
        project_dir = pathlib.Path(args[args.index("--path") + 1])
        user_args = args[args.index("--") + 1:] if "--" in args else []
        parsed = {}
        index = 0
        while index < len(user_args):
            key = user_args[index]
            if key.startswith("--"):
                name = key[2:]
                value = "true"
                if index + 1 < len(user_args) and not user_args[index + 1].startswith("--"):
                    value = user_args[index + 1]
                    index += 1
                parsed[name] = value
            index += 1

        if script_name == "bootstrap_project.gd":
            project_file = project_dir / "project.godot"
            project_file.write_text(
                "; fake project\\n\\n[application]\\nconfig/name=\\"%s\\"\\n" % parsed["project-name"],
                encoding="utf-8",
            )
            save_project_settings(project_dir, {"application/config/name": parsed["project-name"]})
            print(json.dumps({"project_name": parsed["project-name"]}))
            raise SystemExit(0)

        if script_name == "create_scene.gd":
            scene_file = scene_file_from_resource(project_dir, parsed["scene-path"])
            scene_file.parent.mkdir(parents=True, exist_ok=True)
            scene_file.write_text(
                "[gd_scene format=3]\\n\\n[node name=\\"%s\\" type=\\"%s\\"]\\n"
                % (parsed["root-name"], parsed["root-type"]),
                encoding="utf-8",
            )
            save_scene_meta(
                scene_file,
                {
                    "nodes": [
                        {
                            "index": 0,
                            "name": parsed["root-name"],
                            "type": parsed["root-type"],
                            "path": ".",
                            "parent_path": "",
                            "owner_path": "",
                            "groups": [],
                            "child_index": 0,
                            "instance_placeholder": False,
                            "instance_scene_path": "",
                            "script_path": "",
                            "mesh_type": "",
                            "mesh_parameters": {},
                            **default_transform(parsed["root-type"]),
                        }
                    ],
                    "connections": [],
                },
            )
            print(json.dumps({"scene_path": parsed["scene-path"]}))
            raise SystemExit(0)

        if script_name == "inspect_scene.gd":
            scene_file = scene_file_from_resource(project_dir, parsed["scene-path"])
            meta = load_scene_meta(scene_file)
            print(json.dumps({"scene_path": parsed["scene-path"], **meta}))
            raise SystemExit(0)

        if script_name == "validate_scene.gd":
            scene_file = scene_file_from_resource(project_dir, parsed["scene-path"])
            validation = fake_validate_scene(scene_file)
            if validation["error"]:
                print(validation["error"], file=sys.stderr)
            print(
                json.dumps(
                    {
                        "scene_path": parsed["scene-path"],
                        "valid": validation["valid"],
                        "message": validation["message"],
                        "resource_type": validation["resource_type"],
                        "node_count": validation["node_count"],
                        "root_node_name": validation["root_node_name"],
                        "root_node_type": validation["root_node_type"],
                        "connection_count": validation["connection_count"],
                    }
                )
            )
            raise SystemExit(0)

        if script_name == "add_node.gd":
            scene_file = scene_file_from_resource(project_dir, parsed["scene-path"])
            parent_path = parsed.get("parent-path", ".")
            node_name = parsed["node-name"]
            node_type = parsed["node-type"]
            meta = load_scene_meta(scene_file)

            if parent_path not in {node["path"] for node in meta["nodes"]}:
                print("parent not found", file=sys.stderr)
                raise SystemExit(1)

            node_path = node_name if parent_path == "." else f"{parent_path}/{node_name}"
            if node_path in {node["path"] for node in meta["nodes"]}:
                print("duplicate child", file=sys.stderr)
                raise SystemExit(1)

            sibling_count = sum(1 for node in meta["nodes"] if node["parent_path"] == ("" if parent_path == "." else parent_path))
            meta["nodes"].append(
                {
                    "index": len(meta["nodes"]),
                    "name": node_name,
                    "type": node_type,
                    "path": node_path,
                    "parent_path": "" if parent_path == "." else parent_path,
                    "owner_path": "",
                    "groups": [],
                    "child_index": sibling_count,
                    "instance_placeholder": False,
                    "instance_scene_path": "",
                    "script_path": "",
                    "mesh_type": "",
                    "mesh_parameters": {},
                    **default_transform(node_type),
                }
            )
            save_scene_meta(scene_file, meta)
            scene_file.write_text(
                scene_file.read_text(encoding="utf-8")
                + "[node name=\\"%s\\" type=\\"%s\\" parent=\\"%s\\"]\\n"
                % (node_name, node_type, "." if parent_path == "." else parent_path),
                encoding="utf-8",
            )
            print(
                json.dumps(
                    {
                        "scene_path": parsed["scene-path"],
                        "parent_path": parent_path,
                        "node_path": node_path,
                        "node_name": node_name,
                        "node_type": node_type,
                    }
                )
            )
            raise SystemExit(0)

        if script_name == "add_primitive_mesh.gd":
            scene_file = scene_file_from_resource(project_dir, parsed["scene-path"])
            parent_path = parsed.get("parent-path", ".")
            node_name = parsed["node-name"]
            mesh_type = parsed["mesh-type"]
            config_path = pathlib.Path(parsed["config-path"])
            meta = load_scene_meta(scene_file)

            if not config_path.exists():
                print("config file not found", file=sys.stderr)
                raise SystemExit(1)
            if primitive_mesh_defaults(mesh_type) == {}:
                print("unsupported primitive mesh type", file=sys.stderr)
                raise SystemExit(1)
            if parent_path not in {node["path"] for node in meta["nodes"]}:
                print("parent not found", file=sys.stderr)
                raise SystemExit(1)

            node_path = node_name if parent_path == "." else f"{parent_path}/{node_name}"
            if node_path in {node["path"] for node in meta["nodes"]}:
                print("duplicate child", file=sys.stderr)
                raise SystemExit(1)

            config = json.loads(config_path.read_text(encoding="utf-8"))
            mesh_parameter_updates = config.get("mesh_parameters", {})
            transform_updates = config.get("transform", {})
            if not isinstance(mesh_parameter_updates, dict):
                print("mesh_parameters must be an object", file=sys.stderr)
                raise SystemExit(1)
            if not isinstance(transform_updates, dict):
                print("transform must be an object", file=sys.stderr)
                raise SystemExit(1)

            mesh_parameters = primitive_mesh_defaults(mesh_type)
            try:
                mesh_parameters = apply_mesh_parameter_updates(mesh_type, mesh_parameters, mesh_parameter_updates)
            except ValueError as exc:
                print(str(exc), file=sys.stderr)
                raise SystemExit(1)

            sibling_count = sum(
                1 for node in meta["nodes"] if node["parent_path"] == ("" if parent_path == "." else parent_path)
            )
            mesh_node = {
                "index": len(meta["nodes"]),
                "name": node_name,
                "type": "MeshInstance3D",
                "path": node_path,
                "parent_path": "" if parent_path == "." else parent_path,
                "owner_path": "",
                "groups": [],
                "child_index": sibling_count,
                "instance_placeholder": False,
                "instance_scene_path": "",
                "script_path": "",
                "mesh_type": mesh_type,
                "mesh_parameters": mesh_parameters,
                **default_transform("MeshInstance3D"),
            }
            if transform_updates:
                try:
                    apply_transform_update(mesh_node, transform_updates)
                except ValueError as exc:
                    print(str(exc), file=sys.stderr)
                    raise SystemExit(1)

            meta["nodes"].append(mesh_node)
            save_scene_meta(scene_file, meta)
            scene_file.write_text(
                scene_file.read_text(encoding="utf-8")
                + "# primitive mesh %s -> %s\\n" % (node_path, json.dumps(config, sort_keys=True)),
                encoding="utf-8",
            )
            print(
                json.dumps(
                    {
                        "scene_path": parsed["scene-path"],
                        "parent_path": parent_path,
                        "node_path": node_path,
                        "node_name": node_name,
                        "node_type": "MeshInstance3D",
                        "mesh_type": mesh_type,
                        "mesh_parameters": mesh_parameters,
                        "supported_mesh_parameters": primitive_mesh_supported_parameters(mesh_type, mesh_parameters),
                        "updated_mesh_parameters": sorted(mesh_parameter_updates.keys()),
                        "transform": mesh_node["transform"],
                    }
                )
            )
            raise SystemExit(0)

        if script_name == "edit_primitive_mesh.gd":
            scene_file = scene_file_from_resource(project_dir, parsed["scene-path"])
            node_path = parsed.get("node-path", ".")
            config_path = pathlib.Path(parsed["config-path"])
            meta = load_scene_meta(scene_file)

            if not config_path.exists():
                print("config file not found", file=sys.stderr)
                raise SystemExit(1)

            target = find_scene_node(meta, node_path)
            if target is None:
                print("node not found", file=sys.stderr)
                raise SystemExit(1)
            if target["type"] != "MeshInstance3D":
                print("target is not a MeshInstance3D", file=sys.stderr)
                raise SystemExit(1)

            config = json.loads(config_path.read_text(encoding="utf-8"))
            requested_mesh_type = str(config.get("mesh_type", "")).strip()
            mesh_parameter_updates = config.get("mesh_parameters", {})
            if not isinstance(mesh_parameter_updates, dict):
                print("mesh_parameters must be an object", file=sys.stderr)
                raise SystemExit(1)

            mesh_type_before = target.get("mesh_type", "")
            if requested_mesh_type:
                if primitive_mesh_defaults(requested_mesh_type) == {}:
                    print("unsupported primitive mesh type", file=sys.stderr)
                    raise SystemExit(1)
                mesh_type_after = requested_mesh_type
                mesh_parameters = primitive_mesh_defaults(mesh_type_after)
            else:
                mesh_type_after = mesh_type_before
                if not mesh_type_after:
                    print("target mesh is missing", file=sys.stderr)
                    raise SystemExit(1)
                mesh_parameters = target.get("mesh_parameters", primitive_mesh_defaults(mesh_type_after))

            try:
                mesh_parameters = apply_mesh_parameter_updates(mesh_type_after, mesh_parameters, mesh_parameter_updates)
            except ValueError as exc:
                print(str(exc), file=sys.stderr)
                raise SystemExit(1)

            target["mesh_type"] = mesh_type_after
            target["mesh_parameters"] = mesh_parameters
            save_scene_meta(scene_file, meta)
            scene_file.write_text(
                scene_file.read_text(encoding="utf-8")
                + "# edit primitive mesh %s -> %s\\n" % (node_path, json.dumps(config, sort_keys=True)),
                encoding="utf-8",
            )
            print(
                json.dumps(
                    {
                        "scene_path": parsed["scene-path"],
                        "node_path": node_path,
                        "node_name": target["name"],
                        "node_type": target["type"],
                        "mesh_type_before": mesh_type_before,
                        "mesh_type_after": mesh_type_after,
                        "mesh_parameters": mesh_parameters,
                        "supported_mesh_parameters": primitive_mesh_supported_parameters(mesh_type_after, mesh_parameters),
                        "updated_mesh_parameters": sorted(mesh_parameter_updates.keys()),
                    }
                )
            )
            raise SystemExit(0)

        if script_name == "edit_scene.gd":
            scene_file = scene_file_from_resource(project_dir, parsed["scene-path"])
            node_path = parsed.get("node-path", ".")
            changes_path = pathlib.Path(parsed["changes-path"])
            meta = load_scene_meta(scene_file)

            if not changes_path.exists():
                print("changes file not found", file=sys.stderr)
                raise SystemExit(1)

            changes = json.loads(changes_path.read_text(encoding="utf-8"))
            target = find_scene_node(meta, node_path)
            if target is None:
                print("node not found", file=sys.stderr)
                raise SystemExit(1)

            rename_requested = "new_name" in changes
            reparent_requested = "new_parent_path" in changes
            transform_requested = "transform" in changes
            delete_requested = bool(changes.get("delete", False))
            if delete_requested and (rename_requested or reparent_requested or transform_requested):
                print("delete cannot be combined", file=sys.stderr)
                raise SystemExit(1)
            if not delete_requested and not rename_requested and not reparent_requested and not transform_requested:
                print("no scene edits provided", file=sys.stderr)
                raise SystemExit(1)

            node_path_before = target["path"]
            parent_path_before = user_parent_path(target)
            node_name_before = target["name"]
            node_type = target["type"]

            if delete_requested:
                if target["path"] == ".":
                    print("cannot delete root", file=sys.stderr)
                    raise SystemExit(1)

                meta["nodes"] = [
                    node for node in meta["nodes"] if not is_in_subtree(node["path"], target["path"])
                ]
                recalculate_child_indexes(meta)
                save_scene_meta(scene_file, meta)
                scene_file.write_text(
                    scene_file.read_text(encoding="utf-8")
                    + "# delete %s\\n" % node_path_before,
                    encoding="utf-8",
                )
                print(
                    json.dumps(
                        {
                            "scene_path": parsed["scene-path"],
                            "node_path_before": node_path_before,
                            "node_path_after": None,
                            "parent_path_before": parent_path_before,
                            "parent_path_after": None,
                            "node_name_before": node_name_before,
                            "node_name_after": None,
                            "node_type": node_type,
                            "deleted": True,
                            "applied_changes": ["delete"],
                            "updated_transform_fields": [],
                            "transform_kind": "",
                            "supported_fields": [],
                            "transform": {},
                        }
                    )
                )
                raise SystemExit(0)

            applied_changes = []
            updated_transform_fields = []

            new_name = target["name"]
            if rename_requested:
                new_name = str(changes["new_name"]).strip()
                if not new_name:
                    print("empty new name", file=sys.stderr)
                    raise SystemExit(1)

            new_parent_path = target["parent_path"]
            if reparent_requested:
                requested_parent = changes.get("new_parent_path", ".")
                new_parent_path = "" if requested_parent in {"", "."} else requested_parent
                if target["path"] == ".":
                    print("cannot reparent root", file=sys.stderr)
                    raise SystemExit(1)
                parent_node = find_scene_node(meta, "." if not new_parent_path else new_parent_path)
                if parent_node is None:
                    print("parent not found", file=sys.stderr)
                    raise SystemExit(1)
                if is_in_subtree(new_parent_path or ".", target["path"]):
                    print("cannot reparent under descendant", file=sys.stderr)
                    raise SystemExit(1)
                applied_changes.append("reparent")

            final_path = "." if target["path"] == "." else (new_name if not new_parent_path else f"{new_parent_path}/{new_name}")
            if target["path"] != ".":
                for node in meta["nodes"]:
                    if node["path"] == final_path and not is_in_subtree(node["path"], target["path"]):
                        print("duplicate target path", file=sys.stderr)
                        raise SystemExit(1)

            if rename_requested:
                target["name"] = new_name
                applied_changes.append("rename")

            if target["path"] != "." and (rename_requested or reparent_requested):
                old_path = target["path"]
                for node in meta["nodes"]:
                    node["path"] = replace_path_prefix(node["path"], old_path, final_path)
                    if node["path"] == ".":
                        node["parent_path"] = ""
                    else:
                        node["parent_path"] = replace_path_prefix(node["parent_path"], old_path, final_path)
                target = find_scene_node(meta, final_path)
                target["parent_path"] = "" if not new_parent_path else new_parent_path

            if transform_requested:
                try:
                    apply_transform_update(target, changes["transform"])
                except ValueError as exc:
                    print(str(exc), file=sys.stderr)
                    raise SystemExit(1)
                updated_transform_fields = list(changes["transform"].keys())
                applied_changes.append("transform")

            recalculate_child_indexes(meta)
            save_scene_meta(scene_file, meta)
            scene_file.write_text(
                scene_file.read_text(encoding="utf-8")
                + "# edit %s -> %s\\n" % (node_path_before, json.dumps(changes, sort_keys=True)),
                encoding="utf-8",
            )
            print(
                json.dumps(
                    {
                        "scene_path": parsed["scene-path"],
                        "node_path_before": node_path_before,
                        "node_path_after": target["path"],
                        "parent_path_before": parent_path_before,
                        "parent_path_after": user_parent_path(target),
                        "node_name_before": node_name_before,
                        "node_name_after": target["name"],
                        "node_type": node_type,
                        "deleted": False,
                        "applied_changes": applied_changes,
                        "updated_transform_fields": updated_transform_fields,
                        "transform_kind": target.get("transform_kind", ""),
                        "supported_fields": supported_transform_fields(target.get("transform_kind", "")),
                        "transform": target.get("transform", {}),
                    }
                )
            )
            raise SystemExit(0)

        if script_name == "get_node_transform.gd":
            scene_file = scene_file_from_resource(project_dir, parsed["scene-path"])
            node_path = parsed.get("node-path", ".")
            meta = load_scene_meta(scene_file)

            target = None
            for node in meta["nodes"]:
                if node["path"] == node_path:
                    target = node
                    break
            if target is None:
                print("node not found", file=sys.stderr)
                raise SystemExit(1)
            if not target.get("transform_kind"):
                print("unsupported transform kind", file=sys.stderr)
                raise SystemExit(1)

            print(
                json.dumps(
                    {
                        "scene_path": parsed["scene-path"],
                        "node_path": node_path,
                        "node_name": target["name"],
                        "node_type": target["type"],
                        "transform_kind": target["transform_kind"],
                        "supported_fields": supported_transform_fields(target["transform_kind"]),
                        "transform": target["transform"],
                    }
                )
            )
            raise SystemExit(0)

        if script_name == "update_node_transform.gd":
            scene_file = scene_file_from_resource(project_dir, parsed["scene-path"])
            node_path = parsed.get("node-path", ".")
            updates_path = pathlib.Path(parsed["updates-path"])
            meta = load_scene_meta(scene_file)

            if not updates_path.exists():
                print("updates file not found", file=sys.stderr)
                raise SystemExit(1)

            updates = json.loads(updates_path.read_text(encoding="utf-8"))
            target = None
            for node in meta["nodes"]:
                if node["path"] == node_path:
                    target = node
                    break
            if target is None:
                print("node not found", file=sys.stderr)
                raise SystemExit(1)

            try:
                apply_transform_update(target, updates)
            except ValueError as exc:
                print(str(exc), file=sys.stderr)
                raise SystemExit(1)

            save_scene_meta(scene_file, meta)
            scene_file.write_text(
                scene_file.read_text(encoding="utf-8")
                + "# transform %s -> %s\\n" % (node_path, json.dumps(updates, sort_keys=True)),
                encoding="utf-8",
            )
            print(
                json.dumps(
                    {
                        "scene_path": parsed["scene-path"],
                        "node_path": node_path,
                        "node_name": target["name"],
                        "node_type": target["type"],
                        "transform_kind": target["transform_kind"],
                        "supported_fields": supported_transform_fields(target["transform_kind"]),
                        "updated_fields": list(updates.keys()),
                        "transform": target["transform"],
                    }
                )
            )
            raise SystemExit(0)

        if script_name == "get_node_properties.gd":
            scene_file = scene_file_from_resource(project_dir, parsed["scene-path"])
            node_path = parsed.get("node-path", ".")
            meta = load_scene_meta(scene_file)

            target = find_scene_node(meta, node_path)
            if target is None:
                print("node not found", file=sys.stderr)
                raise SystemExit(1)

            properties = build_fake_properties(target)
            print(
                json.dumps(
                    {
                        "scene_path": parsed["scene-path"],
                        "node_path": node_path,
                        "node_name": target["name"],
                        "node_type": target["type"],
                        "property_count": len(properties),
                        "properties": properties,
                    }
                )
            )
            raise SystemExit(0)

        if script_name == "attach_script.gd":
            scene_file = scene_file_from_resource(project_dir, parsed["scene-path"])
            node_path = parsed.get("node-path", ".")
            script_path = parsed["script-path"]
            script_file = scene_file_from_resource(project_dir, script_path)
            meta = load_scene_meta(scene_file)

            if not script_file.exists():
                print("script not found", file=sys.stderr)
                raise SystemExit(1)

            target = None
            for node in meta["nodes"]:
                if node["path"] == node_path:
                    target = node
                    break
            if target is None:
                print("node not found", file=sys.stderr)
                raise SystemExit(1)

            previous_script_path = target.get("script_path", "")
            target["script_path"] = script_path
            save_scene_meta(scene_file, meta)
            scene_file.write_text(
                scene_file.read_text(encoding="utf-8")
                + "# script %s -> %s\\n" % (node_path, script_path),
                encoding="utf-8",
            )
            print(
                json.dumps(
                    {
                        "scene_path": parsed["scene-path"],
                        "node_path": node_path,
                        "node_name": target["name"],
                        "node_type": target["type"],
                        "script_path": script_path,
                        "previous_script_path": previous_script_path,
                    }
                )
            )
            raise SystemExit(0)

        if script_name == "update_project_settings.gd":
            updates_path = pathlib.Path(parsed["updates-path"])
            if not updates_path.exists():
                print("updates file not found", file=sys.stderr)
                raise SystemExit(1)

            updates = json.loads(updates_path.read_text(encoding="utf-8"))
            settings = load_project_settings(project_dir)
            updated_settings = []
            for update in updates:
                name = update["name"]
                had_previous_value = name in settings
                previous_value = settings.get(name)
                next_value = update["value"] if "value" in update else update["value_godot"]
                settings[name] = next_value
                updated_settings.append(
                    {
                        "name": name,
                        "had_previous_value": had_previous_value,
                        "previous_value_type": type(previous_value).__name__ if had_previous_value else "",
                        "previous_value_text": repr(previous_value) if had_previous_value else "",
                        "current_value_type": type(next_value).__name__,
                        "current_value_text": repr(next_value),
                        "used_godot_expression": "value_godot" in update,
                    }
                )

            save_project_settings(project_dir, settings)
            print(json.dumps({"updated_settings": updated_settings, "updated_count": len(updated_settings)}))
            raise SystemExit(0)

    log_path = pathlib.Path(args[args.index("--log-file") + 1])
    log_path.parent.mkdir(parents=True, exist_ok=True)
    scene_arg = next((value for value in reversed(args) if value.endswith(".tscn")), "")
    target = "scene" if scene_arg else "project"
    target_value = scene_arg or "main_scene"
    if "--write-movie" in args:
        output_path = pathlib.Path(args[args.index("--write-movie") + 1])
        frame_count = 1
        if "--quit-after" in args:
            frame_count = max(1, int(args[args.index("--quit-after") + 1]))
        output_path.parent.mkdir(parents=True, exist_ok=True)
        stem = output_path.stem
        suffix = output_path.suffix or ".png"
        for frame_index in range(frame_count):
            frame_path = output_path.parent / f"{stem}{frame_index:08d}{suffix}"
            frame_path.write_bytes(f"fake frame {frame_index:08d}".encode("utf-8"))
        output_path.with_suffix(".wav").write_bytes(b"fake wav")
    log_path.write_text(
        "Godot Engine v4.5.stable.fake\\n"
        "WARNING: Fake warning from log\\n"
        "ERROR: Fake error from log\\n"
        "INFO: Fake debug line from log\\n",
        encoding="utf-8",
    )
    print("Fake stdout: running %s %s" % (target, target_value), flush=True)
    if "--write-movie" in args:
        print("Done recording movie at path: %s" % args[args.index("--write-movie") + 1], flush=True)
    print("WARNING: Fake warning from stderr", file=sys.stderr, flush=True)
    print("SCRIPT ERROR: Fake script error from stderr", file=sys.stderr, flush=True)
    time.sleep(0.3)
    raise SystemExit(0)
    """
)


class GodotControllerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.workspace = Path(self.temp_dir.name)
        self.fake_godot_path = self.workspace / "fake-godot"
        self.fake_godot_path.write_text(FAKE_GODOT, encoding="utf-8")
        self.fake_godot_path.chmod(self.fake_godot_path.stat().st_mode | stat.S_IEXEC)
        self.controller = GodotController()

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_name_normalizers(self) -> None:
        self.assertEqual(snake_case_name("Main Menu"), "main_menu")
        self.assertEqual(pascal_case_name("Main Menu"), "MainMenu")
        self.assertEqual(normalize_project_subdir("Scenes/UI"), "scenes/ui")

    def test_create_project_and_scene(self) -> None:
        result = self.controller.create_project(
            project_name="My Great Game",
            parent_directory=str(self.workspace),
            godot_executable=str(self.fake_godot_path),
        )
        project_path = Path(result["project_path"])

        self.assertTrue((project_path / "project.godot").exists())
        self.assertTrue((project_path / "scenes").exists())
        self.assertIn("4.5", result["godot_version"])

        scene = self.controller.create_scene(
            project_path=str(project_path),
            scene_name="Main Menu",
            root_type="Control",
            folder="Scenes/UI",
            godot_executable=str(self.fake_godot_path),
        )
        scene_path = Path(scene["scene_path"])
        self.assertEqual(scene["scene_resource_path"], "res://scenes/ui/main_menu.tscn")
        self.assertTrue(scene_path.exists())
        self.assertIn('type="Control"', scene_path.read_text(encoding="utf-8"))

    def test_get_project_structure(self) -> None:
        result = self.controller.create_project(
            project_name="Structure",
            parent_directory=str(self.workspace),
            godot_executable=str(self.fake_godot_path),
        )
        project_path = Path(result["project_path"])
        self.controller.create_folder(
            project_path=str(project_path),
            folder_path="addons/test_plugin",
        )
        self.controller.create_scene(
            project_path=str(project_path),
            scene_name="Main Menu",
            folder="scenes/ui",
            godot_executable=str(self.fake_godot_path),
        )

        structure = self.controller.get_project_structure(
            project_path=str(project_path),
            max_depth=3,
        )
        root_names = [entry["name"] for entry in structure["entries"]]
        self.assertEqual(structure["root_resource_path"], "res://")
        self.assertIn("project.godot", root_names)
        self.assertIn("addons", root_names)
        self.assertIn("scenes", root_names)
        self.assertIn("res://", structure["tree_text"])
        self.assertIn("main_menu.tscn", structure["tree_text"])
        self.assertGreaterEqual(structure["directory_count"], 4)
        self.assertGreaterEqual(structure["file_count"], 2)

    def test_list_resources(self) -> None:
        result = self.controller.create_project(
            project_name="Resources",
            parent_directory=str(self.workspace),
            godot_executable=str(self.fake_godot_path),
        )
        project_path = Path(result["project_path"])
        scene = self.controller.create_scene(
            project_path=str(project_path),
            scene_name="Gameplay",
            folder="scenes/ui",
            godot_executable=str(self.fake_godot_path),
        )
        self.controller.create_shader(
            project_path=str(project_path),
            shader_name="Water Ripple",
            folder="shaders/effects",
        )
        self.controller.attach_script(
            project_path=str(project_path),
            scene_path=scene["scene_path"],
            node_path=".",
            script_path="scripts/ui/root_controller.gd",
            script_code="extends Node2D\n",
            godot_executable=str(self.fake_godot_path),
        )
        textures_dir = project_path / "assets" / "ui"
        textures_dir.mkdir(parents=True, exist_ok=True)
        (textures_dir / "logo.png").write_bytes(b"fake-png")
        (textures_dir / "background.webp").write_bytes(b"fake-webp")

        resources = self.controller.list_resources(project_path=str(project_path))
        self.assertEqual(resources["resource_counts"]["scenes"], 1)
        self.assertEqual(resources["resource_counts"]["scripts"], 1)
        self.assertEqual(resources["resource_counts"]["shaders"], 1)
        self.assertEqual(resources["resource_counts"]["textures"], 2)
        self.assertEqual(resources["total_count"], 5)
        self.assertEqual(resources["scenes"][0]["resource_path"], "res://scenes/ui/gameplay.tscn")
        self.assertEqual(resources["scripts"][0]["resource_path"], "res://scripts/ui/root_controller.gd")
        self.assertEqual(resources["shaders"][0]["resource_path"], "res://shaders/effects/water_ripple.gdshader")
        texture_paths = {entry["resource_path"] for entry in resources["textures"]}
        self.assertIn("res://assets/ui/logo.png", texture_paths)
        self.assertIn("res://assets/ui/background.webp", texture_paths)

        ui_only = self.controller.list_resources(
            project_path=str(project_path),
            folder_path="assets/ui",
        )
        self.assertEqual(ui_only["resource_counts"]["textures"], 2)
        self.assertEqual(ui_only["resource_counts"]["scripts"], 0)
        self.assertEqual(ui_only["root_resource_path"], "res://assets/ui")

    def test_validate_scene(self) -> None:
        result = self.controller.create_project(
            project_name="Validator",
            parent_directory=str(self.workspace),
            godot_executable=str(self.fake_godot_path),
        )
        project_path = Path(result["project_path"])
        scene = self.controller.create_scene(
            project_path=str(project_path),
            scene_name="Gameplay",
            root_type="Control",
            godot_executable=str(self.fake_godot_path),
        )

        valid = self.controller.validate_scene(
            project_path=str(project_path),
            scene_path=scene["scene_resource_path"],
            godot_executable=str(self.fake_godot_path),
        )
        self.assertTrue(valid["valid"])
        self.assertEqual(valid["resource_type"], "PackedScene")
        self.assertEqual(valid["node_count"], 1)
        self.assertEqual(valid["root_node_name"], "Gameplay")
        self.assertEqual(valid["root_node_type"], "Control")
        self.assertEqual(valid["error_count"], 0)

        broken_scene = project_path / "scenes" / "broken_scene.tscn"
        broken_scene.write_text(
            textwrap.dedent(
                """\
                [gd_scene load_steps=2 format=3]

                [node name="Broken" type="Sprite2D"]
                texture = SubResource("AtlasTexture_fake")

                [sub_resource type="AtlasTexture" id="AtlasTexture_fake"]
                """
            ),
            encoding="utf-8",
        )

        invalid = self.controller.validate_scene(
            project_path=str(project_path),
            scene_path=str(broken_scene),
            godot_executable=str(self.fake_godot_path),
        )
        self.assertFalse(invalid["valid"])
        self.assertGreaterEqual(invalid["error_count"], 1)
        self.assertIn("Fake invalid scene structure", "\n".join(invalid["errors"]))

    def test_scene_tree_and_add_node(self) -> None:
        result = self.controller.create_project(
            project_name="Inspector",
            parent_directory=str(self.workspace),
            godot_executable=str(self.fake_godot_path),
        )
        project_path = Path(result["project_path"])
        scene = self.controller.create_scene(
            project_path=str(project_path),
            scene_name="Main Menu",
            root_type="Control",
            godot_executable=str(self.fake_godot_path),
        )

        initial_tree = self.controller.get_scene_tree(
            project_path=str(project_path),
            scene_path=scene["scene_path"],
            godot_executable=str(self.fake_godot_path),
        )
        self.assertEqual(initial_tree["node_count"], 1)
        self.assertEqual(initial_tree["nodes"][0]["path"], ".")
        self.assertEqual(initial_tree["scene_tree"][0]["name"], "MainMenu")

        first_add = self.controller.add_node(
            project_path=str(project_path),
            scene_path=scene["scene_resource_path"],
            node_type="Sprite2D",
            node_name="HeroSprite",
            godot_executable=str(self.fake_godot_path),
        )
        self.assertEqual(first_add["node_path"], "HeroSprite")

        second_add = self.controller.add_node(
            project_path=str(project_path),
            scene_path=scene["scene_path"],
            parent_path="HeroSprite",
            node_type="Timer",
            node_name="SpawnTimer",
            godot_executable=str(self.fake_godot_path),
        )
        self.assertEqual(second_add["node_path"], "HeroSprite/SpawnTimer")

        updated_tree = self.controller.get_scene_tree(
            project_path=str(project_path),
            scene_path=scene["scene_path"],
            godot_executable=str(self.fake_godot_path),
        )
        self.assertEqual(updated_tree["node_count"], 3)
        root = updated_tree["scene_tree"][0]
        self.assertEqual(root["children"][0]["name"], "HeroSprite")
        self.assertEqual(root["children"][0]["children"][0]["name"], "SpawnTimer")

    def test_get_and_update_node_transform(self) -> None:
        result = self.controller.create_project(
            project_name="Transforms",
            parent_directory=str(self.workspace),
            godot_executable=str(self.fake_godot_path),
        )
        project_path = Path(result["project_path"])
        scene = self.controller.create_scene(
            project_path=str(project_path),
            scene_name="Gameplay",
            root_type="Control",
            godot_executable=str(self.fake_godot_path),
        )
        self.controller.add_node(
            project_path=str(project_path),
            scene_path=scene["scene_path"],
            node_type="Sprite2D",
            node_name="HeroSprite",
            godot_executable=str(self.fake_godot_path),
        )

        root_transform = self.controller.get_node_transform(
            project_path=str(project_path),
            scene_path=scene["scene_resource_path"],
            node_path=".",
            godot_executable=str(self.fake_godot_path),
        )
        self.assertEqual(root_transform["transform_kind"], "control")
        self.assertIn("size", root_transform["supported_fields"])
        self.assertEqual(root_transform["transform"]["position"]["x"], 0.0)

        updated_root = self.controller.update_node_transform(
            project_path=str(project_path),
            scene_path=scene["scene_path"],
            node_path=".",
            transform={
                "position": {"x": 64, "y": 32},
                "size": {"x": 1280, "y": 720},
                "scale": {"x": 1.25, "y": 1.25},
                "rotation": 0.25,
            },
            godot_executable=str(self.fake_godot_path),
        )
        self.assertEqual(updated_root["transform"]["position"]["x"], 64.0)
        self.assertEqual(updated_root["transform"]["size"]["y"], 720.0)
        self.assertEqual(updated_root["transform"]["scale"]["x"], 1.25)
        self.assertIn("rotation", updated_root["updated_fields"])

        updated_child = self.controller.update_node_transform(
            project_path=str(project_path),
            scene_path=scene["scene_resource_path"],
            node_path="HeroSprite",
            transform={
                "position": {"x": 10, "y": 20},
                "rotation_degrees": 45,
                "scale": {"x": 2.0},
                "skew": 0.1,
            },
            godot_executable=str(self.fake_godot_path),
        )
        self.assertEqual(updated_child["transform_kind"], "node2d")
        self.assertEqual(updated_child["transform"]["position"]["y"], 20.0)
        self.assertEqual(updated_child["transform"]["rotation_degrees"], 45.0)
        self.assertEqual(updated_child["transform"]["scale"]["x"], 2.0)
        self.assertEqual(updated_child["transform"]["scale"]["y"], 1.0)
        self.assertEqual(updated_child["transform"]["skew"], 0.1)

        child_transform = self.controller.get_node_transform(
            project_path=str(project_path),
            scene_path=scene["scene_path"],
            node_path="HeroSprite",
            godot_executable=str(self.fake_godot_path),
        )
        self.assertEqual(child_transform["transform"]["position"]["x"], 10.0)
        self.assertEqual(child_transform["transform"]["rotation_degrees"], 45.0)

    def test_edit_scene_and_get_node_properties(self) -> None:
        result = self.controller.create_project(
            project_name="Scene Editing",
            parent_directory=str(self.workspace),
            godot_executable=str(self.fake_godot_path),
        )
        project_path = Path(result["project_path"])
        scene = self.controller.create_scene(
            project_path=str(project_path),
            scene_name="Gameplay",
            root_type="Control",
            godot_executable=str(self.fake_godot_path),
        )
        self.controller.add_node(
            project_path=str(project_path),
            scene_path=scene["scene_path"],
            node_type="Sprite2D",
            node_name="HeroSprite",
            godot_executable=str(self.fake_godot_path),
        )
        self.controller.add_node(
            project_path=str(project_path),
            scene_path=scene["scene_path"],
            node_type="Node2D",
            node_name="Effects",
            godot_executable=str(self.fake_godot_path),
        )
        self.controller.add_node(
            project_path=str(project_path),
            scene_path=scene["scene_path"],
            parent_path="HeroSprite",
            node_type="Timer",
            node_name="WeaponTimer",
            godot_executable=str(self.fake_godot_path),
        )
        self.controller.attach_script(
            project_path=str(project_path),
            scene_path=scene["scene_path"],
            node_path="HeroSprite",
            script_path="scripts/gameplay/hero_controller.gd",
            script_code="extends Sprite2D\n",
            godot_executable=str(self.fake_godot_path),
        )

        initial_properties = self.controller.get_node_properties(
            project_path=str(project_path),
            scene_path=scene["scene_resource_path"],
            node_path="HeroSprite",
            godot_executable=str(self.fake_godot_path),
        )
        self.assertGreaterEqual(initial_properties["property_count"], 3)
        initial_values = {
            prop["name"]: prop["value"]
            for prop in initial_properties["properties"]
        }
        self.assertEqual(initial_values["name"], "HeroSprite")
        self.assertEqual(initial_values["position"]["x"], 0.0)
        self.assertEqual(initial_values["script"]["resource_path"], "res://scripts/gameplay/hero_controller.gd")

        edited = self.controller.edit_scene(
            project_path=str(project_path),
            scene_path=scene["scene_resource_path"],
            node_path="HeroSprite",
            new_name="PlayerSprite",
            new_parent_path="Effects",
            transform={
                "position": {"x": 128, "y": 96},
                "scale": {"x": 1.5, "y": 1.5},
            },
            godot_executable=str(self.fake_godot_path),
        )
        self.assertEqual(edited["node_path_before"], "HeroSprite")
        self.assertEqual(edited["node_path_after"], "Effects/PlayerSprite")
        self.assertEqual(edited["parent_path_after"], "Effects")
        self.assertEqual(edited["node_name_after"], "PlayerSprite")
        self.assertFalse(edited["deleted"])
        self.assertIn("rename", edited["applied_changes"])
        self.assertIn("reparent", edited["applied_changes"])
        self.assertIn("transform", edited["applied_changes"])
        self.assertIn("position", edited["updated_transform_fields"])
        self.assertEqual(edited["transform"]["position"]["y"], 96.0)

        updated_tree = self.controller.get_scene_tree(
            project_path=str(project_path),
            scene_path=scene["scene_path"],
            godot_executable=str(self.fake_godot_path),
        )
        node_paths = {node["path"] for node in updated_tree["nodes"]}
        self.assertIn("Effects/PlayerSprite", node_paths)
        self.assertIn("Effects/PlayerSprite/WeaponTimer", node_paths)

        updated_properties = self.controller.get_node_properties(
            project_path=str(project_path),
            scene_path=scene["scene_path"],
            node_path="Effects/PlayerSprite",
            godot_executable=str(self.fake_godot_path),
        )
        updated_values = {
            prop["name"]: prop["value"]
            for prop in updated_properties["properties"]
        }
        self.assertEqual(updated_values["name"], "PlayerSprite")
        self.assertEqual(updated_values["position"]["x"], 128.0)
        self.assertEqual(updated_values["scale"]["x"], 1.5)

        deleted = self.controller.edit_scene(
            project_path=str(project_path),
            scene_path=scene["scene_path"],
            node_path="Effects/PlayerSprite/WeaponTimer",
            delete=True,
            godot_executable=str(self.fake_godot_path),
        )
        self.assertTrue(deleted["deleted"])
        self.assertIsNone(deleted["node_path_after"])

        final_tree = self.controller.get_scene_tree(
            project_path=str(project_path),
            scene_path=scene["scene_resource_path"],
            godot_executable=str(self.fake_godot_path),
        )
        final_paths = {node["path"] for node in final_tree["nodes"]}
        self.assertNotIn("Effects/PlayerSprite/WeaponTimer", final_paths)

    def test_add_and_edit_primitive_mesh(self) -> None:
        result = self.controller.create_project(
            project_name="Blockout",
            parent_directory=str(self.workspace),
            godot_executable=str(self.fake_godot_path),
        )
        project_path = Path(result["project_path"])
        scene = self.controller.create_scene(
            project_path=str(project_path),
            scene_name="Greybox",
            root_type="Node3D",
            godot_executable=str(self.fake_godot_path),
        )
        self.controller.add_node(
            project_path=str(project_path),
            scene_path=scene["scene_path"],
            node_type="Node3D",
            node_name="Blockout",
            godot_executable=str(self.fake_godot_path),
        )

        added = self.controller.add_primitive_mesh(
            project_path=str(project_path),
            scene_path=scene["scene_resource_path"],
            parent_path="Blockout",
            mesh_type="BoxMesh",
            node_name="FloorBlock",
            mesh_parameters={
                "size": {"x": 8, "y": 1, "z": 12},
                "subdivide_width": 2,
            },
            transform={
                "position": {"x": 4, "y": 0.5, "z": -2},
                "scale": {"x": 1.5, "y": 1.0, "z": 0.5},
            },
            godot_executable=str(self.fake_godot_path),
        )
        self.assertEqual(added["node_path"], "Blockout/FloorBlock")
        self.assertEqual(added["node_type"], "MeshInstance3D")
        self.assertEqual(added["mesh_type"], "BoxMesh")
        self.assertEqual(added["mesh_parameters"]["size"]["x"], 8.0)
        self.assertEqual(added["mesh_parameters"]["size"]["z"], 12.0)
        self.assertEqual(added["mesh_parameters"]["subdivide_width"], 2)
        self.assertIn("size", added["updated_mesh_parameters"])
        self.assertEqual(added["transform"]["position"]["y"], 0.5)
        self.assertEqual(added["transform"]["scale"]["z"], 0.5)

        replaced = self.controller.edit_primitive_mesh(
            project_path=str(project_path),
            scene_path=scene["scene_path"],
            node_path="Blockout/FloorBlock",
            mesh_type="CylinderMesh",
            mesh_parameters={
                "height": 6,
                "bottom_radius": 1.5,
                "top_radius": 1.0,
                "radial_segments": 12,
            },
            godot_executable=str(self.fake_godot_path),
        )
        self.assertEqual(replaced["mesh_type_before"], "BoxMesh")
        self.assertEqual(replaced["mesh_type_after"], "CylinderMesh")
        self.assertEqual(replaced["mesh_parameters"]["height"], 6.0)
        self.assertEqual(replaced["mesh_parameters"]["bottom_radius"], 1.5)
        self.assertEqual(replaced["mesh_parameters"]["top_radius"], 1.0)
        self.assertEqual(replaced["mesh_parameters"]["cap_top"], True)
        self.assertIn("height", replaced["updated_mesh_parameters"])

        tuned = self.controller.edit_primitive_mesh(
            project_path=str(project_path),
            scene_path=scene["scene_resource_path"],
            node_path="Blockout/FloorBlock",
            mesh_parameters={
                "height": 7.5,
                "cap_top": False,
            },
            godot_executable=str(self.fake_godot_path),
        )
        self.assertEqual(tuned["mesh_type_before"], "CylinderMesh")
        self.assertEqual(tuned["mesh_type_after"], "CylinderMesh")
        self.assertEqual(tuned["mesh_parameters"]["height"], 7.5)
        self.assertEqual(tuned["mesh_parameters"]["cap_top"], False)

        mesh_properties = self.controller.get_node_properties(
            project_path=str(project_path),
            scene_path=scene["scene_path"],
            node_path="Blockout/FloorBlock",
            godot_executable=str(self.fake_godot_path),
        )
        property_values = {prop["name"]: prop["value"] for prop in mesh_properties["properties"]}
        self.assertEqual(property_values["mesh"]["class_name"], "CylinderMesh")

    def test_create_folder_and_shader(self) -> None:
        result = self.controller.create_project(
            project_name="Shaders",
            parent_directory=str(self.workspace),
            godot_executable=str(self.fake_godot_path),
        )
        project_path = Path(result["project_path"])

        folder = self.controller.create_folder(
            project_path=str(project_path),
            folder_path="Shaders/UI FX",
        )
        self.assertTrue(Path(folder["folder_path"]).exists())
        self.assertEqual(folder["folder_resource_path"], "res://shaders/ui_fx")
        self.assertTrue(folder["created"])

        shader = self.controller.create_shader(
            project_path=str(project_path),
            shader_name="Water Ripple",
            folder="Shaders/UI FX",
            shader_type="canvas_item",
        )
        shader_path = Path(shader["shader_path"])
        self.assertTrue(shader_path.exists())
        self.assertEqual(shader["shader_resource_path"], "res://shaders/ui_fx/water_ripple.gdshader")
        self.assertTrue(shader["created_from_template"])
        self.assertTrue(shader["known_shader_type"])
        self.assertIn("shader_type canvas_item;", shader_path.read_text(encoding="utf-8"))

        custom_source = "shader_type spatial;\n\nvoid fragment() {\n\tALBEDO = vec3(1.0);\n}\n"
        custom_shader = self.controller.create_shader(
            project_path=str(project_path),
            shader_name="Custom Outline.gdshader",
            folder="shaders/materials",
            shader_type="spatial",
            shader_code=custom_source,
        )
        custom_path = Path(custom_shader["shader_path"])
        self.assertTrue(custom_path.exists())
        self.assertEqual(custom_shader["shader_resource_path"], "res://shaders/materials/custom_outline.gdshader")
        self.assertFalse(custom_shader["created_from_template"])
        self.assertEqual(custom_path.read_text(encoding="utf-8"), custom_source)

    def test_attach_script_to_node(self) -> None:
        result = self.controller.create_project(
            project_name="Scripts",
            parent_directory=str(self.workspace),
            godot_executable=str(self.fake_godot_path),
        )
        project_path = Path(result["project_path"])
        scene = self.controller.create_scene(
            project_path=str(project_path),
            scene_name="Gameplay",
            root_type="Control",
            godot_executable=str(self.fake_godot_path),
        )
        self.controller.add_node(
            project_path=str(project_path),
            scene_path=scene["scene_path"],
            node_type="Sprite2D",
            node_name="HeroSprite",
            godot_executable=str(self.fake_godot_path),
        )

        attached = self.controller.attach_script(
            project_path=str(project_path),
            scene_path=scene["scene_resource_path"],
            node_path="HeroSprite",
            script_name="Hero Controller",
            folder="Scripts/Gameplay",
            godot_executable=str(self.fake_godot_path),
        )
        attached_path = Path(attached["script_path"])
        self.assertEqual(attached["node_path"], "HeroSprite")
        self.assertEqual(attached["script_resource_path"], "res://scripts/gameplay/hero_controller.gd")
        self.assertTrue(attached["created_script"])
        self.assertTrue(attached["created_from_template"])
        self.assertFalse(attached["replaced_existing_script"])
        self.assertTrue(attached_path.exists())
        self.assertIn("extends Sprite2D", attached_path.read_text(encoding="utf-8"))

        root_source = "extends Control\n\nfunc _ready() -> void:\n\tprint(\"ready\")\n"
        root_script = self.controller.attach_script(
            project_path=str(project_path),
            scene_path=scene["scene_path"],
            node_path=".",
            script_path="scripts/ui/root_controller.gd",
            script_code=root_source,
            godot_executable=str(self.fake_godot_path),
        )
        root_path = Path(root_script["script_path"])
        self.assertEqual(root_script["node_path"], ".")
        self.assertEqual(root_script["script_resource_path"], "res://scripts/ui/root_controller.gd")
        self.assertTrue(root_script["created_script"])
        self.assertFalse(root_script["created_from_template"])
        self.assertEqual(root_path.read_text(encoding="utf-8"), root_source)

    def test_update_project_settings(self) -> None:
        result = self.controller.create_project(
            project_name="Settings",
            parent_directory=str(self.workspace),
            godot_executable=str(self.fake_godot_path),
        )
        project_path = Path(result["project_path"])

        updated = self.controller.update_project_settings(
            project_path=str(project_path),
            settings=[
                {"name": "application/config/name", "value": "Renamed Project"},
                {"name": "display/window/size/viewport_width", "value": 1280},
                {"name": "display/window/size/viewport_height", "value": 720},
            ],
            godot_executable=str(self.fake_godot_path),
        )

        settings_store = project_path / ".godot_mcp_fake_project_settings.json"
        self.assertTrue(settings_store.exists())
        stored = json.loads(settings_store.read_text(encoding="utf-8"))
        self.assertEqual(updated["updated_count"], 3)
        self.assertEqual(stored["application/config/name"], "Renamed Project")
        self.assertEqual(stored["display/window/size/viewport_width"], 1280)
        self.assertEqual(stored["display/window/size/viewport_height"], 720)

    def test_docs_search_uses_local_cache(self) -> None:
        fuzzy = self.controller.search_docs(
            query="add child node",
            godot_executable=str(self.fake_godot_path),
        )
        self.assertGreaterEqual(fuzzy["total_matches"], 1)
        self.assertTrue(Path(fuzzy["docs_cache_path"]).exists())
        self.assertEqual(fuzzy["results"][0]["kind"], "method")
        self.assertEqual(fuzzy["results"][0]["class_name"], "Node")
        self.assertEqual(fuzzy["results"][0]["name"], "add_child")

        exact = self.controller.search_docs(
            class_name="Timer",
            member_name="start",
            member_type="method",
            godot_executable=str(self.fake_godot_path),
        )
        self.assertGreaterEqual(exact["total_matches"], 1)
        self.assertEqual(exact["results"][0]["class_name"], "Timer")
        self.assertEqual(exact["results"][0]["name"], "start")

    def test_start_and_run_return_process_info(self) -> None:
        result = self.controller.create_project(
            project_name="Runner",
            parent_directory=str(self.workspace),
            godot_executable=str(self.fake_godot_path),
        )
        project_path = Path(result["project_path"])
        scene = self.controller.create_scene(
            project_path=str(project_path),
            scene_name="Gameplay",
            godot_executable=str(self.fake_godot_path),
        )

        project_run = self.controller.run_project(
            project_path=str(project_path),
            godot_executable=str(self.fake_godot_path),
        )
        start_result = self.controller.start_project(
            project_path=str(project_path),
            godot_executable=str(self.fake_godot_path),
        )
        run_result = self.controller.run_scene(
            project_path=str(project_path),
            scene_path=scene["scene_path"],
            godot_executable=str(self.fake_godot_path),
        )

        time.sleep(0.1)
        self.assertGreater(project_run["pid"], 0)
        self.assertGreater(start_result["pid"], 0)
        self.assertGreater(run_result["pid"], 0)
        self.assertTrue(Path(project_run["log_path"]).exists())
        self.assertTrue(Path(start_result["log_path"]).exists())
        self.assertTrue(Path(run_result["log_path"]).exists())
        self.assertIn("--log-file", project_run["command"])
        self.assertIn("--log-file", start_result["command"])
        self.assertIn("--log-file", run_result["command"])

    def test_screenshot_captures_last_frame(self) -> None:
        result = self.controller.create_project(
            project_name="Screenshots",
            parent_directory=str(self.workspace),
            godot_executable=str(self.fake_godot_path),
        )
        project_path = Path(result["project_path"])
        scene = self.controller.create_scene(
            project_path=str(project_path),
            scene_name="Gameplay",
            set_as_main_scene=True,
            godot_executable=str(self.fake_godot_path),
        )

        captured = self.controller.screenshot(
            project_path=str(project_path),
            scene_path=scene["scene_resource_path"],
            capture_seconds=0.2,
            fps=10,
            godot_executable=str(self.fake_godot_path),
        )
        screenshot_path = Path(captured["screenshot_path"])
        self.assertEqual(captured["run_target"], "scene")
        self.assertEqual(captured["frame_count"], 2)
        self.assertEqual(captured["frame_index"], 1)
        self.assertTrue(screenshot_path.exists())
        self.assertEqual(screenshot_path.read_bytes(), b"fake frame 00000001")

        screenshots_dir = screenshot_path.parent
        self.assertEqual(list(screenshots_dir.glob("*00000000.png")), [])
        self.assertEqual(list(screenshots_dir.glob("*00000001.png")), [])
        self.assertEqual(list(screenshots_dir.glob("*.wav")), [])

    def test_run_with_capture_collects_output_and_debug(self) -> None:
        result = self.controller.create_project(
            project_name="Capture",
            parent_directory=str(self.workspace),
            godot_executable=str(self.fake_godot_path),
        )
        project_path = Path(result["project_path"])
        scene = self.controller.create_scene(
            project_path=str(project_path),
            scene_name="Gameplay",
            set_as_main_scene=True,
            godot_executable=str(self.fake_godot_path),
        )

        project_capture = self.controller.run_with_capture(
            project_path=str(project_path),
            capture_seconds=0.05,
            max_output_chars=4000,
            godot_executable=str(self.fake_godot_path),
        )
        self.assertEqual(project_capture["run_target"], "project")
        self.assertTrue(project_capture["terminated_after_capture"])
        self.assertIn("Fake stdout: running project", project_capture["stdout"])
        self.assertGreaterEqual(project_capture["debug_output"]["warning_count"], 1)
        self.assertGreaterEqual(project_capture["debug_output"]["error_count"], 1)
        self.assertIn("Fake warning from log", project_capture["log_output"])

        scene_capture = self.controller.run_with_capture(
            project_path=str(project_path),
            scene_path=scene["scene_resource_path"],
            headless=True,
            capture_seconds=0.05,
            max_output_chars=4000,
            godot_executable=str(self.fake_godot_path),
        )
        self.assertEqual(scene_capture["run_target"], "scene")
        self.assertEqual(scene_capture["scene_resource_path"], scene["scene_resource_path"])
        self.assertIn("Fake stdout: running scene", scene_capture["stdout"])
        self.assertTrue(Path(scene_capture["log_path"]).exists())


class GodotServerTests(unittest.TestCase):
    def test_tools_are_listed(self) -> None:
        server = GodotMcpServer()
        response = server.handle_message({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
        self.assertIsNotNone(response)
        tools = response["result"]["tools"]
        tool_names = {tool["name"] for tool in tools}
        self.assertIn("godot_create_project", tool_names)
        self.assertIn("godot_run_project", tool_names)
        self.assertIn("godot_run_scene", tool_names)
        self.assertIn("godot_run_with_capture", tool_names)
        self.assertIn("godot_screenshot", tool_names)
        self.assertIn("godot_create_folder", tool_names)
        self.assertIn("godot_get_project_structure", tool_names)
        self.assertIn("godot_list_resources", tool_names)
        self.assertIn("godot_create_shader", tool_names)
        self.assertIn("godot_update_project_settings", tool_names)
        self.assertIn("godot_attach_script", tool_names)
        self.assertIn("godot_get_scene_tree", tool_names)
        self.assertIn("godot_validate_scene", tool_names)
        self.assertIn("godot_add_node", tool_names)
        self.assertIn("godot_add_primitive_mesh", tool_names)
        self.assertIn("godot_edit_primitive_mesh", tool_names)
        self.assertIn("godot_edit_scene", tool_names)
        self.assertIn("godot_get_node_properties", tool_names)
        self.assertIn("godot_get_node_transform", tool_names)
        self.assertIn("godot_update_node_transform", tool_names)
        self.assertIn("godot_search_docs", tool_names)

    def test_initialize(self) -> None:
        server = GodotMcpServer()
        response = server.handle_message(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {"protocolVersion": "2024-11-05"},
            }
        )
        self.assertEqual(response["result"]["serverInfo"]["name"], "godot-mcp")
        self.assertIn("tools", response["result"]["capabilities"])
        self.assertIn("resources", response["result"]["capabilities"])

    def test_resource_discovery_lists_resources_and_templates(self) -> None:
        server = GodotMcpServer()

        resources_response = server.handle_message({"jsonrpc": "2.0", "id": 1, "method": "resources/list"})
        self.assertIsNotNone(resources_response)
        resources = resources_response["result"]["resources"]
        resource_uris = {resource["uri"] for resource in resources}
        self.assertIn("godot://server/tools", resource_uris)
        self.assertIn("godot://server/guide", resource_uris)

        templates_response = server.handle_message(
            {"jsonrpc": "2.0", "id": 2, "method": "resources/templates/list"}
        )
        self.assertIsNotNone(templates_response)
        templates = templates_response["result"]["resourceTemplates"]
        template_uris = {template["uriTemplate"] for template in templates}
        self.assertIn("godot://tool/{name}", template_uris)

    def test_resources_read_catalog_and_tool_detail(self) -> None:
        server = GodotMcpServer()

        catalog_response = server.handle_message(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "resources/read",
                "params": {"uri": "godot://server/tools"},
            }
        )
        self.assertIsNotNone(catalog_response)
        catalog_contents = catalog_response["result"]["contents"][0]
        self.assertEqual(catalog_contents["mimeType"], "application/json")
        catalog = json.loads(catalog_contents["text"])
        tool_names = {tool["name"] for tool in catalog["tools"]}
        self.assertIn("godot_add_node", tool_names)
        self.assertIn("godot_add_primitive_mesh", tool_names)

        tool_response = server.handle_message(
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "resources/read",
                "params": {"uri": "godot://tool/godot_add_primitive_mesh"},
            }
        )
        self.assertIsNotNone(tool_response)
        tool_contents = tool_response["result"]["contents"][0]
        self.assertEqual(tool_contents["mimeType"], "application/json")
        tool_detail = json.loads(tool_contents["text"])
        self.assertEqual(tool_detail["name"], "godot_add_primitive_mesh")
        self.assertIn("PrimitiveMesh", tool_detail["description"])


if __name__ == "__main__":
    unittest.main()
