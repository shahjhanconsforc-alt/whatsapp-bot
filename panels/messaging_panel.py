from pathlib import Path
from datetime import datetime
from urllib.parse import quote
import json
import os


_RANGE_CONFIG_STATE_DEFAULTS = {
    "last_batch_min_size": 20,
    "last_batch_max_size": 30,
    "last_random_message_enabled": True,
    "last_message_panel_count": 1,
    "last_random_attachment_enabled": True,
    "last_media_count_min": 1,
    "last_media_count_max": 1,
    "last_random_attachment_delay_enabled": True,
    "last_attachment_delay_min": 0,
    "last_attachment_delay_max": 30,
    "last_random_search_result_delay_enabled": True,
    "last_search_result_delay_min": 1,
    "last_search_result_delay_max": 4,
    "last_random_click_delay_enabled": True,
    "last_click_delay_min_ms": 150,
    "last_click_delay_max_ms": 900,
    "last_random_send_delay_enabled": True,
    "last_send_delay_min": 0,
    "last_send_delay_max": 30,
    "last_typing_pause_chars_min": 10,
    "last_typing_pause_chars_max": 20,
    "last_typing_pause_delay_min": 2000,
    "last_typing_pause_delay_max": 5000,
    "last_typing_pause_delay_unit": "ms",
    "last_remove_chars_during_typing_enabled": True,
    "last_remove_chars_times_min": 3,
    "last_remove_chars_times_max": 7,
    "last_remove_chars_count_min": 1,
    "last_remove_chars_count_max": 3,
    "last_optional_side_actions_enabled": True,
    "last_side_action_chance_percent": 20,
    "last_side_action_pause_min_ms": 700,
    "last_side_action_pause_max_ms": 2000,
    "last_random_batch_size_enabled": True,
    "last_random_batch_start_enabled": True,
    "last_batch_start_min_minutes": 3,
    "last_batch_start_max_minutes": 6,
    "last_profiles_numbers": 1,
    "last_random_profile_pick_enabled": True,
    "last_selected_sms_ids": [],
}


def _clone_range_config_defaults():
    cloned = {}
    for key, value in _RANGE_CONFIG_STATE_DEFAULTS.items():
        if isinstance(value, list):
            cloned[key] = list(value)
        elif isinstance(value, dict):
            cloned[key] = dict(value)
        else:
            cloned[key] = value
    return cloned


def _range_config_file_path():
    data_dir = Path(__file__).resolve().parent.parent / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir / "saved_configurations.txt"


def _coerce_range_bool(value, default=False):
    if isinstance(value, bool):
        return value
    text = str(value or "").strip().lower()
    if text in ("1", "true", "yes", "on"):
        return True
    if text in ("0", "false", "no", "off"):
        return False
    return bool(default)


def _coerce_range_int(value, default, min_value, max_value):
    try:
        parsed = int(value)
    except Exception:
        parsed = int(default)
    return max(int(min_value), min(int(max_value), parsed))


def _normalize_saved_sms_ids(values, max_items=100):
    if not isinstance(values, list):
        return []
    normalized = []
    for item in values:
        try:
            sms_id = int(item)
        except Exception:
            continue
        if sms_id <= 0 or sms_id in normalized:
            continue
        normalized.append(sms_id)
        if len(normalized) >= max(1, int(max_items or 100)):
            break
    return normalized


