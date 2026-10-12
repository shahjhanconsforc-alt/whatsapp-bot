import csv
import io
import re
import threading
import time
import traceback
from copy import deepcopy
from pathlib import Path
from urllib.parse import urlparse

import openpyxl
from playwright.sync_api import sync_playwright
from werkzeug.utils import secure_filename


INVITE_LINK_RE = re.compile(r"https?://chat\.whatsapp\.com/(?:invite/)?[A-Za-z0-9]+", re.IGNORECASE)
CHAT_READY_SELECTORS = (
    "[data-testid='chat-list']",
    "div[aria-label='Chat list']",
    "#pane-side",
)
LOGIN_SELECTORS = (
    "canvas[aria-label*='Scan']",
    "canvas[aria-label*='scan']",
    "[data-testid='qrcode']",
    "text='Log into WhatsApp Web'",
    "text='Use WhatsApp on your computer'",
)
JOIN_BUTTON_SELECTORS = (
    "button:has-text('Join group')",
    "div[role='button']:has-text('Join group')",
    "button:has-text('Join chat')",
    "div[role='button']:has-text('Join chat')",
)
REQUEST_TO_JOIN_SELECTORS = (
    "button:has-text('Request to join')",
    "div[role='button']:has-text('Request to join')",
    "button:has-text('Request to Join')",
    "div[role='button']:has-text('Request to Join')",
)
ALREADY_JOINED_SELECTORS = (
    "button:has-text('Open chat')",
    "div[role='button']:has-text('Open chat')",
    "text=/already a participant/i",
)
REQUEST_PENDING_SELECTORS = (
    "button:has-text('Cancel request')",
    "div[role='button']:has-text('Cancel request')",
    "text=/request sent/i",
    "text=/requested to join/i",
    "text=/request pending/i",
    "text=/pending approval/i",
)
GROUP_NOT_FOUND_SELECTORS = (
    "text=/couldn't find this group/i",
    "text=/could not find this group/i",
    "text=/this invite link is no longer valid/i",
    "text=/group invite link.*reset/i",
    "text=/group invite link.*invalid/i",
    "text=/group not found/i",
    "text=/this group is not available/i",
)
LOGIN_WAIT_TIMEOUT_SECONDS = 1800
INVITE_PAGE_SETTLE_MS = 900
ACTION_BUTTON_LOOKUP_TIMEOUT_SECONDS = 5
ACTION_BUTTON_GRACE_TIMEOUT_SECONDS = 2.5
INVITE_PAGE_NETWORKIDLE_GRACE_MS = 1500
ACTION_BUTTON_CLICK_DELAY_MS = 1200


class GroupJoinStopped(RuntimeError):
    pass


_JOIN_LOCK = threading.Lock()
_JOIN_STATE = {
    "running": False,
    "last_error": None,
    "last_result": None,
    "logs": [],
    "rows": [],
    "started_at": "",
    "finished_at": "",
    "waiting_for_login": False,
    "range_start": "",
    "range_end": "",
    "selected_count": 0,
    "total_links": 0,
    "joined_count": 0,
    "requested_count": 0,
    "skipped_count": 0,
    "not_found_count": 0,
}
_JOIN_RUNTIME = {
    "token": 0,
    "stop_event": None,
    "context": None,
    "page": None,
    "profile_dir": "",
    "release_profile": None,
}


def _now_iso():
    return time.strftime("%Y-%m-%d %H:%M:%S")


def _empty_state():
    return {
        "running": False,
        "last_error": None,
        "last_result": None,
        "logs": [],
        "rows": [],
        "started_at": "",
        "finished_at": "",
        "waiting_for_login": False,
        "range_start": "",
        "range_end": "",
        "selected_count": 0,
        "total_links": 0,
        "joined_count": 0,
        "requested_count": 0,
        "skipped_count": 0,
        "not_found_count": 0,
    }


