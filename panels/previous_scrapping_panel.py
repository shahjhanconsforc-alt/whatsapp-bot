def scrape_status(deps):
    request = deps["request"]
    jsonify = deps["jsonify"]
    list_scrap_ids = deps["list_scrap_ids"]
    scrape_state = deps["scrape_state"]
    load_scrape_rows = deps["load_scrape_rows"]
    build_scrape_summary_from_rows = deps["build_scrape_summary_from_rows"]

    selected_scrap_id = (request.args.get("scrap_id") or "").strip()
    available_scrap_ids = list_scrap_ids()

    if selected_scrap_id and selected_scrap_id != scrape_state["scrap_id"]:
        rows = load_scrape_rows(selected_scrap_id)
        summary = build_scrape_summary_from_rows(selected_scrap_id, rows)
        return jsonify(
            {
                "running": False,
                "last_error": None,
                "last_result": summary["last_result"],
                "scrap_id": selected_scrap_id,
                "groups_total": summary["groups_total"],
                "groups_done": summary["groups_done"],
                "groups_skipped": summary.get("groups_skipped", 0),
                "total_contacts": summary["total_contacts"],
                "groups": [],
                "history_rows": rows,
                "db_rows": rows,
                "logs": [],
                "started_at": summary["started_at"],
                "finished_at": summary["finished_at"],
                "available_scrap_ids": available_scrap_ids,
            }
        )

    total_contacts = sum(g.get("contacts_count", 0) for g in scrape_state["groups"])
    db_rows = load_scrape_rows(scrape_state["scrap_id"])
    return jsonify(
        {
            "running": scrape_state["running"],
            "last_error": scrape_state["last_error"],
            "last_result": scrape_state["last_result"],
            "scrap_id": scrape_state["scrap_id"],
            "groups_total": scrape_state["groups_total"],
            "groups_done": scrape_state["groups_done"],
            "groups_skipped": scrape_state["groups_skipped"],
            "total_contacts": total_contacts,
            "groups": scrape_state["groups"],
            "history_rows": db_rows,
            "db_rows": db_rows,
            "logs": scrape_state["logs"],
            "started_at": scrape_state["started_at"],
            "finished_at": scrape_state["finished_at"],
            "available_scrap_ids": available_scrap_ids,
        }
    )


def scrape_recover_start(deps):
    request = deps["request"]
    jsonify = deps["jsonify"]
    recovery_manager = deps["recovery_manager"]
    payload = request.get_json(silent=True) or {}
    mode = (payload.get("mode") or "by_scrap_id").strip().lower()
    base_scrap_id = (payload.get("scrap_id") or "").strip()
    group_name = (payload.get("group_name") or "").strip()
    ok, err = recovery_manager.start(base_scrap_id, group_name, mode=mode)
    if not ok:
        return jsonify({"ok": False, "error": err}), 409
    return jsonify({"ok": True})


def scrape_recover_status(deps):
    jsonify = deps["jsonify"]
    recovery_manager = deps["recovery_manager"]
    return jsonify(recovery_manager.status())


def api_search_scrape_groups(deps):
    request = deps["request"]
    jsonify = deps["jsonify"]
    traceback = deps["traceback"]
    search_groups_across_scrap_runs = deps["search_groups_across_scrap_runs"]
    try:
        q = (request.args.get("q") or "").strip()
        limit_raw = request.args.get("limit") or "300"
        try:
            limit = max(1, min(1000, int(limit_raw)))
        except Exception:
            limit = 300
        results = search_groups_across_scrap_runs(q, limit=limit)
        return jsonify({"ok": True, "results": results})
    except Exception as exc:
        print(f"[SCRAPE DB ERROR] api_search_scrape_groups failed: {exc}")
        traceback.print_exc()
        return jsonify({"ok": False, "error": str(exc), "results": []}), 500


def api_unique_scrape_groups(deps):
    request = deps["request"]
    jsonify = deps["jsonify"]
    traceback = deps["traceback"]
    list_unique_group_names = deps["list_unique_group_names"]
    try:
        limit_raw = request.args.get("limit") or "2000"
        try:
            limit = max(1, min(5000, int(limit_raw)))
        except Exception:
            limit = 2000
        groups = list_unique_group_names(limit=limit)
        return jsonify({"ok": True, "groups": groups})
    except Exception as exc:
        print(f"[SCRAPE DB ERROR] api_unique_scrape_groups failed: {exc}")
        traceback.print_exc()
        return jsonify({"ok": False, "error": str(exc), "groups": []}), 500