def _normalize_saved_range_config(raw):
    defaults = _clone_range_config_defaults()
    source = dict(raw or {}) if isinstance(raw, dict) else {}
    normalized = _clone_range_config_defaults()

    selected_sms_ids = _normalize_saved_sms_ids(
        source.get("last_selected_sms_ids", source.get("selected_sms_ids", []))
    )
    normalized["last_selected_sms_ids"] = selected_sms_ids
    normalized["last_message_panel_count"] = _coerce_range_int(
        source.get(
            "last_message_panel_count",
            source.get("message_panel_count", max(1, len(selected_sms_ids) or 1)),
        ),
        max(1, len(selected_sms_ids) or 1),
        1,
        100,
    )
    if selected_sms_ids:
        normalized["last_message_panel_count"] = min(100, len(selected_sms_ids))

    normalized["last_random_message_enabled"] = _coerce_range_bool(
        source.get(
            "last_random_message_enabled",
            source.get("random_message_enabled", defaults["last_random_message_enabled"]),
        ),
        defaults["last_random_message_enabled"],
    )
    normalized["last_random_attachment_enabled"] = _coerce_range_bool(
        source.get(
            "last_random_attachment_enabled",
            source.get("random_attachment_enabled", defaults["last_random_attachment_enabled"]),
        ),
        defaults["last_random_attachment_enabled"],
    )
    media_min = _coerce_range_int(
        source.get("last_media_count_min", source.get("media_count_min", defaults["last_media_count_min"])),
        defaults["last_media_count_min"],
        1,
        200,
    )
    media_max = _coerce_range_int(
        source.get("last_media_count_max", source.get("media_count_max", defaults["last_media_count_max"])),
        defaults["last_media_count_max"],
        1,
        200,
    )
    if media_max < media_min:
        media_min, media_max = media_max, media_min
    normalized["last_media_count_min"] = media_min
    normalized["last_media_count_max"] = media_max

    normalized["last_random_attachment_delay_enabled"] = _coerce_range_bool(
        source.get(
            "last_random_attachment_delay_enabled",
            source.get(
                "random_attachment_delay_enabled",
                defaults["last_random_attachment_delay_enabled"],
            ),
        ),
        defaults["last_random_attachment_delay_enabled"],
    )
    attachment_delay_min = _coerce_range_int(
        source.get(
            "last_attachment_delay_min",
            source.get("attachment_delay_min", defaults["last_attachment_delay_min"]),
        ),
        defaults["last_attachment_delay_min"],
        0,
        3600,
    )
    attachment_delay_max = _coerce_range_int(
        source.get(
            "last_attachment_delay_max",
            source.get("attachment_delay_max", defaults["last_attachment_delay_max"]),
        ),
        defaults["last_attachment_delay_max"],
        0,
        3600,
    )
    if attachment_delay_max < attachment_delay_min:
        attachment_delay_min, attachment_delay_max = (
            attachment_delay_max,
            attachment_delay_min,
        )
    normalized["last_attachment_delay_min"] = attachment_delay_min
    normalized["last_attachment_delay_max"] = attachment_delay_max

    normalized["last_random_search_result_delay_enabled"] = _coerce_range_bool(
        source.get(
            "last_random_search_result_delay_enabled",
            source.get(
                "random_search_result_delay_enabled",
                defaults["last_random_search_result_delay_enabled"],
            ),
        ),
        defaults["last_random_search_result_delay_enabled"],
    )
    search_result_delay_min = _coerce_range_int(
        source.get(
            "last_search_result_delay_min",
            source.get("search_result_delay_min", defaults["last_search_result_delay_min"]),
        ),
        defaults["last_search_result_delay_min"],
        0,
        3600,
    )
    search_result_delay_max = _coerce_range_int(
        source.get(
            "last_search_result_delay_max",
            source.get("search_result_delay_max", defaults["last_search_result_delay_max"]),
        ),
        defaults["last_search_result_delay_max"],
        0,
        3600,
    )
    if search_result_delay_max < search_result_delay_min:
        search_result_delay_min, search_result_delay_max = (
            search_result_delay_max,
            search_result_delay_min,
        )
    normalized["last_search_result_delay_min"] = search_result_delay_min
    normalized["last_search_result_delay_max"] = search_result_delay_max

    normalized["last_random_click_delay_enabled"] = _coerce_range_bool(
        source.get(
            "last_random_click_delay_enabled",
            source.get("random_click_delay_enabled", defaults["last_random_click_delay_enabled"]),
        ),
        defaults["last_random_click_delay_enabled"],
    )
    click_delay_min_ms = _coerce_range_int(
        source.get(
            "last_click_delay_min_ms",
            source.get("click_delay_min_ms", defaults["last_click_delay_min_ms"]),
        ),
        defaults["last_click_delay_min_ms"],
        0,
        60000,
    )
    click_delay_max_ms = _coerce_range_int(
        source.get(
            "last_click_delay_max_ms",
            source.get("click_delay_max_ms", defaults["last_click_delay_max_ms"]),
        ),
        defaults["last_click_delay_max_ms"],
        0,
        60000,
    )
    if click_delay_max_ms < click_delay_min_ms:
        click_delay_min_ms, click_delay_max_ms = click_delay_max_ms, click_delay_min_ms
    normalized["last_click_delay_min_ms"] = click_delay_min_ms
    normalized["last_click_delay_max_ms"] = click_delay_max_ms

    normalized["last_random_send_delay_enabled"] = _coerce_range_bool(
        source.get(
            "last_random_send_delay_enabled",
            source.get("random_send_delay_enabled", defaults["last_random_send_delay_enabled"]),
        ),
        defaults["last_random_send_delay_enabled"],
    )
    send_delay_min = _coerce_range_int(
        source.get("last_send_delay_min", source.get("send_delay_min", defaults["last_send_delay_min"])),
        defaults["last_send_delay_min"],
        0,
        3600,
    )
    send_delay_max = _coerce_range_int(
        source.get("last_send_delay_max", source.get("send_delay_max", defaults["last_send_delay_max"])),
        defaults["last_send_delay_max"],
        0,
        3600,
    )
    if send_delay_max < send_delay_min:
        send_delay_min, send_delay_max = send_delay_max, send_delay_min
    normalized["last_send_delay_min"] = send_delay_min
    normalized["last_send_delay_max"] = send_delay_max

    typing_chars_min = _coerce_range_int(
        source.get(
            "last_typing_pause_chars_min",
            source.get("typing_pause_chars_min", defaults["last_typing_pause_chars_min"]),
        ),
        defaults["last_typing_pause_chars_min"],
        0,
        1000,
    )
    typing_chars_max = _coerce_range_int(
        source.get(
            "last_typing_pause_chars_max",
            source.get("typing_pause_chars_max", defaults["last_typing_pause_chars_max"]),
        ),
        defaults["last_typing_pause_chars_max"],
        0,
        1000,
    )
    if typing_chars_max < typing_chars_min:
        typing_chars_min, typing_chars_max = typing_chars_max, typing_chars_min
    normalized["last_typing_pause_chars_min"] = typing_chars_min
    normalized["last_typing_pause_chars_max"] = typing_chars_max

    typing_delay_unit = str(
        source.get(
            "last_typing_pause_delay_unit",
            source.get("typing_pause_delay_unit", defaults["last_typing_pause_delay_unit"]),
        )
        or defaults["last_typing_pause_delay_unit"]
    ).strip().lower()
    raw_typing_delay_min = source.get(
        "last_typing_pause_delay_min",
        source.get("typing_pause_delay_min"),
    )
    raw_typing_delay_max = source.get(
        "last_typing_pause_delay_max",
        source.get("typing_pause_delay_max"),
    )
    using_legacy_typing_delay_seconds = (
        typing_delay_unit != "ms"
        and (raw_typing_delay_min is not None or raw_typing_delay_max is not None)
    )
    if raw_typing_delay_min is None:
        raw_typing_delay_min = defaults["last_typing_pause_delay_min"]
    if raw_typing_delay_max is None:
        raw_typing_delay_max = defaults["last_typing_pause_delay_max"]
    typing_delay_min = _coerce_range_int(
        raw_typing_delay_min,
        defaults["last_typing_pause_delay_min"],
        0,
        3600000,
    )
    typing_delay_max = _coerce_range_int(
        raw_typing_delay_max,
        defaults["last_typing_pause_delay_max"],
        0,
        3600000,
    )
    if using_legacy_typing_delay_seconds:
        typing_delay_min = max(0, min(3600000, typing_delay_min * 1000))
        typing_delay_max = max(0, min(3600000, typing_delay_max * 1000))
    if typing_delay_max < typing_delay_min:
        typing_delay_min, typing_delay_max = typing_delay_max, typing_delay_min
    normalized["last_typing_pause_delay_min"] = typing_delay_min
    normalized["last_typing_pause_delay_max"] = typing_delay_max
    normalized["last_typing_pause_delay_unit"] = "ms"

    normalized["last_remove_chars_during_typing_enabled"] = _coerce_range_bool(
        source.get(
            "last_remove_chars_during_typing_enabled",
            source.get(
                "remove_chars_during_typing_enabled",
                defaults["last_remove_chars_during_typing_enabled"],
            ),
        ),
        defaults["last_remove_chars_during_typing_enabled"],
    )
    remove_chars_times_min = _coerce_range_int(
        source.get(
            "last_remove_chars_times_min",
            source.get("remove_chars_times_min", defaults["last_remove_chars_times_min"]),
        ),
        defaults["last_remove_chars_times_min"],
        0,
        100,
    )
    remove_chars_times_max = _coerce_range_int(
        source.get(
            "last_remove_chars_times_max",
            source.get("remove_chars_times_max", defaults["last_remove_chars_times_max"]),
        ),
        defaults["last_remove_chars_times_max"],
        0,
        100,
    )
    if remove_chars_times_max < remove_chars_times_min:
        remove_chars_times_min, remove_chars_times_max = (
            remove_chars_times_max,
            remove_chars_times_min,
        )
    normalized["last_remove_chars_times_min"] = remove_chars_times_min
    normalized["last_remove_chars_times_max"] = remove_chars_times_max

    remove_chars_count_min = _coerce_range_int(
        source.get(
            "last_remove_chars_count_min",
            source.get("remove_chars_count_min", defaults["last_remove_chars_count_min"]),
        ),
        defaults["last_remove_chars_count_min"],
        0,
        1000,
    )
    remove_chars_count_max = _coerce_range_int(
        source.get(
            "last_remove_chars_count_max",
            source.get("remove_chars_count_max", defaults["last_remove_chars_count_max"]),
        ),
        defaults["last_remove_chars_count_max"],
        0,
        1000,
    )
    if remove_chars_count_max < remove_chars_count_min:
        remove_chars_count_min, remove_chars_count_max = (
            remove_chars_count_max,
            remove_chars_count_min,
        )
    normalized["last_remove_chars_count_min"] = remove_chars_count_min
    normalized["last_remove_chars_count_max"] = remove_chars_count_max

    normalized["last_optional_side_actions_enabled"] = _coerce_range_bool(
        source.get(
            "last_optional_side_actions_enabled",
            source.get("optional_side_actions_enabled", defaults["last_optional_side_actions_enabled"]),
        ),
        defaults["last_optional_side_actions_enabled"],
    )
    side_action_chance_percent = _coerce_range_int(
        source.get(
            "last_side_action_chance_percent",
            source.get("side_action_chance_percent", defaults["last_side_action_chance_percent"]),
        ),
        defaults["last_side_action_chance_percent"],
        0,
        100,
    )
    side_action_pause_min_ms = _coerce_range_int(
        source.get(
            "last_side_action_pause_min_ms",
            source.get("side_action_pause_min_ms", defaults["last_side_action_pause_min_ms"]),
        ),
        defaults["last_side_action_pause_min_ms"],
        0,
        60000,
    )
    side_action_pause_max_ms = _coerce_range_int(
        source.get(
            "last_side_action_pause_max_ms",
            source.get("side_action_pause_max_ms", defaults["last_side_action_pause_max_ms"]),
        ),
        defaults["last_side_action_pause_max_ms"],
        0,
        60000,
    )
    if side_action_pause_max_ms < side_action_pause_min_ms:
        side_action_pause_min_ms, side_action_pause_max_ms = (
            side_action_pause_max_ms,
            side_action_pause_min_ms,
        )
    normalized["last_side_action_chance_percent"] = side_action_chance_percent
    normalized["last_side_action_pause_min_ms"] = side_action_pause_min_ms
    normalized["last_side_action_pause_max_ms"] = side_action_pause_max_ms

    normalized["last_random_batch_size_enabled"] = _coerce_range_bool(
        source.get(
            "last_random_batch_size_enabled",
            source.get("random_batch_size_enabled", defaults["last_random_batch_size_enabled"]),
        ),
        defaults["last_random_batch_size_enabled"],
    )
    batch_min = _coerce_range_int(
        source.get("last_batch_min_size", source.get("batch_min_size", defaults["last_batch_min_size"])),
        defaults["last_batch_min_size"],
        1,
        500,
    )
    batch_max = _coerce_range_int(
        source.get("last_batch_max_size", source.get("batch_max_size", defaults["last_batch_max_size"])),
        defaults["last_batch_max_size"],
        1,
        500,
    )
    if batch_max < batch_min:
        batch_min, batch_max = batch_max, batch_min
    normalized["last_batch_min_size"] = batch_min
    normalized["last_batch_max_size"] = batch_max

    normalized["last_random_batch_start_enabled"] = _coerce_range_bool(
        source.get(
            "last_random_batch_start_enabled",
            source.get("random_batch_start_enabled", defaults["last_random_batch_start_enabled"]),
        ),
        defaults["last_random_batch_start_enabled"],
    )
    batch_start_min = _coerce_range_int(
        source.get(
            "last_batch_start_min_minutes",
            source.get("batch_start_min_minutes", defaults["last_batch_start_min_minutes"]),
        ),
        defaults["last_batch_start_min_minutes"],
        0,
        120,
    )
    batch_start_max = _coerce_range_int(
        source.get(
            "last_batch_start_max_minutes",
            source.get("batch_start_max_minutes", defaults["last_batch_start_max_minutes"]),
        ),
        defaults["last_batch_start_max_minutes"],
        0,
        120,
    )
    if batch_start_max < batch_start_min:
        batch_start_min, batch_start_max = batch_start_max, batch_start_min
    normalized["last_batch_start_min_minutes"] = batch_start_min
    normalized["last_batch_start_max_minutes"] = batch_start_max

    normalized["last_profiles_numbers"] = _coerce_range_int(
        source.get("last_profiles_numbers", source.get("profiles_numbers", defaults["last_profiles_numbers"])),
        defaults["last_profiles_numbers"],
        1,
        100,
    )
    normalized["last_random_profile_pick_enabled"] = _coerce_range_bool(
        source.get(
            "last_random_profile_pick_enabled",
            source.get("random_profile_pick_enabled", defaults["last_random_profile_pick_enabled"]),
        ),
        defaults["last_random_profile_pick_enabled"],
    )

    return normalized


def _save_range_config_to_txt(config):
    normalized = _normalize_saved_range_config(config)
    path = _range_config_file_path()
    path.write_text(json.dumps(normalized, indent=2), encoding="utf-8")
    return normalized, path