def _invalidate_runtime_locked():
    next_token = int(_JOIN_RUNTIME.get("token") or 0) + 1
    _JOIN_RUNTIME.clear()
    _JOIN_RUNTIME.update(
        {
            "token": next_token,
            "stop_event": None,
            "context": None,
            "page": None,
            "profile_dir": "",
            "release_profile": None,
        }
    )
    return next_token


def _is_active_run_locked(run_token):
    return int(_JOIN_RUNTIME.get("token") or 0) == int(run_token or 0)


def _raise_if_stop_requested(stop_event):
    if stop_event and stop_event.is_set():
        raise GroupJoinStopped("Group joining stopped by user.")


def _sleep_with_stop(stop_event, seconds, step=0.25):
    deadline = time.time() + max(0.0, float(seconds or 0))
    while time.time() < deadline:
        _raise_if_stop_requested(stop_event)
        remaining = deadline - time.time()
        time.sleep(min(step, max(0.0, remaining)))
    _raise_if_stop_requested(stop_event)


def is_running():
    with _JOIN_LOCK:
        return bool(_JOIN_STATE.get("running"))


def reset_if_idle():
    with _JOIN_LOCK:
        if _JOIN_STATE.get("running"):
            return False
        _JOIN_STATE.clear()
        _JOIN_STATE.update(_empty_state())
        _invalidate_runtime_locked()
        return True


def force_stop_and_reset():
    with _JOIN_LOCK:
        was_running = bool(_JOIN_STATE.get("running"))
        stop_event = _JOIN_RUNTIME.get("stop_event")
        page = _JOIN_RUNTIME.get("page")
        context = _JOIN_RUNTIME.get("context")
        profile_dir = _JOIN_RUNTIME.get("profile_dir")
        release_profile = _JOIN_RUNTIME.get("release_profile")
        _JOIN_STATE.clear()
        _JOIN_STATE.update(_empty_state())
        _invalidate_runtime_locked()

    if stop_event:
        try:
            stop_event.set()
        except Exception:
            pass

    try:
        if page and not page.is_closed():
            page.close()
    except Exception:
        pass

    try:
        if context:
            context.close()
    except Exception:
        pass

    if callable(release_profile) and str(profile_dir or "").strip():
        try:
            release_profile(profile_dir)
        except Exception:
            pass

    return was_running


def _recompute_counts_locked():
    rows = _JOIN_STATE["rows"]
    _JOIN_STATE["total_links"] = len(rows)
    _JOIN_STATE["joined_count"] = sum(1 for row in rows if row.get("status") == "joined")
    _JOIN_STATE["requested_count"] = sum(1 for row in rows if row.get("status") == "requested")
    _JOIN_STATE["skipped_count"] = sum(1 for row in rows if row.get("status") == "skipped")
    _JOIN_STATE["not_found_count"] = sum(1 for row in rows if row.get("status") == "group_not_found")


def _append_log_locked(message):
    text = f"[{_now_iso()}] {str(message or '').strip()}"
    _JOIN_STATE["logs"].append(text)
    if len(_JOIN_STATE["logs"]) > 250:
        _JOIN_STATE["logs"] = _JOIN_STATE["logs"][-250:]


def _set_row_status_locked(index, status, detail=""):
    if index < 0 or index >= len(_JOIN_STATE["rows"]):
        return
    row = _JOIN_STATE["rows"][index]
    row["status"] = status
    row["detail"] = str(detail or "").strip()
    row["updated_at"] = _now_iso()
    _recompute_counts_locked()


def _snapshot_state_locked():
    payload = deepcopy(_JOIN_STATE)
    _recompute_counts_locked()
    payload["total_links"] = _JOIN_STATE["total_links"]
    payload["joined_count"] = _JOIN_STATE["joined_count"]
    payload["requested_count"] = _JOIN_STATE["requested_count"]
    payload["skipped_count"] = _JOIN_STATE["skipped_count"]
    payload["not_found_count"] = _JOIN_STATE["not_found_count"]
    return payload


