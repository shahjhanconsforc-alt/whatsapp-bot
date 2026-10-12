def status(deps):
    send_state = deps["send_state"]
    app_log_lock = deps["app_log_lock"]
    app_log_state = deps["app_log_state"]
    build_contact_items = deps["build_contact_items"]
    jsonify = deps["jsonify"]
    load_profile_numbers_sequence = deps.get("_load_profile_numbers_sequence")
    generate_campaign_id = deps.get("generate_campaign_id")
    get_campaign_actions_snapshot = deps.get("_get_campaign_actions_snapshot")

    contacts = send_state["contacts"] if send_state["running"] else send_state["last_contacts"]
    statuses = (
        send_state["contact_statuses"] if send_state["running"] else send_state["last_contact_statuses"]
    )
    live_rows = send_state["live_rows"] if send_state["running"] else send_state["last_live_rows"]
    automation_action_rows = (
        send_state["automation_action_rows"]
        if send_state["running"]
        else send_state["last_automation_action_rows"]
    )
    profile_states = send_state["profile_states"] if send_state["running"] else send_state["last_profile_states"]
    if callable(get_campaign_actions_snapshot):
        try:
            campaign_actions = list(get_campaign_actions_snapshot(send_state) or [])
        except Exception:
            campaign_actions = []
    else:
        campaign_actions = []
    profile_numbers_sequence = {}
    if callable(load_profile_numbers_sequence):
        try:
            profile_numbers_sequence = dict(load_profile_numbers_sequence() or {})
        except Exception:
            profile_numbers_sequence = {}
    if send_state["running"] and str(send_state.get("campaign_id") or "").strip():
        campaign_id_value = str(send_state.get("campaign_id") or "").zfill(6)
    else:
        try:
            campaign_id_value = str(generate_campaign_id() or "").zfill(6) if callable(generate_campaign_id) else ""
        except Exception:
            fallback_campaign_id = str(send_state.get("last_campaign_id") or "").strip()
            campaign_id_value = fallback_campaign_id.zfill(6) if fallback_campaign_id else ""
    contact_items = build_contact_items(contacts, statuses)
    if send_state["running"]:
        optional_side_actions_enabled = bool(
            (send_state.get("_optional_side_action_config") or {}).get(
                "enabled",
                send_state.get("last_optional_side_actions_enabled"),
            )
        )
    else:
        optional_side_actions_enabled = bool(send_state.get("last_optional_side_actions_enabled"))
    with app_log_lock:
        logs = list(app_log_state["logs"])
    return jsonify(
        {
            "running": send_state["running"],
            "last_error": send_state["last_error"],
            "last_result": send_state["last_result"],
            "campaign_id": campaign_id_value,
            "campaign_name": (
                str(send_state["campaign_name"]).strip()
                if send_state["running"] and str(send_state["campaign_name"]).strip()
                else str(send_state["last_campaign_name"]).strip()
            ),
            "contacts": contacts,
            "contact_items": contact_items,
            "sent": send_state["sent"],
            "total": send_state["total"],
            "live_rows": live_rows,
            "automation_action_rows": automation_action_rows,
            "automation_action_event": (
                str(send_state.get("automation_action_event_text") or "").strip()
                if send_state["running"]
                else str(send_state.get("last_automation_action_event_text") or "").strip()
            ),
            "campaign_actions": campaign_actions,
            "campaign_action_event": (
                str(send_state.get("campaign_action_event_text") or "").strip()
                if send_state["running"]
                else str(send_state.get("last_campaign_action_event_text") or "").strip()
            ),
            "optional_side_actions_enabled": optional_side_actions_enabled,
            "profile_states": profile_states,
            "profile_numbers_sequence": profile_numbers_sequence,
            "cancel_requested": bool(send_state.get("cancel_requested")),
            "cancel_requested_at": str(send_state.get("cancel_requested_at") or ""),
            "pause_requested": bool(send_state.get("pause_requested")),
            "paused": bool(send_state.get("paused")),
            "pause_requested_at": str(send_state.get("pause_requested_at") or ""),
            "session_opening": bool(send_state.get("session_opening")),
            "awaiting_session_start": bool(send_state.get("awaiting_session_start")),
            "session_start_requested": bool(send_state.get("session_start_requested")),
            "session_logged_in_count": int(send_state.get("session_logged_in_count") or 0),
            "session_logged_out_count": int(send_state.get("session_logged_out_count") or 0),
            "batch_pause_active": bool(send_state.get("batch_pause_active")),
            "batch_pause_remaining_sec": int(send_state.get("batch_pause_remaining_sec") or 0),
            "batch_next_start_at": str(send_state.get("batch_next_start_at") or ""),
            "batch_pauses": dict(send_state.get("batch_pauses") or {}),
            "current_batch_no": int(send_state.get("current_batch_no") or 0),
            "total_batches": int(send_state.get("total_batches") or 0),
            "batch_min_size": int(send_state.get("last_batch_min_size") or 20),
            "batch_max_size": int(send_state.get("last_batch_max_size") or 30),
            "logs": logs[-300:],
        }
    )