def _load_range_config_from_txt(create_if_missing=False):
    path = _range_config_file_path()
    defaults = _clone_range_config_defaults()
    if not path.exists():
        if create_if_missing:
            try:
                path.write_text(json.dumps(defaults, indent=2), encoding="utf-8")
            except Exception:
                pass
        return defaults
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        raw = {}
    normalized = _normalize_saved_range_config(raw)
    if create_if_missing or normalized != raw:
        try:
            path.write_text(json.dumps(normalized, indent=2), encoding="utf-8")
        except Exception:
            pass
    return normalized


def _apply_saved_range_config_to_send_state(send_state, config=None, create_if_missing=False):
    normalized = (
        _load_range_config_from_txt(create_if_missing=create_if_missing)
        if config is None
        else _normalize_saved_range_config(config)
    )
    for key, value in normalized.items():
        if isinstance(value, list):
            send_state[key] = list(value)
        elif isinstance(value, dict):
            send_state[key] = dict(value)
        else:
            send_state[key] = value
    return normalized


def _load_sms_messages_from_db(get_db_connection, limit=100):
    rows = []
    try:
        db_conn = get_db_connection()
        cur = db_conn.cursor()
        cur.execute(
            """
            SELECT message
            FROM sms_messages
            WHERE message IS NOT NULL
            ORDER BY id ASC
            LIMIT %s
            """,
            (max(1, int(limit or 100)),),
        )
        fetched = cur.fetchall() or []
        for item in fetched:
            text = ""
            try:
                text = str((item[0] if item else "") or "").strip()
            except Exception:
                text = ""
            if text:
                rows.append(text)
        try:
            cur.close()
        except Exception:
            pass
        try:
            db_conn.close()
        except Exception:
            pass
    except Exception:
        return []
    return rows


def _load_sms_message_rows_from_db(get_db_connection, limit=500):
    rows = []
    try:
        db_conn = get_db_connection()
        cur = db_conn.cursor()
        cur.execute(
            """
            SELECT id, title, message
            FROM sms_messages
            WHERE message IS NOT NULL
            ORDER BY id ASC
            LIMIT %s
            """,
            (max(1, int(limit or 500)),),
        )
        fetched = cur.fetchall() or []
        for item in fetched:
            try:
                sms_id = int(item[0])
            except Exception:
                continue
            title = str((item[1] if len(item) > 1 else "") or "").strip()
            message = str((item[2] if len(item) > 2 else "") or "").strip()
            if not message:
                continue
            rows.append({"id": sms_id, "title": title, "message": message})
        try:
            cur.close()
        except Exception:
            pass
        try:
            db_conn.close()
        except Exception:
            pass
    except Exception:
        return []
    return rows


def _dashboard_safe_int(value, default=0):
    try:
        return int(value)
    except Exception:
        return int(default)


def _load_front_dashboard_summary(deps, send_state):
    get_db_schema = deps["get_db_schema"]
    list_group_tables = deps["list_group_tables"]
    get_tables_info = deps["get_tables_info"]

    summary = {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "db_connected": False,
        "db_error": "",
        "connection": {
            "host": str(os.getenv("PGHOST", "localhost") or "localhost"),
            "port": str(os.getenv("PGPORT", "5432") or "5432"),
            "database": str(os.getenv("PGDATABASE", "whatsapp_db") or "whatsapp_db"),
            "user": str(os.getenv("PGUSER", "postgres") or "postgres"),
            "schema": "",
        },
        "table_count": 0,
        "tables_with_phone": 0,
        "table_rows_total": 0,
        "phone_rows_total": 0,
        "all_contacts_total": 0,
        "group_metadata_total": 0,
        "sms_sent_total": 0,
        "sms_not_sent_total": 0,
        "sms_messages_total": 0,
        "tables": [],
    }

    try:
        summary["connection"]["schema"] = str(get_db_schema() or "").strip()
    except Exception:
        summary["connection"]["schema"] = ""

    try:
        # Keep the front dashboard focused on core tables, not the generated group_* tables.
        table_names = [
            name
            for name in list(list_group_tables() or [])
            if not str(name or "").strip().lower().startswith("group_")
        ]
        raw_tables = list(get_tables_info(table_names) or []) if table_names else []
        table_info = []
        for item in raw_tables:
            current = dict(item or {})
            current["table"] = str(current.get("table") or "").strip()
            current["columns"] = list(current.get("columns") or [])
            current["columns_count"] = _dashboard_safe_int(
                current.get("columns_count"),
                default=len(current["columns"]),
            )
            current["row_count"] = _dashboard_safe_int(current.get("row_count"))
            current["phone_count"] = _dashboard_safe_int(current.get("phone_count"))
            current["phone_column"] = str(current.get("phone_column") or "").strip()
            table_info.append(current)
        table_info.sort(
            key=lambda item: (
                -_dashboard_safe_int(item.get("row_count")),
                str(item.get("table") or "").lower(),
            )
        )
        summary["db_connected"] = True
        summary["tables"] = table_info
        summary["table_count"] = len(table_info)
        summary["tables_with_phone"] = sum(1 for item in table_info if item.get("phone_column"))
        summary["table_rows_total"] = sum(_dashboard_safe_int(item.get("row_count")) for item in table_info)
        summary["phone_rows_total"] = sum(_dashboard_safe_int(item.get("phone_count")) for item in table_info)
        table_map = {str(item.get("table") or ""): item for item in table_info}
        summary["all_contacts_total"] = _dashboard_safe_int((table_map.get("all_contacts") or {}).get("phone_count"))
        summary["group_metadata_total"] = _dashboard_safe_int((table_map.get("group_metadata") or {}).get("row_count"))
        summary["sms_sent_total"] = _dashboard_safe_int((table_map.get("sms_sent") or {}).get("row_count"))
        summary["sms_not_sent_total"] = _dashboard_safe_int((table_map.get("sms_not_sent") or {}).get("row_count"))
        summary["sms_messages_total"] = _dashboard_safe_int((table_map.get("sms_messages") or {}).get("row_count"))
    except Exception as exc:
        summary["db_error"] = str(exc or "").strip() or "Could not load database summary."

    return summary


def _reset_send_state(send_state):
    send_state["last_message"] = ""
    send_state["last_messages"] = [""] * 100
    send_state["last_delay"] = "0"
    send_state["last_country_filter"] = ""
    send_state["last_filename"] = ""
    send_state["last_attachment_names"] = []
    send_state["last_resend"] = False
    send_state["last_source_type"] = "file"
    send_state["last_send_target"] = "contacts"
    send_state["last_selected_tables"] = []
    send_state["last_group_filter_name"] = ""
    send_state["last_group_filter_names"] = []
    send_state["last_selected_contacts"] = []
    send_state["contacts"] = []
    send_state["last_contacts"] = []
    send_state["contact_statuses"] = {}
    send_state["last_contact_statuses"] = {}
    send_state["last_error"] = None
    send_state["last_result"] = None
    send_state["last_failed"] = []
    send_state["failed"] = []
    send_state["sent"] = 0
    send_state["total"] = 0
    send_state["campaign_id"] = ""
    send_state["last_campaign_id"] = ""
    send_state["campaign_name"] = ""
    send_state["last_campaign_name"] = ""
    send_state["live_rows"] = []
    send_state["last_live_rows"] = []
    send_state["profile_states"] = []
    send_state["last_profile_states"] = []
    send_state["batch_pause_active"] = False
    send_state["batch_pause_remaining_sec"] = 0
    send_state["batch_next_start_at"] = ""
    send_state["pause_requested"] = False
    send_state["paused"] = False
    send_state["pause_requested_at"] = ""
    send_state["cancel_requested"] = False
    send_state["cancel_requested_at"] = ""
    send_state["session_opening"] = False
    send_state["awaiting_session_start"] = False
    send_state["session_start_requested"] = False
    send_state["session_logged_in_count"] = 0
    send_state["session_logged_out_count"] = 0
    send_state["current_batch_no"] = 0
    send_state["total_batches"] = 0
    for key, value in _clone_range_config_defaults().items():
        send_state[key] = value
    send_state["_active_send_contexts"] = []