def _extract_invite_matches(text):
    matches = []
    for raw_match in INVITE_LINK_RE.findall(str(text or "")):
        cleaned = raw_match.strip().rstrip(".,;")
        if cleaned:
            matches.append(cleaned)
    return matches


def _parse_uploaded_invite_rows(file_storage):
    filename = secure_filename(file_storage.filename or "")
    ext = Path(filename).suffix.lower()

    def add_matches_from_cells(cells, rows):
        for row_no, cell in cells:
            for link in _extract_invite_matches(cell):
                rows.append(
                    {
                        "row_no": len(rows) + 1,
                        "source_row": row_no,
                        "invite_link": link,
                        "status": "pending",
                        "detail": "Ready",
                        "updated_at": "",
                    }
                )
        return rows

    if ext == ".csv":
        file_storage.stream.seek(0)
        text = file_storage.stream.read().decode("utf-8", errors="ignore")
        rows = []
        cells = []
        for row_index, row in enumerate(csv.reader(io.StringIO(text)), start=1):
            if not row:
                continue
            for cell in row:
                if str(cell or "").strip():
                    cells.append((row_index, cell))
        return add_matches_from_cells(cells, rows)

    if ext == ".xlsx":
        file_storage.stream.seek(0)
        workbook = openpyxl.load_workbook(file_storage.stream, read_only=True, data_only=True)
        sheet = workbook.active
        rows = []
        cells = []
        for row_index, row in enumerate(sheet.iter_rows(values_only=True), start=1):
            for cell in row or []:
                if str(cell or "").strip():
                    cells.append((row_index, cell))
        workbook.close()
        return add_matches_from_cells(cells, rows)

    raise RuntimeError("Unsupported file type. Use .csv or .xlsx")


def _coerce_join_rows(raw_rows=None, raw_links=None):
    rows = []
    if isinstance(raw_rows, list) and raw_rows:
        for idx, raw_row in enumerate(raw_rows, start=1):
            item = raw_row if isinstance(raw_row, dict) else {}
            invite_link = str(item.get("invite_link") or "").strip()
            if not invite_link:
                continue
            row_no = item.get("row_no")
            source_row = item.get("source_row")
            try:
                row_no = int(row_no)
            except Exception:
                row_no = len(rows) + 1
            try:
                source_row = int(source_row)
            except Exception:
                source_row = idx
            rows.append(
                {
                    "row_no": row_no,
                    "source_row": source_row,
                    "invite_link": invite_link,
                    "status": "pending",
                    "detail": "Ready",
                    "updated_at": "",
                }
            )
        return rows

    for idx, raw_link in enumerate(raw_links or [], start=1):
        invite_link = str(raw_link or "").strip()
        if not invite_link:
            continue
        rows.append(
            {
                "row_no": len(rows) + 1,
                "source_row": idx,
                "invite_link": invite_link,
                "status": "pending",
                "detail": "Ready",
                "updated_at": "",
            }
        )
    return rows


def _normalize_join_range(total_rows, range_start, range_end):
    total_rows = int(total_rows or 0)
    if total_rows <= 0:
        raise ValueError("No invite links available for joining.")

    raw_start = "" if range_start is None else str(range_start).strip()
    raw_end = "" if range_end is None else str(range_end).strip()

    try:
        start = 1 if not raw_start else int(raw_start)
        end = total_rows if not raw_end else int(raw_end)
    except Exception as exc:
        raise ValueError("Range values must be whole numbers.") from exc

    if start < 1 or end < 1:
        raise ValueError("Range values must start from 1 or higher.")
    if start > end:
        raise ValueError("Range start must be less than or equal to range end.")
    if start > total_rows:
        raise ValueError(f"Range start is greater than total links ({total_rows}).")
    if end > total_rows:
        raise ValueError(f"Range end is greater than total links ({total_rows}).")

    return start, end


