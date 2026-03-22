extends SceneTree


func _init() -> void:
    var args := _parse_args(OS.get_cmdline_user_args())
    var project_name := str(args.get("project-name", "")).strip_edges()
    if project_name.is_empty():
        printerr("Missing required argument: --project-name")
        quit(1)
        return

    ProjectSettings.set_setting("application/config/name", project_name)
    var save_error := ProjectSettings.save()
    if save_error != OK:
        printerr("ProjectSettings.save failed with code %s" % save_error)
        quit(1)
        return

    print(JSON.stringify({"project_name": project_name}))
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