def index(deps):
    request = deps["request"]
    send_state = deps["send_state"]
    scrape_state = deps["scrape_state"]
    app_log_lock = deps["app_log_lock"]
    app_log_state = deps["app_log_state"]
    recovery_manager = deps["recovery_manager"]
    _reset_scrape_state = deps["_reset_scrape_state"]
    groups_joining_panel = deps.get("groups_joining_panel")
    render_template = deps["render_template"]
    get_db_connection = deps["get_db_connection"]
    generate_campaign_id = deps["generate_campaign_id"]
    split_campaign_name_base_and_suffix = deps["_split_campaign_name_base_and_suffix"]

    keep = request.args.get("keep") == "1"
    if not send_state["running"] and not keep:
        _reset_send_state(send_state)
        _apply_saved_range_config_to_send_state(send_state, create_if_missing=True)
        with app_log_lock:
            app_log_state["logs"] = []
    if not scrape_state["running"] and not keep:
        _reset_scrape_state()
    if not keep and groups_joining_panel:
        groups_joining_panel.reset_if_idle()
    if not keep:
        recovery_manager.reset_if_idle()
    sms_catalog = _load_sms_message_rows_from_db(get_db_connection, limit=500)
    selected_sms_ids = list(send_state.get("last_selected_sms_ids") or [])
    valid_sms_ids = {
        int(item.get("id"))
        for item in sms_catalog
        if item.get("id") is not None
    }
    selected_sms_ids = [sms_id for sms_id in selected_sms_ids if sms_id in valid_sms_ids]
    if not selected_sms_ids and sms_catalog:
        selected_sms_ids = [int(item.get("id")) for item in sms_catalog if item.get("id") is not None]
    send_state["last_selected_sms_ids"] = list(selected_sms_ids)
    send_state["last_message_panel_count"] = min(100, max(1, len(selected_sms_ids) or 1))
    sms_catalog_map = {}
    for item in sms_catalog:
        try:
            sms_id = int(item.get("id"))
        except Exception:
            continue
        sms_catalog_map[str(sms_id)] = str(item.get("message") or "")
    active_campaign_name = (
        str(send_state.get("campaign_name") or "").strip()
        if send_state["running"] and str(send_state.get("campaign_name") or "").strip()
        else str(send_state.get("last_campaign_name") or "").strip()
    )
    try:
        campaign_name_input_value, _ = split_campaign_name_base_and_suffix(
            active_campaign_name or "campaign",
            default_value="campaign",
        )
    except Exception:
        campaign_name_input_value = "campaign"
    campaign_name_input_value = str(campaign_name_input_value or "campaign").strip() or "campaign"
    if send_state["running"] and str(send_state.get("campaign_id") or "").strip():
        campaign_id_display_value = str(send_state.get("campaign_id") or "").zfill(6)
    else:
        try:
            campaign_id_display_value = str(generate_campaign_id() or "").zfill(6)
        except Exception:
            fallback_campaign_id = str(send_state.get("last_campaign_id") or "").strip()
            campaign_id_display_value = fallback_campaign_id.zfill(6) if fallback_campaign_id else ""
    try:
        existing_messages = list(send_state.get("last_messages") or [])
    except Exception:
        existing_messages = []
    has_any_message = any(str(x or "").strip() for x in existing_messages)
    if not has_any_message:
        seeded = _load_sms_messages_from_db(get_db_connection, limit=100)
        if seeded:
            message_slots = [""] * 100
            for idx, text in enumerate(seeded[:100]):
                message_slots[idx] = text
            send_state["last_messages"] = message_slots
            send_state["last_message"] = message_slots[0] if message_slots and message_slots[0] else ""
    dashboard_summary = _load_front_dashboard_summary(deps, send_state)
    return render_template(
        "index.html",
        state=send_state,
        keep=keep,
        sms_catalog=sms_catalog,
        sms_catalog_map=sms_catalog_map,
        selected_sms_ids=selected_sms_ids,
        campaign_name_input_value=campaign_name_input_value,
        campaign_id_display_value=campaign_id_display_value,
        dashboard_summary=dashboard_summary,
    )


def reset(deps):
    send_state = deps["send_state"]
    scrape_state = deps["scrape_state"]
    app_log_lock = deps["app_log_lock"]
    app_log_state = deps["app_log_state"]
    recovery_manager = deps["recovery_manager"]
    _reset_scrape_state = deps["_reset_scrape_state"]
    groups_joining_panel = deps.get("groups_joining_panel")
    flash = deps["flash"]
    redirect = deps["redirect"]
    url_for = deps["url_for"]

    if send_state["running"]:
        flash("Cannot reset while sending is in progress.")
        return redirect(url_for("index", keep=1))
    if scrape_state["running"]:
        flash("Cannot reset while scraping is in progress.")
        return redirect(url_for("index", keep=1))
    if groups_joining_panel and groups_joining_panel.is_running():
        flash("Cannot reset while group joining is in progress.")
        return redirect(url_for("index", keep=1))
    _reset_send_state(send_state)
    with app_log_lock:
        app_log_state["logs"] = []
    _reset_scrape_state()
    if groups_joining_panel:
        groups_joining_panel.reset_if_idle()
    recovery_manager.reset_if_idle()
    flash("")
    return redirect(url_for("index"))


def api_range_config_save(deps):
    request = deps["request"]
    jsonify = deps["jsonify"]
    send_state = deps["send_state"]
    try:
        payload = request.get_json(silent=True) or {}
    except Exception:
        payload = {}
    try:
        normalized, path = _save_range_config_to_txt(payload)
    except Exception as exc:
        return jsonify({"ok": False, "error": f"Could not save configurations: {exc}"}), 400
    _apply_saved_range_config_to_send_state(send_state, normalized)
    return jsonify(
        {
            "ok": True,
            "message": "Configurations saved into TXT file.",
            "config": normalized,
            "path": str(path),
        }
    )


def api_campaign_name_suggest(deps):
    request = deps["request"]
    jsonify = deps["jsonify"]
    generate_autonomous_campaign_name = deps["generate_autonomous_campaign_name"]
    base_name = ""
    try:
        if request.method == "POST":
            payload = request.get_json(silent=True) or {}
            base_name = str(payload.get("base") or payload.get("campaign_name") or "").strip()
        else:
            base_name = str(request.args.get("base") or request.args.get("campaign_name") or "").strip()
    except Exception:
        base_name = ""
    try:
        campaign_name = generate_autonomous_campaign_name(base_name)
    except Exception as exc:
        return jsonify({"ok": False, "error": f"Could not generate campaign name: {exc}"}), 400
    return jsonify({"ok": True, "campaign_name": campaign_name})