def _validate_join_range_metadata(range_start, range_end):
    raw_start = "" if range_start is None else str(range_start).strip()
    raw_end = "" if range_end is None else str(range_end).strip()
    if not raw_start and not raw_end:
        return "", ""

    try:
        start = int(raw_start)
        end = int(raw_end)
    except Exception as exc:
        raise ValueError("Range values must be whole numbers.") from exc

    if start < 1 or end < 1:
        raise ValueError("Range values must start from 1 or higher.")
    if start > end:
        raise ValueError("Range start must be less than or equal to range end.")
    return start, end


def _filter_rows_for_selected_range(rows, range_start, range_end):
    filtered_rows = []
    for row_index, row in enumerate(rows):
        row_no = int(row.get("row_no") or row_index + 1)
        if range_start <= row_no <= range_end:
            row["status"] = "pending"
            row["detail"] = "Ready"
            row["updated_at"] = ""
            filtered_rows.append(row)
    return filtered_rows


def _row_range_from_rows(rows):
    row_numbers = []
    for row_index, row in enumerate(rows):
        try:
            row_numbers.append(int(row.get("row_no") or row_index + 1))
        except Exception:
            row_numbers.append(row_index + 1)
    if not row_numbers:
        return "", ""
    return row_numbers[0], row_numbers[-1]


def _extract_invite_code(invite_url):
    parsed = urlparse(invite_url)
    path_parts = [part for part in parsed.path.split("/") if part]
    if not path_parts:
        raise ValueError(f"Could not extract invite code from: {invite_url}")
    return path_parts[-1]


def _build_accept_url(invite_url):
    code = _extract_invite_code(invite_url)
    return f"https://web.whatsapp.com/accept?code={code}&utm_campaign=wa_chat_v2"


def _is_any_selector_visible(page, selectors):
    for selector in selectors:
        try:
            if page.locator(selector).first.is_visible():
                return True
        except Exception:
            continue
    return False


def _wait_for_visible_selector(page, selectors, timeout_seconds, stop_event=None):
    deadline = time.time() + float(timeout_seconds)
    while time.time() < deadline:
        _raise_if_stop_requested(stop_event)
        for selector in selectors:
            locator = page.locator(selector).first
            try:
                if locator.is_visible():
                    return locator
            except Exception:
                if stop_event and stop_event.is_set():
                    raise GroupJoinStopped("Group joining stopped by user.")
                continue
        _sleep_with_stop(stop_event, 0.25)
    return None


def _wait_for_visible_selector_group(page, selector_groups, timeout_seconds, stop_event=None):
    deadline = time.time() + float(timeout_seconds)
    while time.time() < deadline:
        _raise_if_stop_requested(stop_event)
        for group_name, selectors in selector_groups:
            for selector in selectors:
                locator = page.locator(selector).first
                try:
                    if locator.is_visible():
                        return group_name, locator
                except Exception:
                    if stop_event and stop_event.is_set():
                        raise GroupJoinStopped("Group joining stopped by user.")
                    continue
        _sleep_with_stop(stop_event, 0.25)
    return "", None


def _wait_for_invite_page_state(page, timeout_seconds, stop_event=None):
    return _wait_for_visible_selector_group(
        page,
        (
            ("login", LOGIN_SELECTORS),
            ("already_joined", ALREADY_JOINED_SELECTORS),
            ("request_pending", REQUEST_PENDING_SELECTORS),
            ("not_found", GROUP_NOT_FOUND_SELECTORS),
            ("join", JOIN_BUTTON_SELECTORS),
            ("request", REQUEST_TO_JOIN_SELECTORS),
        ),
        timeout_seconds=timeout_seconds,
        stop_event=stop_event,
    )


