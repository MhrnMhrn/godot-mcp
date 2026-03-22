extends SceneTree


func _init() -> void:
    var args := _parse_args(OS.get_cmdline_user_args())
    var updates_path := str(args.get("updates-path", "")).strip_edges()
    if updates_path.is_empty():
        printerr("Missing required argument: --updates-path")
        quit(1)
        return

    var file := FileAccess.open(updates_path, FileAccess.READ)
    if file == null:
        printerr("Could not open updates file: %s" % updates_path)
        quit(1)
        return

    var parsed_updates: Variant = JSON.parse_string(file.get_as_text())
    if parsed_updates == null or not (parsed_updates is Array):
        printerr("Updates file must contain a JSON array.")
        quit(1)
        return

    var updated_settings := []
    for index in range(parsed_updates.size()):
        var raw_update: Variant = parsed_updates[index]
        if raw_update == null or not (raw_update is Dictionary):
            printerr("Update entry %s is not an object." % index)
            quit(1)
            return

        var update: Dictionary = raw_update
        var setting_name := str(update.get("name", "")).strip_edges()
        if setting_name.is_empty():
            printerr("Update entry %s is missing a setting name." % index)
            quit(1)
            return

        var has_json_value := update.has("value")
        var has_expression := str(update.get("value_godot", "")).strip_edges() != ""
        if has_json_value == has_expression:
            printerr("Update entry %s must include exactly one of value or value_godot." % index)
            quit(1)
            return

        var next_value: Variant = update.get("value")
        if has_expression:
            var expression_text := str(update.get("value_godot", "")).strip_edges()
            var expression := Expression.new()
            var parse_error := expression.parse(expression_text, PackedStringArray())
            if parse_error != OK:
                printerr("Expression parse failed for %s with code %s." % [setting_name, parse_error])
                quit(1)
                return

            next_value = expression.execute([], null, false)
            if expression.has_execute_failed():
                printerr("Expression execution failed for %s." % setting_name)
                quit(1)
                return

        var had_previous_value := ProjectSettings.has_setting(setting_name)
        var previous_value: Variant = ProjectSettings.get_setting(setting_name, null)

        ProjectSettings.set_setting(setting_name, next_value)
        updated_settings.append({
            "name": setting_name,
            "had_previous_value": had_previous_value,
            "previous_value_type": type_string(typeof(previous_value)) if had_previous_value else "",
            "previous_value_text": var_to_str(previous_value) if had_previous_value else "",
            "current_value_type": type_string(typeof(next_value)),
            "current_value_text": var_to_str(next_value),
            "used_godot_expression": has_expression,
        })

    var save_error := ProjectSettings.save()
    if save_error != OK:
        printerr("ProjectSettings.save failed with code %s" % save_error)
        quit(1)
        return

    print(JSON.stringify({
        "updated_settings": updated_settings,
        "updated_count": updated_settings.size(),
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