def send(deps):
    request = deps["request"]
    send_state = deps["send_state"]
    parse_selected_tables = deps["parse_selected_tables"]
    _parse_yes_no = deps["_parse_yes_no"]
    _parse_int_with_bounds = deps["_parse_int_with_bounds"]
    _normalize_campaign_id = deps["_normalize_campaign_id"]
    _normalize_campaign_name_base = deps["_normalize_campaign_name_base"]
    generate_autonomous_campaign_name = deps["generate_autonomous_campaign_name"]
    secure_filename = deps["secure_filename"]
    is_supported_attachment_filename = deps["is_supported_attachment_filename"]
    save_uploaded_attachments = deps["save_uploaded_attachments"]
    build_payload = deps["build_payload"]
    load_contacts_from_multiple_groups = deps["load_contacts_from_multiple_groups"]
    load_group_contacts_from_all_contacts = deps["load_group_contacts_from_all_contacts"]
    get_max_row_number_for_tables = deps["get_max_row_number_for_tables"]
    load_numbers_from_tables = deps["load_numbers_from_tables"]
    load_numbers = deps["load_numbers"]
    filter_numbers_by_country_codes = deps["filter_numbers_by_country_codes"]
    generate_campaign_id = deps["generate_campaign_id"]
    start_send_job = deps["start_send_job"]
    jsonify = deps["jsonify"]
    flash = deps["flash"]
    redirect = deps["redirect"]
    url_for = deps["url_for"]

    is_ajax = (request.headers.get("X-Requested-With") or "").lower() == "xmlhttprequest"

    def send_error(message, status_code=400):
        if is_ajax:
            return jsonify({"ok": False, "error": message}), status_code
        flash(message)
        return redirect(url_for("index"))

    def send_ok(message, campaign_id="", campaign_name=""):
        if is_ajax:
            cid = str(campaign_id or "").zfill(6) if str(campaign_id or "").strip() else ""
            return jsonify(
                {
                    "ok": True,
                    "message": message,
                    "running": send_state["running"],
                    "campaign_id": cid,
                    "campaign_name": str(campaign_name or "").strip(),
                }
            )
        flash(message)
        return redirect(url_for("index", keep=1))

    if send_state["running"]:
        return send_error("A send job is already running. Please wait.", 409)

    file = request.files.get("contacts")
    source_type = (request.form.get("source_type") or "file").strip().lower()
    send_target = (request.form.get("send_target") or "contacts").strip().lower()
    if send_target not in ("contacts", "groups"):
        send_target = "contacts"

    selected_tables_list = request.form.getlist("selected_tables")
    selected_tables_raw = request.form.get("selected_tables") or "[]"
    selected_tables = parse_selected_tables(
        selected_tables_list if selected_tables_list else selected_tables_raw
    )
    db_select_all_rows = _parse_yes_no(request.form.get("db_select_all_rows"), default=True)
    db_row_start_raw = request.form.get("db_row_start")
    db_row_end_raw = request.form.get("db_row_end")
    db_row_start = (
        _parse_int_with_bounds(db_row_start_raw, 1, 1, 10_000_000)
        if (db_row_start_raw and str(db_row_start_raw).strip())
        else None
    )
    db_row_end = (
        _parse_int_with_bounds(db_row_end_raw, 1, 1, 10_000_000)
        if (db_row_end_raw and str(db_row_end_raw).strip())
        else None
    )
    if db_row_start is not None and db_row_end is not None and db_row_end < db_row_start:
        db_row_start, db_row_end = db_row_end, db_row_start
    if db_select_all_rows:
        db_row_start = None
        db_row_end = None
    selected_contacts_raw = request.form.get("selected_contacts") or "[]"
    selected_contacts = parse_selected_tables(selected_contacts_raw)
    reuse_campaign_id = _normalize_campaign_id(request.form.get("reuse_campaign_id") or "")
    campaign_name_base = _normalize_campaign_name_base(request.form.get("campaign_name") or "", default_value="campaign")
    campaign_name = generate_autonomous_campaign_name(campaign_name_base)
    group_filter_name = (request.form.get("group_filter_name") or "").strip()
    group_filter_names = parse_selected_tables(request.form.get("group_filter_names") or "[]")
    attachment_files = request.files.getlist("attachments")
    message_slots = []
    message_variants = []
    for i in range(1, 101):
        msg = str(request.form.get(f"message_{i}") or "").strip()
        message_slots.append(msg)
        if msg:
            message_variants.append({"slot": i, "text": msg})
    legacy_message = str(request.form.get("message") or "").strip()
    if not message_variants and legacy_message:
        message_slots[0] = legacy_message
        message_variants = [{"slot": 1, "text": legacy_message}]
    message = message_variants[0]["text"] if message_variants else legacy_message
    delay = request.form.get("delay") or "0"
    batch_min_raw = request.form.get("batch_min_size") or "20"
    batch_max_raw = request.form.get("batch_max_size") or "30"
    random_message_pick_raw = request.form.get("random_message_pick")
    message_panel_count_raw = request.form.get("message_panel_count") or "1"
    random_attachment_pick_raw = request.form.get("random_attachment_pick")
    media_count_min_raw = request.form.get("media_count_min") or "1"
    media_count_max_raw = request.form.get("media_count_max") or "1"
    random_attachment_delay_raw = request.form.get("random_attachment_delay")
    attachment_delay_min_raw = request.form.get("attachment_delay_min") or "0"
    attachment_delay_max_raw = request.form.get("attachment_delay_max") or "30"
    random_search_result_delay_raw = request.form.get("random_search_result_delay")
    search_result_delay_min_raw = request.form.get("search_result_delay_min") or "1"
    search_result_delay_max_raw = request.form.get("search_result_delay_max") or "4"
    random_click_delay_raw = request.form.get("random_click_delay")
    click_delay_min_ms_raw = request.form.get("click_delay_min_ms") or "150"
    click_delay_max_ms_raw = request.form.get("click_delay_max_ms") or "900"
    random_send_delay_raw = request.form.get("random_send_delay")
    send_delay_min_raw = request.form.get("send_delay_min") or "0"
    send_delay_max_raw = request.form.get("send_delay_max") or ""
    typing_pause_chars_min_raw = request.form.get("typing_pause_chars_min") or "10"
    typing_pause_chars_max_raw = request.form.get("typing_pause_chars_max") or "20"
    typing_pause_delay_min_raw = request.form.get("typing_pause_delay_min") or "2000"
    typing_pause_delay_max_raw = request.form.get("typing_pause_delay_max") or "5000"
    remove_chars_during_typing_raw = request.form.get("remove_chars_during_typing_enabled")
    remove_chars_times_min_raw = request.form.get("remove_chars_times_min") or "3"
    remove_chars_times_max_raw = request.form.get("remove_chars_times_max") or "7"
    remove_chars_count_min_raw = request.form.get("remove_chars_count_min") or "1"
    remove_chars_count_max_raw = request.form.get("remove_chars_count_max") or "3"
    optional_side_actions_raw = request.form.get("optional_side_actions_enabled")
    side_action_chance_percent_raw = request.form.get("side_action_chance_percent") or "20"
    side_action_pause_min_ms_raw = request.form.get("side_action_pause_min_ms") or "700"
    side_action_pause_max_ms_raw = request.form.get("side_action_pause_max_ms") or "2000"
    random_batch_size_raw = request.form.get("random_batch_size")
    random_batch_start_delay_raw = request.form.get("random_batch_start_delay")
    batch_start_min_minutes_raw = request.form.get("batch_start_min_minutes") or "3"
    batch_start_max_minutes_raw = request.form.get("batch_start_max_minutes") or "6"
    profiles_numbers_raw = request.form.get("profiles_numbers") or "1"
    active_profile_indexes_raw = request.form.get("active_profile_indexes") or "[]"
    profile_numbers_map_raw = request.form.get("profile_numbers_map") or "{}"
    skipped_profiles_raw = request.form.get("skipped_profiles") or "[]"
    random_profile_pick_raw = request.form.get("random_profile_pick")
    selected_sms_ids_raw = request.form.get("selected_sms_ids") or "[]"
    country_filter = (request.form.get("country") or "").strip()
    resend_sms = True

    unsupported_uploads = []
    for item in attachment_files or []:
        name = secure_filename((item.filename or "").strip())
        if not name:
            continue
        if not is_supported_attachment_filename(name):
            unsupported_uploads.append(name)
    if unsupported_uploads:
        return send_error(
            "Unsupported attachment type: "
            + ", ".join(unsupported_uploads)
            + ". Allowed: image/video/audio/pdf/doc/docx/xls/xlsx/csv/txt/zip/ppt/pptx"
        )

    saved_attachments = save_uploaded_attachments(attachment_files)
    if not message and not saved_attachments:
        return send_error("Please enter a message or attach at least one file.")
    payload = build_payload(message, saved_attachments, message_variants=message_variants)

    if not send_delay_max_raw:
        send_delay_max_raw = delay if str(delay).strip() else "30"
    random_message_enabled = _parse_yes_no(random_message_pick_raw, default=True)
    random_attachment_enabled = _parse_yes_no(random_attachment_pick_raw, default=True)
    random_attachment_delay_enabled = _parse_yes_no(random_attachment_delay_raw, default=True)
    random_search_result_delay_enabled = _parse_yes_no(random_search_result_delay_raw, default=True)
    random_click_delay_enabled = _parse_yes_no(random_click_delay_raw, default=True)
    random_send_delay_enabled = _parse_yes_no(random_send_delay_raw, default=True)
    remove_chars_during_typing_enabled = _parse_yes_no(remove_chars_during_typing_raw, default=True)
    optional_side_actions_enabled = _parse_yes_no(optional_side_actions_raw, default=False)
    random_batch_size_enabled = _parse_yes_no(random_batch_size_raw, default=True)
    random_batch_start_enabled = _parse_yes_no(random_batch_start_delay_raw, default=True)
    random_profile_pick_enabled = _parse_yes_no(random_profile_pick_raw, default=True)
    selected_sms_ids = []
    try:
        selected_sms_ids = [int(x) for x in (parse_selected_tables(selected_sms_ids_raw) or []) if str(x).strip()]
    except Exception:
        selected_sms_ids = []

    message_panel_count = _parse_int_with_bounds(message_panel_count_raw, 1, 1, 100)

    media_count_min = _parse_int_with_bounds(media_count_min_raw, 1, 1, 200)
    media_count_max = _parse_int_with_bounds(media_count_max_raw, 1, 1, 200)
    if media_count_max < media_count_min:
        media_count_min, media_count_max = media_count_max, media_count_min

    attachment_delay_min = _parse_int_with_bounds(attachment_delay_min_raw, 0, 0, 3600)
    attachment_delay_max = _parse_int_with_bounds(attachment_delay_max_raw, 30, 0, 3600)
    if attachment_delay_max < attachment_delay_min:
        attachment_delay_min, attachment_delay_max = attachment_delay_max, attachment_delay_min

    search_result_delay_min = _parse_int_with_bounds(search_result_delay_min_raw, 1, 0, 3600)
    search_result_delay_max = _parse_int_with_bounds(search_result_delay_max_raw, 4, 0, 3600)
    if search_result_delay_max < search_result_delay_min:
        search_result_delay_min, search_result_delay_max = (
            search_result_delay_max,
            search_result_delay_min,
        )

    click_delay_min_ms = _parse_int_with_bounds(click_delay_min_ms_raw, 150, 0, 60000)
    click_delay_max_ms = _parse_int_with_bounds(click_delay_max_ms_raw, 900, 0, 60000)
    if click_delay_max_ms < click_delay_min_ms:
        click_delay_min_ms, click_delay_max_ms = click_delay_max_ms, click_delay_min_ms

    send_delay_min = _parse_int_with_bounds(send_delay_min_raw, 0, 0, 3600)
    send_delay_max = _parse_int_with_bounds(send_delay_max_raw, 30, 0, 3600)
    if send_delay_max < send_delay_min:
        send_delay_min, send_delay_max = send_delay_max, send_delay_min

    typing_pause_chars_min = _parse_int_with_bounds(typing_pause_chars_min_raw, 10, 0, 1000)
    typing_pause_chars_max = _parse_int_with_bounds(typing_pause_chars_max_raw, 20, 0, 1000)
    if typing_pause_chars_max < typing_pause_chars_min:
        typing_pause_chars_min, typing_pause_chars_max = typing_pause_chars_max, typing_pause_chars_min

    typing_pause_delay_min = _parse_int_with_bounds(typing_pause_delay_min_raw, 2000, 0, 3600000)
    typing_pause_delay_max = _parse_int_with_bounds(typing_pause_delay_max_raw, 5000, 0, 3600000)
    if typing_pause_delay_max < typing_pause_delay_min:
        typing_pause_delay_min, typing_pause_delay_max = typing_pause_delay_max, typing_pause_delay_min

    remove_chars_times_min = _parse_int_with_bounds(remove_chars_times_min_raw, 3, 0, 100)
    remove_chars_times_max = _parse_int_with_bounds(remove_chars_times_max_raw, 7, 0, 100)
    if remove_chars_times_max < remove_chars_times_min:
        remove_chars_times_min, remove_chars_times_max = remove_chars_times_max, remove_chars_times_min

    remove_chars_count_min = _parse_int_with_bounds(remove_chars_count_min_raw, 1, 0, 1000)
    remove_chars_count_max = _parse_int_with_bounds(remove_chars_count_max_raw, 3, 0, 1000)
    if remove_chars_count_max < remove_chars_count_min:
        remove_chars_count_min, remove_chars_count_max = remove_chars_count_max, remove_chars_count_min

    side_action_chance_percent = _parse_int_with_bounds(side_action_chance_percent_raw, 20, 0, 100)
    side_action_pause_min_ms = _parse_int_with_bounds(side_action_pause_min_ms_raw, 700, 0, 60000)
    side_action_pause_max_ms = _parse_int_with_bounds(side_action_pause_max_ms_raw, 2000, 0, 60000)
    if side_action_pause_max_ms < side_action_pause_min_ms:
        side_action_pause_min_ms, side_action_pause_max_ms = side_action_pause_max_ms, side_action_pause_min_ms

    delay_seconds = send_delay_max
    batch_min_size = _parse_int_with_bounds(batch_min_raw, 20, 1, 500)
    batch_max_size = _parse_int_with_bounds(batch_max_raw, 30, 1, 500)
    if batch_max_size < batch_min_size:
        batch_min_size, batch_max_size = batch_max_size, batch_min_size

    batch_start_min_minutes = _parse_int_with_bounds(batch_start_min_minutes_raw, 3, 0, 120)
    batch_start_max_minutes = _parse_int_with_bounds(batch_start_max_minutes_raw, 6, 0, 120)
    if batch_start_max_minutes < batch_start_min_minutes:
        batch_start_min_minutes, batch_start_max_minutes = (
            batch_start_max_minutes,
            batch_start_min_minutes,
        )
    profiles_numbers = _parse_int_with_bounds(profiles_numbers_raw, 1, 1, 100)
    active_profile_indexes = []
    try:
        parsed_active_indexes = json.loads(active_profile_indexes_raw)
        if isinstance(parsed_active_indexes, list):
            for item in parsed_active_indexes:
                try:
                    idx = int(item)
                except Exception:
                    continue
                if idx > 0 and idx not in active_profile_indexes:
                    active_profile_indexes.append(idx)
    except Exception:
        active_profile_indexes = []
    active_profile_indexes = sorted(active_profile_indexes)
    profile_numbers_map = {}
    try:
        parsed_map = json.loads(profile_numbers_map_raw)
        if isinstance(parsed_map, dict):
            for k, v in parsed_map.items():
                key = str(k).strip()
                val = str(v or "").strip()
                if key:
                    profile_numbers_map[key] = val
    except Exception:
        profile_numbers_map = {}
    skipped_profiles = []
    try:
        parsed_skips = json.loads(skipped_profiles_raw)
        if isinstance(parsed_skips, list):
            for item in parsed_skips:
                try:
                    val = int(item)
                except Exception:
                    continue
                if val > 0 and val not in skipped_profiles:
                    skipped_profiles.append(val)
    except Exception:
        skipped_profiles = []

    if not active_profile_indexes:
        return send_error(
            "No logged-in WhatsApp sessions available. Open WhatsApp Sessions and log in at least one profile first."
        )

    range_config = {
        "random_message_enabled": random_message_enabled,
        "message_panel_count": message_panel_count,
        "random_attachment_enabled": random_attachment_enabled,
        "media_count_min": media_count_min,
        "media_count_max": media_count_max,
        "random_attachment_delay_enabled": random_attachment_delay_enabled,
        "attachment_delay_min": attachment_delay_min,
        "attachment_delay_max": attachment_delay_max,
        "random_search_result_delay_enabled": random_search_result_delay_enabled,
        "search_result_delay_min": search_result_delay_min,
        "search_result_delay_max": search_result_delay_max,
        "random_click_delay_enabled": random_click_delay_enabled,
        "click_delay_min_ms": click_delay_min_ms,
        "click_delay_max_ms": click_delay_max_ms,
        "random_send_delay_enabled": random_send_delay_enabled,
        "send_delay_min": send_delay_min,
        "send_delay_max": send_delay_max,
        "typing_pause_chars_min": typing_pause_chars_min,
        "typing_pause_chars_max": typing_pause_chars_max,
        "typing_pause_delay_min": typing_pause_delay_min,
        "typing_pause_delay_max": typing_pause_delay_max,
        "typing_pause_delay_unit": "ms",
        "remove_chars_during_typing_enabled": remove_chars_during_typing_enabled,
        "remove_chars_times_min": remove_chars_times_min,
        "remove_chars_times_max": remove_chars_times_max,
        "remove_chars_count_min": remove_chars_count_min,
        "remove_chars_count_max": remove_chars_count_max,
        "optional_side_actions_enabled": optional_side_actions_enabled,
        "side_action_chance_percent": side_action_chance_percent,
        "side_action_pause_min_ms": side_action_pause_min_ms,
        "side_action_pause_max_ms": side_action_pause_max_ms,
        "random_batch_size_enabled": random_batch_size_enabled,
        "random_batch_start_enabled": random_batch_start_enabled,
        "batch_start_min_minutes": batch_start_min_minutes,
        "batch_start_max_minutes": batch_start_max_minutes,
        "profiles_numbers": profiles_numbers,
        "active_profile_indexes": active_profile_indexes,
        "profile_numbers_map": profile_numbers_map,
        "skipped_profiles": skipped_profiles,
        "random_profile_pick_enabled": random_profile_pick_enabled,
    }

    send_state["last_message"] = message
    send_state["last_messages"] = list(message_slots)
    send_state["last_delay"] = str(delay_seconds)
    send_state["last_country_filter"] = country_filter
    send_state["last_attachment_names"] = payload["attachment_names"]
    send_state["last_resend"] = resend_sms
    send_state["last_source_type"] = source_type
    send_state["last_send_target"] = send_target
    send_state["last_selected_tables"] = selected_tables
    send_state["last_campaign_name"] = campaign_name
    send_state["last_group_filter_name"] = group_filter_name
    send_state["last_group_filter_names"] = group_filter_names
    send_state["last_selected_contacts"] = list(selected_contacts)
    send_state["last_filename"] = file.filename if file else ""
    send_state["last_batch_min_size"] = batch_min_size
    send_state["last_batch_max_size"] = batch_max_size
    send_state["last_random_message_enabled"] = random_message_enabled
    send_state["last_message_panel_count"] = message_panel_count
    send_state["last_random_attachment_enabled"] = random_attachment_enabled
    send_state["last_media_count_min"] = media_count_min
    send_state["last_media_count_max"] = media_count_max
    send_state["last_random_attachment_delay_enabled"] = random_attachment_delay_enabled
    send_state["last_attachment_delay_min"] = attachment_delay_min
    send_state["last_attachment_delay_max"] = attachment_delay_max
    send_state["last_random_search_result_delay_enabled"] = random_search_result_delay_enabled
    send_state["last_search_result_delay_min"] = search_result_delay_min
    send_state["last_search_result_delay_max"] = search_result_delay_max
    send_state["last_random_click_delay_enabled"] = random_click_delay_enabled
    send_state["last_click_delay_min_ms"] = click_delay_min_ms
    send_state["last_click_delay_max_ms"] = click_delay_max_ms
    send_state["last_random_send_delay_enabled"] = random_send_delay_enabled
    send_state["last_send_delay_min"] = send_delay_min
    send_state["last_send_delay_max"] = send_delay_max
    send_state["last_typing_pause_chars_min"] = typing_pause_chars_min
    send_state["last_typing_pause_chars_max"] = typing_pause_chars_max
    send_state["last_typing_pause_delay_min"] = typing_pause_delay_min
    send_state["last_typing_pause_delay_max"] = typing_pause_delay_max
    send_state["last_typing_pause_delay_unit"] = "ms"
    send_state["last_remove_chars_during_typing_enabled"] = remove_chars_during_typing_enabled
    send_state["last_remove_chars_times_min"] = remove_chars_times_min
    send_state["last_remove_chars_times_max"] = remove_chars_times_max
    send_state["last_remove_chars_count_min"] = remove_chars_count_min
    send_state["last_remove_chars_count_max"] = remove_chars_count_max
    send_state["last_optional_side_actions_enabled"] = optional_side_actions_enabled
    send_state["last_side_action_chance_percent"] = side_action_chance_percent
    send_state["last_side_action_pause_min_ms"] = side_action_pause_min_ms
    send_state["last_side_action_pause_max_ms"] = side_action_pause_max_ms
    send_state["last_random_batch_size_enabled"] = random_batch_size_enabled
    send_state["last_random_batch_start_enabled"] = random_batch_start_enabled
    send_state["last_batch_start_min_minutes"] = batch_start_min_minutes
    send_state["last_batch_start_max_minutes"] = batch_start_max_minutes
    send_state["last_profiles_numbers"] = max(active_profile_indexes) if active_profile_indexes else profiles_numbers
    send_state["last_random_profile_pick_enabled"] = random_profile_pick_enabled
    send_state["last_selected_sms_ids"] = list(selected_sms_ids)

    try:
        used_selected_contacts = False
        skipped_count = 0
        applied_prefixes = []
        targets = []
        if send_target == "groups":
            selected_groups = [g for g in (selected_contacts or []) if str(g).strip()]
            selected_groups = sorted(set(str(g).strip() for g in selected_groups if str(g).strip()))
            if not selected_groups:
                return send_error("Please add group(s) into Selected Contacts for group send mode.")
            targets = selected_groups
            send_state["last_selected_contacts"] = list(targets)
            used_selected_contacts = True
        else:
            selected_contacts = [c for c in (selected_contacts or []) if str(c).strip()]
            if not selected_contacts:
                return send_error("No contacts in Selected Contacts list. Please add contacts before sending.")
            if reuse_campaign_id:
                numbers = list(selected_contacts)
            elif source_type == "database":
                if group_filter_names:
                    multi_group_payload = load_contacts_from_multiple_groups(group_filter_names)
                    numbers = multi_group_payload.get("contacts", [])
                    if not group_filter_name and group_filter_names:
                        group_filter_name = ", ".join(group_filter_names)
                        send_state["last_group_filter_name"] = group_filter_name
                    if not selected_tables:
                        selected_tables = ["all_contacts"]
                        send_state["last_selected_tables"] = selected_tables
                elif group_filter_name:
                    numbers = load_group_contacts_from_all_contacts(group_filter_name)
                    if not selected_tables:
                        selected_tables = ["all_contacts"]
                        send_state["last_selected_tables"] = selected_tables
                elif not selected_tables:
                    return send_error("Please select at least one database table.")
                else:
                    if not db_select_all_rows:
                        max_row_number = get_max_row_number_for_tables(selected_tables)
                        if max_row_number > 0:
                            if db_row_start is not None and db_row_start > max_row_number:
                                return send_error(
                                    f"From row {db_row_start} exceeds max available row {max_row_number}."
                                )
                            if db_row_end is not None and db_row_end > max_row_number:
                                return send_error(
                                    f"To row {db_row_end} exceeds max available row {max_row_number}."
                                )
                    numbers = load_numbers_from_tables(
                        selected_tables, row_start=db_row_start, row_end=db_row_end
                    )
            else:
                if not file or not file.filename:
                    return send_error("Please upload a contacts file.")
                numbers = load_numbers(file)

            numbers, skipped_count, applied_prefixes = filter_numbers_by_country_codes(numbers, country_filter)

            selected_set = set(selected_contacts)
            numbers = [n for n in numbers if n in selected_set]
            if not numbers:
                return send_error("No selected contacts matched the loaded source/filter.")
            used_selected_contacts = True

            if not numbers:
                if country_filter:
                    return send_error("No numbers matched the provided country code filter.")
                if source_type == "database":
                    if group_filter_name or group_filter_names:
                        return send_error("No phone numbers found in the selected group.")
                    return send_error("No phone numbers found in selected database tables.")
                return send_error("No phone numbers found in the file.")
            targets = numbers
    except Exception as exc:
        return send_error(str(exc))

    try:
        campaign_id = generate_campaign_id()
    except Exception as exc:
        return send_error(f"Could not generate campaign ID: {exc}")
    started = start_send_job(
        targets,
        payload,
        delay_seconds,
        resend_sms,
        send_target=send_target,
        campaign_id=campaign_id,
        campaign_name=campaign_name,
        batch_min_size=batch_min_size,
        batch_max_size=batch_max_size,
        range_config=range_config,
    )
    if not started:
        return send_error("A send job is already running.", 409)

    if reuse_campaign_id:
        source_text = f"Re-use Campaign {reuse_campaign_id}"
    else:
        source_text = f"DB tables ({len(selected_tables)})" if source_type == "database" else "file"
    source_text += f" - Target: {'Groups' if send_target == 'groups' else 'Contacts'}"
    source_text += f" - Batch range: {batch_min_size}-{batch_max_size}"
    source_text += f" - Logged-in WhatsApp sessions: {len(active_profile_indexes)}"
    if used_selected_contacts:
        source_text += " - Selected Contacts"
    if group_filter_names:
        source_text += f" - Groups: {', '.join(group_filter_names)}"
    elif group_filter_name:
        source_text += f" - Group: {group_filter_name}"

    if applied_prefixes:
        return send_ok(
            f"Starting sending for {len(targets)} filtered contacts (skipped {skipped_count}). "
            f"Filter: {', '.join(applied_prefixes)}. Source: {source_text}. "
            f"Campaign: {str(campaign_id).zfill(6)}_{campaign_name}.",
            campaign_id=campaign_id,
            campaign_name=campaign_name,
        )
    return send_ok(
        f"Starting sending for {len(targets)} contacts. Source: {source_text}. "
        f"Campaign: {str(campaign_id).zfill(6)}_{campaign_name}.",
        campaign_id=campaign_id,
        campaign_name=campaign_name,
    )