def _wait_for_invite_page_state_with_grace(page, stop_event=None):
    state_type, state_locator = _wait_for_invite_page_state(
        page,
        timeout_seconds=ACTION_BUTTON_LOOKUP_TIMEOUT_SECONDS,
        stop_event=stop_event,
    )
    if state_type:
        return state_type, state_locator

    try:
        _raise_if_stop_requested(stop_event)
        page.wait_for_load_state("networkidle", timeout=INVITE_PAGE_NETWORKIDLE_GRACE_MS)
    except Exception:
        if stop_event and stop_event.is_set():
            raise GroupJoinStopped("Group joining stopped by user.")

    return _wait_for_invite_page_state(
        page,
        timeout_seconds=ACTION_BUTTON_GRACE_TIMEOUT_SECONDS,
        stop_event=stop_event,
    )


def _ensure_logged_in(page, stop_event=None, run_token=None):
    _raise_if_stop_requested(stop_event)
    try:
        page.goto("https://web.whatsapp.com", wait_until="domcontentloaded")
    except Exception as exc:
        if stop_event and stop_event.is_set():
            raise GroupJoinStopped("Group joining stopped by user.") from exc
        raise
    ready = _wait_for_visible_selector(page, CHAT_READY_SELECTORS, timeout_seconds=8, stop_event=stop_event)
    if ready:
        with _JOIN_LOCK:
            if run_token is None or _is_active_run_locked(run_token):
                _JOIN_STATE["waiting_for_login"] = False
        return

    deadline = time.time() + LOGIN_WAIT_TIMEOUT_SECONDS
    while time.time() < deadline:
        _raise_if_stop_requested(stop_event)
        ready = _wait_for_visible_selector(page, CHAT_READY_SELECTORS, timeout_seconds=2, stop_event=stop_event)
        if ready:
            with _JOIN_LOCK:
                if run_token is None or _is_active_run_locked(run_token):
                    was_waiting = bool(_JOIN_STATE.get("waiting_for_login"))
                    _JOIN_STATE["waiting_for_login"] = False
                    if was_waiting:
                        _append_log_locked("WhatsApp Web login detected. Resuming group joining.")
            return
        if _is_any_selector_visible(page, LOGIN_SELECTORS):
            with _JOIN_LOCK:
                if run_token is None or _is_active_run_locked(run_token):
                    if not _JOIN_STATE.get("waiting_for_login"):
                        _append_log_locked("WhatsApp Web login required. Group joining is paused until you log in.")
                    _JOIN_STATE["waiting_for_login"] = True
        if page.is_closed():
            with _JOIN_LOCK:
                if run_token is None or _is_active_run_locked(run_token):
                    _JOIN_STATE["waiting_for_login"] = False
            raise RuntimeError("WhatsApp Web page was closed before login finished.")
        _sleep_with_stop(stop_event, 1)

    with _JOIN_LOCK:
        if run_token is None or _is_active_run_locked(run_token):
            _JOIN_STATE["waiting_for_login"] = False
    raise RuntimeError("Timed out waiting for WhatsApp Web login.")


