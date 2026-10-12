def api_campaigns_panel(deps):
    request = deps["request"]
    jsonify = deps["jsonify"]
    traceback = deps["traceback"]
    _parse_optional_limit = deps["_parse_optional_limit"]
    list_campaign_summaries = deps["list_campaign_summaries"]
    try:
        q = (request.args.get("q") or "").strip()
        limit = _parse_optional_limit(request.args.get("limit"), default=None)
        campaigns = list_campaign_summaries(limit=limit, query_text=q)
        return jsonify({"ok": True, "campaigns": campaigns})
    except Exception as exc:
        print(f"[CAMPAIGNS ERROR] api_campaigns_panel failed: {exc}")
        traceback.print_exc()
        return jsonify({"ok": False, "error": str(exc), "campaigns": []}), 500


def api_campaign_details(deps):
    request = deps["request"]
    jsonify = deps["jsonify"]
    traceback = deps["traceback"]
    _parse_optional_limit = deps["_parse_optional_limit"]
    get_campaign_detail = deps["get_campaign_detail"]
    try:
        campaign_id = (request.args.get("campaign_id") or "").strip()
        limit = _parse_optional_limit(request.args.get("limit"), default=None)
        detail = get_campaign_detail(campaign_id, list_limit=limit)
        if not detail:
            return jsonify({"ok": False, "error": "Campaign not found.", "campaign": None}), 404
        return jsonify({"ok": True, "campaign": detail})
    except Exception as exc:
        print(f"[CAMPAIGNS ERROR] api_campaign_details failed: {exc}")
        traceback.print_exc()
        return jsonify({"ok": False, "error": str(exc), "campaign": None}), 500


def api_campaign_reuse(deps):
    request = deps["request"]
    jsonify = deps["jsonify"]
    traceback = deps["traceback"]
    _parse_optional_limit = deps["_parse_optional_limit"]
    get_campaign_detail = deps["get_campaign_detail"]
    build_contact_items = deps["build_contact_items"]
    try:
        campaign_id = (request.args.get("campaign_id") or "").strip()
        reuse_scope = str(request.args.get("scope") or "campaign").strip().lower()
        limit = _parse_optional_limit(request.args.get("limit"), default=None)
        detail = get_campaign_detail(campaign_id, list_limit=limit)
        if not detail:
            return jsonify({"ok": False, "error": "Campaign not found."}), 404
        if reuse_scope == "failed":
            targets = detail.get("failed_numbers") or []
        else:
            reuse_scope = "campaign"
            targets = detail.get("targets") or []
        send_target_hint = detail.get("send_target_hint") or "contacts"
        return jsonify(
            {
                "ok": True,
                "campaign_id": detail.get("campaign_id") or "",
                "reuse_scope": reuse_scope,
                "send_target": send_target_hint if send_target_hint in ("contacts", "groups") else "contacts",
                "contacts": targets,
                "contact_items": build_contact_items(targets, {}),
                "targets_total": len(targets),
            }
        )
    except Exception as exc:
        print(f"[CAMPAIGNS ERROR] api_campaign_reuse failed: {exc}")
        traceback.print_exc()
        return jsonify({"ok": False, "error": str(exc)}), 500