def api_send_pause(deps):
    send_state = deps["send_state"]
    jsonify = deps["jsonify"]
    if not send_state.get("running"):
        return jsonify({"ok": False, "error": "No send job is running."}), 400
    send_state["pause_requested"] = True
    return jsonify(
        {
            "ok": True,
            "running": bool(send_state.get("running")),
            "pause_requested": True,
            "paused": bool(send_state.get("paused")),
        }
    )


def api_send_resume(deps):
    send_state = deps["send_state"]
    jsonify = deps["jsonify"]
    if not send_state.get("running"):
        return jsonify({"ok": False, "error": "No send job is running."}), 400
    send_state["pause_requested"] = False
    return jsonify(
        {
            "ok": True,
            "running": bool(send_state.get("running")),
            "pause_requested": False,
            "paused": bool(send_state.get("paused")),
        }
    )


def api_send_cancel(deps):
    send_state = deps["send_state"]
    jsonify = deps["jsonify"]
    cancel_send_job = deps["_cancel_active_send_job"]
    if not send_state.get("running"):
        return jsonify({"ok": False, "error": "No send job is running."}), 400
    result = cancel_send_job(send_state)
    status_code = 200 if result.get("ok") else 400
    return jsonify(result), status_code


def api_send_session_start(deps):
    send_state = deps["send_state"]
    jsonify = deps["jsonify"]
    if not send_state.get("running"):
        return jsonify({"ok": False, "error": "No WhatsApp session job is running."}), 400
    if not send_state.get("awaiting_session_start"):
        return jsonify({"ok": False, "error": "WhatsApp sessions are not ready yet."}), 400
    send_state["session_start_requested"] = True
    return jsonify(
        {
            "ok": True,
            "running": bool(send_state.get("running")),
            "awaiting_session_start": bool(send_state.get("awaiting_session_start")),
            "session_start_requested": True,
        }
    )