def _join_group_from_invite(page, invite_url, stop_event=None, run_token=None):
    accept_url = _build_accept_url(invite_url)
    try:
        while True:
            _raise_if_stop_requested(stop_event)
            page.goto(accept_url, wait_until="domcontentloaded")
            _sleep_with_stop(stop_event, INVITE_PAGE_SETTLE_MS / 1000.0)

            state_type, state_locator = _wait_for_invite_page_state_with_grace(page, stop_event=stop_event)
            if state_type == "login":
                _ensure_logged_in(page, stop_event=stop_event, run_token=run_token)
                continue
            if state_type == "already_joined":
                return "skipped", "Already joined."
            if state_type == "request_pending":
                return "requested", "Join request already pending."
            if state_type == "not_found":
                return "group_not_found", "Group not found or invite link expired."
            if state_type not in ("join", "request") or not state_locator:
                if _is_any_selector_visible(page, LOGIN_SELECTORS):
                    _ensure_logged_in(page, stop_event=stop_event, run_token=run_token)
                    continue
                if _is_any_selector_visible(page, GROUP_NOT_FOUND_SELECTORS):
                    return "group_not_found", "Group not found or invite link expired."
                if _is_any_selector_visible(page, REQUEST_PENDING_SELECTORS):
                    return "requested", "Join request already pending."
                if _is_any_selector_visible(page, ALREADY_JOINED_SELECTORS):
                    return "skipped", "Already joined."
                return "skipped", "No join button shown. Moved to next link."

            action_type = state_type
            action_button = state_locator
            action_button.scroll_into_view_if_needed()
            _sleep_with_stop(stop_event, ACTION_BUTTON_CLICK_DELAY_MS / 1000.0)
            action_button.click(force=True)

            retry_current_link = False
            deadline = time.time() + 20
            while time.time() < deadline:
                _raise_if_stop_requested(stop_event)
                if _is_any_selector_visible(page, LOGIN_SELECTORS):
                    _ensure_logged_in(page, stop_event=stop_event, run_token=run_token)
                    retry_current_link = True
                    break
                if _is_any_selector_visible(page, GROUP_NOT_FOUND_SELECTORS):
                    return "group_not_found", "Group not found or invite link expired."
                if _is_any_selector_visible(page, ALREADY_JOINED_SELECTORS):
                    return "joined", "Joined successfully."
                if _is_any_selector_visible(page, REQUEST_PENDING_SELECTORS):
                    return "requested", "Join request sent."
                if action_type == "join" and not _is_any_selector_visible(page, JOIN_BUTTON_SELECTORS):
                    return "joined", "Joined successfully."
                if action_type == "request" and not _is_any_selector_visible(page, REQUEST_TO_JOIN_SELECTORS):
                    return "requested", "Join request sent."
                _sleep_with_stop(stop_event, 0.4)

            if retry_current_link:
                continue
            if action_type == "request" and not _is_any_selector_visible(page, REQUEST_TO_JOIN_SELECTORS):
                return "requested", "Join request submitted, waiting for approval."
            return "skipped", "Join result timed out."
    except GroupJoinStopped:
        raise
    except Exception as exc:
        if stop_event and stop_event.is_set():
            raise GroupJoinStopped("Group joining stopped by user.") from exc
        raise


