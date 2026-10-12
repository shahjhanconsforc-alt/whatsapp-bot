def api_groups_panel(deps):
    request = deps["request"]
    jsonify = deps["jsonify"]
    traceback = deps["traceback"]
    _parse_optional_limit = deps["_parse_optional_limit"]
    list_unique_groups_from_all_contacts = deps["list_unique_groups_from_all_contacts"]
    try:
        q = (request.args.get("q") or "").strip()
        limit = _parse_optional_limit(request.args.get("limit"), default=None)
        groups = list_unique_groups_from_all_contacts(limit=limit, query_text=q)
        return jsonify({"ok": True, "groups": groups})
    except Exception as exc:
        print(f"[GROUPS ERROR] api_groups_panel failed: {exc}")
        traceback.print_exc()
        return jsonify({"ok": False, "error": str(exc), "groups": []}), 500


def api_group_details(deps):
    request = deps["request"]
    jsonify = deps["jsonify"]
    traceback = deps["traceback"]
    _parse_optional_limit = deps["_parse_optional_limit"]
    get_group_detail_from_all_contacts = deps["get_group_detail_from_all_contacts"]
    try:
        group_name = (request.args.get("group_name") or "").strip()
        limit = _parse_optional_limit(request.args.get("limit"), default=None)
        detail = get_group_detail_from_all_contacts(group_name, contact_limit=limit)
        if not detail:
            return jsonify({"ok": False, "error": "Group not found.", "group": None}), 404
        return jsonify({"ok": True, "group": detail})
    except Exception as exc:
        print(f"[GROUPS ERROR] api_group_details failed: {exc}")
        traceback.print_exc()
        return jsonify({"ok": False, "error": str(exc), "group": None}), 500


def api_group_details_bulk(deps):
    request = deps["request"]
    jsonify = deps["jsonify"]
    traceback = deps["traceback"]
    parse_selected_tables = deps["parse_selected_tables"]
    _parse_optional_limit = deps["_parse_optional_limit"]
    load_contacts_from_multiple_groups = deps["load_contacts_from_multiple_groups"]
    try:
        payload = request.get_json(silent=True) or {}
        group_names = parse_selected_tables(payload.get("group_names") or [])
        limit = _parse_optional_limit(payload.get("limit"), default=None)
        result = load_contacts_from_multiple_groups(group_names, limit=limit)
        return jsonify({"ok": True, **result})
    except Exception as exc:
        print(f"[GROUPS ERROR] api_group_details_bulk failed: {exc}")
        traceback.print_exc()
        return jsonify({"ok": False, "error": str(exc), "groups": [], "contacts": [], "contact_items": []}), 500