def template_pic(deps, filename):
    send_from_directory = deps["send_from_directory"]
    pic_dir = deps["Path"](deps["__file__"]).parent / "templates" / "pic"
    return send_from_directory(str(pic_dir), filename)


def send_upload_asset(deps, filename):
    send_from_directory = deps["send_from_directory"]
    uploads_dir = deps["Path"](deps["__file__"]).parent / "send_uploads"
    return send_from_directory(str(uploads_dir), filename)


def api_recent_send_media(deps):
    jsonify = deps["jsonify"]
    traceback = deps["traceback"]
    RECENT_MEDIA_EXTENSIONS = deps["RECENT_MEDIA_EXTENSIONS"]
    IMAGE_EXTENSIONS = deps["IMAGE_EXTENSIONS"]
    VIDEO_EXTENSIONS = deps["VIDEO_EXTENSIONS"]
    AUDIO_EXTENSIONS = deps["AUDIO_EXTENSIONS"]
    DOCUMENT_EXTENSIONS = deps["DOCUMENT_EXTENSIONS"]
    request = deps["request"]
    try:
        uploads_dir = deps["Path"](deps["__file__"]).parent / "send_uploads"
        uploads_dir.mkdir(parents=True, exist_ok=True)
        limit_raw = request.args.get("limit") or "200"
        try:
            limit = max(1, min(1000, int(limit_raw)))
        except Exception:
            limit = 200

        files = []
        for p in uploads_dir.iterdir():
            if not p.is_file():
                continue
            ext = p.suffix.lower()
            if ext and ext not in RECENT_MEDIA_EXTENSIONS:
                continue
            try:
                stat = p.stat()
            except Exception:
                continue
            kind = "other"
            if ext in IMAGE_EXTENSIONS:
                kind = "image"
            elif ext in VIDEO_EXTENSIONS:
                kind = "video"
            elif ext in AUDIO_EXTENSIONS:
                kind = "audio"
            elif ext in DOCUMENT_EXTENSIONS:
                kind = "document"
            files.append(
                {
                    "name": p.name,
                    "size": int(stat.st_size or 0),
                    "modified_at": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                    "kind": kind,
                    "url": f"/assets/send_uploads/{quote(p.name)}",
                }
            )

        files.sort(key=lambda x: x.get("modified_at") or "", reverse=True)
        return jsonify({"ok": True, "files": files[:limit]})
    except Exception as exc:
        print(f"[MEDIA ERROR] api_recent_send_media failed: {exc}")
        traceback.print_exc()
        return jsonify({"ok": False, "error": str(exc), "files": []}), 500


def api_recent_send_media_delete(deps):
    jsonify = deps["jsonify"]
    traceback = deps["traceback"]
    request = deps["request"]
    try:
        payload = request.get_json(silent=True) or {}
        names = payload.get("files") or []
        if not isinstance(names, list):
            return jsonify({"ok": False, "error": "files must be a list"}), 400

        uploads_dir = (deps["Path"](deps["__file__"]).parent / "send_uploads").resolve()
        uploads_dir.mkdir(parents=True, exist_ok=True)

        deleted = []
        missing = []
        skipped = []
        failed = []

        for raw_name in names[:1000]:
            name = str(raw_name or "").strip()
            if not name:
                continue
            if Path(name).name != name or name in (".", ".."):
                skipped.append(name)
                continue
            target = (uploads_dir / name).resolve()
            if target.parent != uploads_dir:
                skipped.append(name)
                continue
            if not target.exists():
                missing.append(name)
                continue
            if not target.is_file():
                skipped.append(name)
                continue
            try:
                target.unlink()
                deleted.append(name)
            except Exception as exc:
                failed.append({"name": name, "error": str(exc)})

        return jsonify(
            {
                "ok": True,
                "deleted": deleted,
                "missing": missing,
                "skipped": skipped,
                "failed": failed,
            }
        )
    except Exception as exc:
        print(f"[MEDIA ERROR] api_recent_send_media_delete failed: {exc}")
        traceback.print_exc()
        return jsonify({"ok": False, "error": str(exc)}), 500