def _run_group_join_job(
    rows,
    profile_dir,
    launch_kwargs,
    launch_persistent_context_safe,
    release_playwright_profile,
    stop_event,
    run_token,
):
    context = None
    try:
        def _log_runtime(message):
            with _JOIN_LOCK:
                if _is_active_run_locked(run_token):
                    _append_log_locked(message)

        with _JOIN_LOCK:
            if _is_active_run_locked(run_token):
                range_start = _JOIN_STATE.get("range_start") or 1
                range_end = _JOIN_STATE.get("range_end") or len(rows)
                selected_count = int(_JOIN_STATE.get("selected_count") or len(rows))
                _append_log_locked(
                    f"Starting group joining for rows {range_start}-{range_end} "
                    f"({selected_count} selected link(s))."
                )
                _append_log_locked(f"Using Playwright profile: {profile_dir}")

        seen_links = set()
        with sync_playwright() as p:
            _raise_if_stop_requested(stop_event)
            context = launch_persistent_context_safe(
                browser_type=p.chromium,
                profile_dir=profile_dir,
                launch_kwargs=launch_kwargs,
                owner_label="group joining",
                log_fn=_log_runtime,
            )
            page = context.pages[0] if context.pages else context.new_page()
            with _JOIN_LOCK:
                if _is_active_run_locked(run_token):
                    _JOIN_RUNTIME["context"] = context
                    _JOIN_RUNTIME["page"] = page
            _ensure_logged_in(page, stop_event=stop_event, run_token=run_token)

            for selected_position, row in enumerate(rows, start=1):
                _raise_if_stop_requested(stop_event)
                row_index = selected_position - 1
                invite_link = row.get("invite_link", "")
                normalized_key = invite_link.strip().lower()
                with _JOIN_LOCK:
                    if _is_active_run_locked(run_token):
                        _set_row_status_locked(row_index, "joining", "Processing link...")
                        _append_log_locked(
                            f"Processing selected link {selected_position}/{len(rows)} "
                            f"(row {row.get('row_no') or row_index + 1}): {invite_link}"
                        )

                if normalized_key in seen_links:
                    with _JOIN_LOCK:
                        if _is_active_run_locked(run_token):
                            _set_row_status_locked(row_index, "skipped", "Duplicate link in uploaded file.")
                            _append_log_locked(f"Skipped duplicate link: {invite_link}")
                    continue
                seen_links.add(normalized_key)

                try:
                    status, detail = _join_group_from_invite(
                        page,
                        invite_link,
                        stop_event=stop_event,
                        run_token=run_token,
                    )
                except GroupJoinStopped:
                    raise
                except Exception as exc:
                    status = "skipped"
                    detail = f"Unexpected error: {exc}"

                with _JOIN_LOCK:
                    if _is_active_run_locked(run_token):
                        _set_row_status_locked(row_index, status, detail)
                        _append_log_locked(f"{invite_link} -> {status}: {detail}")

        with _JOIN_LOCK:
            if _is_active_run_locked(run_token):
                _recompute_counts_locked()
                range_label = f"{_JOIN_STATE.get('range_start') or 1}-{_JOIN_STATE.get('range_end') or len(rows)}"
                _JOIN_STATE["last_result"] = (
                    f"Finished group joining for rows {range_label}. "
                    f"Joined: {_JOIN_STATE['joined_count']}, "
                    f"Requested: {_JOIN_STATE['requested_count']}, "
                    f"Skipped: {_JOIN_STATE['skipped_count']}, "
                    f"Group not found: {_JOIN_STATE['not_found_count']}."
                )
                _append_log_locked(_JOIN_STATE["last_result"])
    except GroupJoinStopped:
        pass
    except Exception as exc:
        with _JOIN_LOCK:
            if _is_active_run_locked(run_token):
                _JOIN_STATE["last_error"] = str(exc)
                _append_log_locked(f"Error: {exc}")
        traceback.print_exc()
    finally:
        try:
            if context:
                context.close()
        except Exception:
            pass
        release_playwright_profile(profile_dir)
        with _JOIN_LOCK:
            if _is_active_run_locked(run_token):
                _JOIN_RUNTIME["context"] = None
                _JOIN_RUNTIME["page"] = None
                _JOIN_RUNTIME["profile_dir"] = ""
                _JOIN_RUNTIME["release_profile"] = None
                _JOIN_RUNTIME["stop_event"] = None
                _JOIN_STATE["running"] = False
                _JOIN_STATE["finished_at"] = _now_iso()


def api_groups_joining_preview(deps):
    request = deps["request"]
    jsonify = deps["jsonify"]
    try:
        file_storage = request.files.get("file")
        if not file_storage or not (file_storage.filename or "").strip():
            return jsonify({"ok": False, "error": "Please upload a .csv or .xlsx file."}), 400

        rows = _parse_uploaded_invite_rows(file_storage)
        if not rows:
            return jsonify({"ok": False, "error": "No WhatsApp invite links found in the file.", "rows": []}), 400

        return jsonify(
            {
                "ok": True,
                "rows": rows,
                "total_links": len(rows),
            }
        )
    except Exception as exc:
        print(f"[GROUP JOIN ERROR] preview failed: {exc}")
        traceback.print_exc()
        return jsonify({"ok": False, "error": str(exc), "rows": []}), 500


def api_groups_joining_start(deps):
    request = deps["request"]
    jsonify = deps["jsonify"]
    get_playwright_user_data_dir = deps["get_playwright_user_data_dir"]
    get_playwright_launch_kwargs = deps["get_playwright_launch_kwargs"]
    launch_persistent_context_safe = deps["launch_persistent_context_safe"]
    release_playwright_profile = deps["release_playwright_profile"]
    try:
        payload = request.get_json(silent=True) or {}
        raw_rows = _coerce_join_rows(payload.get("rows"), payload.get("links") or [])
        if not raw_rows:
            return jsonify({"ok": False, "error": "No invite links provided."}), 400

        filtered_rows_only = bool(payload.get("filtered_rows_only"))
        if filtered_rows_only:
            rows = raw_rows
            range_start, range_end = _validate_join_range_metadata(
                payload.get("range_start"),
                payload.get("range_end"),
            )
            if range_start == "" or range_end == "":
                range_start, range_end = _row_range_from_rows(rows)
        else:
            range_start, range_end = _normalize_join_range(
                len(raw_rows),
                payload.get("range_start"),
                payload.get("range_end"),
            )
            rows = _filter_rows_for_selected_range(raw_rows, range_start, range_end)

        if not rows:
            return jsonify({"ok": False, "error": "No invite links found for the selected range."}), 400

        profile_dir = get_playwright_user_data_dir()
        launch_kwargs = dict(get_playwright_launch_kwargs(default_headless=False))
        stop_event = threading.Event()
        with _JOIN_LOCK:
            if _JOIN_STATE["running"]:
                return jsonify({"ok": False, "error": "Groups joining is already running."}), 409
            run_token = _invalidate_runtime_locked()
            _JOIN_STATE.clear()
            _JOIN_STATE.update(_empty_state())
            _JOIN_STATE["running"] = True
            _JOIN_STATE["rows"] = rows
            _JOIN_STATE["started_at"] = _now_iso()
            _JOIN_STATE["finished_at"] = ""
            _JOIN_STATE["range_start"] = range_start
            _JOIN_STATE["range_end"] = range_end
            _JOIN_STATE["selected_count"] = len(rows)
            _recompute_counts_locked()
            _JOIN_RUNTIME["token"] = run_token
            _JOIN_RUNTIME["stop_event"] = stop_event
            _JOIN_RUNTIME["profile_dir"] = str(profile_dir or "")
            _JOIN_RUNTIME["release_profile"] = release_playwright_profile

        worker = threading.Thread(
            target=_run_group_join_job,
            args=(
                deepcopy(rows),
                profile_dir,
                launch_kwargs,
                launch_persistent_context_safe,
                release_playwright_profile,
                stop_event,
                run_token,
            ),
            daemon=True,
        )
        worker.start()
        return jsonify({"ok": True})
    except ValueError as exc:
        with _JOIN_LOCK:
            _JOIN_STATE["running"] = False
            _JOIN_STATE["last_error"] = str(exc)
            _invalidate_runtime_locked()
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:
        print(f"[GROUP JOIN ERROR] start failed: {exc}")
        traceback.print_exc()
        with _JOIN_LOCK:
            _JOIN_STATE["running"] = False
            _JOIN_STATE["last_error"] = str(exc)
            _invalidate_runtime_locked()
        return jsonify({"ok": False, "error": str(exc)}), 500


def api_groups_joining_stop(deps):
    jsonify = deps["jsonify"]
    try:
        stopped = force_stop_and_reset()
        return jsonify({"ok": True, "stopped": bool(stopped)})
    except Exception as exc:
        print(f"[GROUP JOIN ERROR] stop failed: {exc}")
        traceback.print_exc()
        return jsonify({"ok": False, "error": str(exc)}), 500


def api_groups_joining_status(deps):
    jsonify = deps["jsonify"]
    with _JOIN_LOCK:
        payload = _snapshot_state_locked()
    return jsonify(payload)