def api_group_tables(deps):
    jsonify = deps["jsonify"]
    list_group_tables = deps["list_group_tables"]
    try:
        tables = list_group_tables()
        return jsonify({"ok": True, "tables": tables})
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc), "tables": []}), 500


def api_table_info(deps):
    jsonify = deps["jsonify"]
    traceback = deps["traceback"]
    request = deps["request"]
    parse_selected_tables = deps["parse_selected_tables"]
    get_tables_info = deps["get_tables_info"]
    try:
        payload = request.get_json(silent=True) or {}
        selected_tables = parse_selected_tables(payload.get("tables") or [])
        info = get_tables_info(selected_tables)
        return jsonify({"ok": True, "info": info})
    except Exception as exc:
        print(f"[DB ERROR] api_table_info failed: {exc}")
        traceback.print_exc()
        return jsonify({"ok": False, "error": str(exc), "info": []}), 500


def api_preview_table_contacts(deps):
    jsonify = deps["jsonify"]
    traceback = deps["traceback"]
    request = deps["request"]
    parse_selected_tables = deps["parse_selected_tables"]
    _parse_yes_no = deps["_parse_yes_no"]
    _parse_row_bounds = deps["_parse_row_bounds"]
    get_max_row_number_for_tables = deps["get_max_row_number_for_tables"]
    load_numbers_from_tables = deps["load_numbers_from_tables"]
    build_contact_items = deps["build_contact_items"]
    try:
        payload = request.get_json(silent=True) or {}
        selected_tables = parse_selected_tables(payload.get("tables") or [])
        select_all_rows = _parse_yes_no(payload.get("select_all_rows"), default=True)
        row_start = payload.get("row_start")
        row_end = payload.get("row_end")
        row_start, row_end = _parse_row_bounds(row_start=row_start, row_end=row_end)
        max_row_number = get_max_row_number_for_tables(selected_tables)
        if select_all_rows:
            row_start = None
            row_end = None
        elif max_row_number > 0:
            if row_start is not None and row_start > max_row_number:
                return (
                    jsonify(
                        {
                            "ok": False,
                            "error": f"From row {row_start} exceeds max available row {max_row_number}.",
                            "contacts": [],
                            "max_row_number": max_row_number,
                        }
                    ),
                    400,
                )
            if row_end is not None and row_end > max_row_number:
                return (
                    jsonify(
                        {
                            "ok": False,
                            "error": f"To row {row_end} exceeds max available row {max_row_number}.",
                            "contacts": [],
                            "max_row_number": max_row_number,
                        }
                    ),
                    400,
                )

        contacts, row_id_map = load_numbers_from_tables(
            selected_tables,
            row_start=row_start,
            row_end=row_end,
            include_row_ids=True,
        )
        return jsonify(
            {
                "ok": True,
                "contacts": contacts,
                "contact_items": build_contact_items(contacts, {}, row_id_map=row_id_map),
                "max_row_number": max_row_number,
            }
        )
    except Exception as exc:
        print(f"[DB ERROR] api_preview_table_contacts failed: {exc}")
        traceback.print_exc()
        return jsonify({"ok": False, "error": str(exc), "contacts": []}), 500


def api_preview_file_contacts(deps):
    jsonify = deps["jsonify"]
    traceback = deps["traceback"]
    request = deps["request"]
    load_numbers = deps["load_numbers"]
    build_contact_items = deps["build_contact_items"]
    try:
        file = request.files.get("contacts")
        if not file or not file.filename:
            return jsonify({"ok": False, "error": "No file uploaded.", "contacts": []}), 400
        contacts = load_numbers(file)
        return jsonify(
            {
                "ok": True,
                "contacts": contacts,
                "contact_items": build_contact_items(contacts, {}),
            }
        )
    except Exception as exc:
        print(f"[FILE ERROR] api_preview_file_contacts failed: {exc}")
        traceback.print_exc()
        return jsonify({"ok": False, "error": str(exc), "contacts": []}), 500


def api_preview_manual_all_contacts(deps):
    jsonify = deps["jsonify"]
    traceback = deps["traceback"]
    request = deps["request"]
    load_numbers_manual_flexible = deps["load_numbers_manual_flexible"]
    build_contact_items = deps["build_contact_items"]
    try:
        file = request.files.get("contacts")
        if not file or not file.filename:
            return jsonify({"ok": False, "error": "No file uploaded.", "contacts": []}), 400
        contacts = load_numbers_manual_flexible(file)
        return jsonify(
            {
                "ok": True,
                "contacts": contacts,
                "contact_items": build_contact_items(contacts, {}),
            }
        )
    except Exception as exc:
        print(f"[FILE ERROR] api_preview_manual_all_contacts failed: {exc}")
        traceback.print_exc()
        return jsonify({"ok": False, "error": str(exc), "contacts": []}), 500


def api_import_all_contacts_manual(deps):
    jsonify = deps["jsonify"]
    traceback = deps["traceback"]
    request = deps["request"]
    group_exists_in_all_contacts = deps["group_exists_in_all_contacts"]
    load_numbers_manual_flexible = deps["load_numbers_manual_flexible"]
    import_manual_contacts_to_all_contacts = deps["import_manual_contacts_to_all_contacts"]
    try:
        file = request.files.get("contacts")
        group_name = (request.form.get("group_name") or "").strip()
        if not file or not file.filename:
            return jsonify({"ok": False, "error": "Please upload a .csv or .xlsx file."}), 400
        if not group_name:
            return jsonify({"ok": False, "error": "Please enter group name."}), 400
        if group_exists_in_all_contacts(group_name):
            return (
                jsonify(
                    {
                        "ok": False,
                        "reason": "group_exists",
                        "group_name": group_name,
                        "error": f"Group already exists in all_contacts: {group_name}",
                    }
                ),
                409,
            )

        contacts = load_numbers_manual_flexible(file)
        inserted = import_manual_contacts_to_all_contacts(contacts, group_name)
        return jsonify(
            {
                "ok": True,
                "group_name": group_name,
                "inserted_count": len(inserted),
                "contacts": inserted,
                "message": f"Imported {len(inserted)} contacts to all_contacts for group '{group_name}'.",
            }
        )
    except Exception as exc:
        print(f"[DB ERROR] api_import_all_contacts_manual failed: {exc}")
        traceback.print_exc()
        return jsonify({"ok": False, "error": str(exc)}), 500


def api_add_sms_message(deps):
    jsonify = deps["jsonify"]
    request = deps["request"]
    get_db_connection = deps["get_db_connection"]
    traceback = deps["traceback"]
    try:
        payload = request.get_json(silent=True) or {}
        title = str(payload.get("title") or "").strip()
        message = str(payload.get("message") or "").strip()
        if not message:
            return jsonify({"ok": False, "error": "SMS message is required."}), 400
        if len(title) > 255:
            title = title[:255]
        db_conn = get_db_connection()
        cur = db_conn.cursor()
        cur.execute(
            """
            INSERT INTO sms_messages (title, message)
            VALUES (%s, %s)
            RETURNING id
            """,
            (title or None, message),
        )
        row = cur.fetchone()
        db_conn.commit()
        try:
            cur.close()
        except Exception:
            pass
        try:
            db_conn.close()
        except Exception:
            pass
        new_id = int(row[0]) if row and row[0] is not None else 0
        return jsonify({"ok": True, "id": new_id, "title": title, "message": message})
    except Exception as exc:
        print(f"[DB ERROR] api_add_sms_message failed: {exc}")
        traceback.print_exc()
        return jsonify({"ok": False, "error": str(exc)}), 500


def api_delete_sms_message(deps):
    jsonify = deps["jsonify"]
    request = deps["request"]
    get_db_connection = deps["get_db_connection"]
    traceback = deps["traceback"]
    try:
        payload = request.get_json(silent=True) or {}
        try:
            sms_id = int(payload.get("id") or 0)
        except Exception:
            sms_id = 0
        if sms_id <= 0:
            return jsonify({"ok": False, "error": "Valid SMS ID is required."}), 400

        db_conn = get_db_connection()
        cur = db_conn.cursor()
        cur.execute("DELETE FROM sms_messages WHERE id = %s RETURNING id", (sms_id,))
        row = cur.fetchone()
        db_conn.commit()
        try:
            cur.close()
        except Exception:
            pass
        try:
            db_conn.close()
        except Exception:
            pass

        if not row:
            return jsonify({"ok": False, "error": "SMS not found."}), 404
        return jsonify({"ok": True, "id": sms_id})
    except Exception as exc:
        print(f"[DB ERROR] api_delete_sms_message failed: {exc}")
        traceback.print_exc()
        return jsonify({"ok": False, "error": str(exc)}), 500
