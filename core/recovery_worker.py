from datetime import datetime
from pathlib import Path
import threading
import traceback
import random
import os
import re

from playwright.sync_api import sync_playwright

from core.group_db_exporter import save_group_metadata_to_postgres
from core.main_scrapper import (
    extract_group_metadata,
    open_group_and_members,
    open_group_info,
    open_members_from_group_info,
    extract_member_contacts,
    return_to_group_list,
)


def _env_bool(name, default=False):
    raw = os.getenv(name)
    if raw is None:
        return bool(default)
    return str(raw).strip().lower() in ("1", "true", "yes", "on")


def get_playwright_launch_kwargs(default_headless=False):
    headless = _env_bool("PLAYWRIGHT_HEADLESS", default_headless)
    start_maximized = _env_bool("PLAYWRIGHT_START_MAXIMIZED", True)
    no_viewport = _env_bool("PLAYWRIGHT_NO_VIEWPORT", True)
    slow_mo_raw = str(os.getenv("PLAYWRIGHT_SLOW_MO_MS", "0") or "0").strip()
    try:
        slow_mo = max(0, int(slow_mo_raw))
    except Exception:
        slow_mo = 0

    kwargs = {"headless": headless}
    if start_maximized:
        kwargs["args"] = ["--start-maximized"]
    if no_viewport:
        kwargs["no_viewport"] = True
    if slow_mo > 0:
        kwargs["slow_mo"] = slow_mo
    return kwargs


def get_playwright_user_data_dir():
    base = Path(__file__).parent
    multi_account = _env_bool("PLAYWRIGHT_MULTI_ACCOUNT", False)
    if not multi_account:
        raw = str(os.getenv("PLAYWRIGHT_USER_DATA_DIR", "./playwright_profile") or "").strip()
        path = Path(raw)
        if not path.is_absolute():
            path = (base / path).resolve()
        path.mkdir(parents=True, exist_ok=True)
        return path

    root_raw = str(os.getenv("PLAYWRIGHT_PROFILES_ROOT", "./playwright_profiles") or "").strip()
    root = Path(root_raw)
    if not root.is_absolute():
        root = (base / root).resolve()
    root.mkdir(parents=True, exist_ok=True)

    default_profile = str(os.getenv("PLAYWRIGHT_PROFILE_NAME", "default") or "default").strip() or "default"
    auto_select = _env_bool("PLAYWRIGHT_PROFILE_AUTO_SELECT", True)
    current_marker = root / ".current_profile"
    selected_name = default_profile

    if auto_select:
        marker_name = ""
        if current_marker.exists():
            try:
                marker_name = current_marker.read_text(encoding="utf-8").strip()
            except Exception:
                marker_name = ""
        if marker_name and (root / marker_name).is_dir():
            selected_name = marker_name
        else:
            profile_dirs = [p for p in root.iterdir() if p.is_dir() and not p.name.startswith(".")]
            if profile_dirs:
                profile_dirs.sort(key=lambda p: p.stat().st_mtime, reverse=True)
                selected_name = profile_dirs[0].name

    safe_name = "".join(ch for ch in selected_name if ch.isalnum() or ch in ("-", "_")).strip() or "default"
    path = root / safe_name
    path.mkdir(parents=True, exist_ok=True)
    try:
        current_marker.write_text(safe_name, encoding="utf-8")
    except Exception:
        pass
    return path


def _wait_for_any_selector(page, selectors, timeout_ms=120000):
    for selector in selectors:
        try:
            page.wait_for_selector(selector, timeout=timeout_ms)
            return selector
        except Exception:
            continue
    return ""


def _first_text_from_selectors(page, selectors, timeout_ms=1200):
    for selector in selectors:
        try:
            node = page.locator(selector).first
            if node.count() == 0:
                continue
            node.wait_for(state="visible", timeout=timeout_ms)
            value = (node.inner_text() or "").strip()
            if value:
                return value
        except Exception:
            continue
    return ""


def _click_first_selector(page, selectors, timeout_ms=1500):
    for selector in selectors:
        try:
            node = page.locator(selector).first
            if node.count() == 0:
                continue
            node.wait_for(state="visible", timeout=timeout_ms)
            try:
                node.scroll_into_view_if_needed(timeout=timeout_ms)
            except Exception:
                pass
            try:
                node.click(timeout=timeout_ms)
            except Exception:
                try:
                    node.click(timeout=timeout_ms, force=True)
                except Exception:
                    node.evaluate("(el) => el.click()")
            return True
        except Exception:
            continue
    return False


def _is_profile_panel_open(page):
    opened = _wait_for_any_selector(
        page,
        (
            "span[data-testid='pushname-input-read-only selectable-text']",
            "[data-testid='phone']",
            "button[aria-label='Edit Name']",
        ),
        timeout_ms=1400,
    )
    return bool(opened)


def _force_click_profile_navbar(page):
    # Profile opening is globally disabled by user request.
    return False


def _open_whatsapp_profile_panel(page):
    # Profile opening is globally disabled by user request.
    return False, "disabled_no_profile_click"


def _collect_whatsapp_account_snapshot(page):
    profile_name = ""
    profile_status = ""
    phone_number = ""
    opened_profile = False
    profile_open_method = "none"
    try:
        _wait_for_any_selector(
            page,
            (
                "[data-testid='chat-list']",
                "div[aria-label='Chat list']",
                "#pane-side",
            ),
            timeout_ms=120000,
        )
        page.wait_for_timeout(300)
        opened_profile, profile_open_method = _open_whatsapp_profile_panel(page)
        if opened_profile:
            page.wait_for_timeout(700)
            profile_name = _first_text_from_selectors(
                page,
                (
                    "span[data-testid='pushname-input-read-only selectable-text']",
                    "span[data-testid='pushname-input-read-only selectable-text'] span",
                    "[data-testid='drawer-right'] h2",
                    "[data-testid='drawer-right'] h1",
                    "header h2",
                    "header h1",
                    "h2",
                ),
                timeout_ms=1800,
            )
            if str(profile_name or "").strip().lower() in (
                "profile",
                "your profile",
                "you",
            ):
                profile_name = ""
            profile_status = _first_text_from_selectors(
                page,
                (
                    "[data-testid='drawer-right'] [data-testid='status']",
                    "[data-testid='drawer-right'] div:has-text('About') + div",
                    "span[data-testid='about']",
                    "[data-testid='drawer-right'] span[dir='auto']",
                    "div:has-text('About') + div",
                ),
                timeout_ms=1200,
            )
            phone_number = _first_text_from_selectors(
                page,
                (
                    "xpath=//*[@data-testid='phone']/following::span[contains(normalize-space(.),'+')][1]",
                    "div:has([data-testid='phone']) span",
                    "span:has-text('+92')",
                ),
                timeout_ms=1200,
            )
            panel_text = ""
            try:
                panel_text = (
                    page.locator("[data-testid='drawer-right']").first.inner_text(timeout=1200) or ""
                )
            except Exception:
                try:
                    panel_text = page.locator("#app").inner_text(timeout=1200) or ""
                except Exception:
                    panel_text = ""
            if panel_text:
                cleaned_panel_text = (
                    panel_text.replace("\u00a0", " ")
                    .replace("\u200e", "")
                    .replace("\u200f", "")
                    .replace("\u202a", "")
                    .replace("\u202b", "")
                    .replace("\u202c", "")
                    .replace("\u2066", "")
                    .replace("\u2067", "")
                    .replace("\u2068", "")
                    .replace("\u2069", "")
                )
                phone_match = re.search(r"\+\s*\d[\d\s\-\(\)]{6,}\d", cleaned_panel_text)
                if not phone_match:
                    phone_match = re.search(r"\b\d[\d\s\-\(\)]{6,}\d\b", cleaned_panel_text)
                if phone_match and not phone_number:
                    phone_number = re.sub(r"\s+", " ", phone_match.group(0)).strip()
                lines = [ln.strip() for ln in cleaned_panel_text.splitlines() if ln and ln.strip()]
                ignored_exact = {
                    "profile",
                    "your profile",
                    "about",
                    "phone",
                    "privacy",
                    "notifications",
                    "security",
                }
                if not profile_name:
                    for ln in lines:
                        low = ln.lower()
                        if (
                            low in ignored_exact
                            or "end-to-end encrypted" in low
                            or low.startswith("phone")
                            or re.search(r"\+\d", ln)
                            or re.search(r"\b\d{7,15}\b", ln)
                        ):
                            continue
                        if len(ln) > 1 and len(ln) <= 80 and not re.search(r"\+\d", ln):
                            profile_name = ln
                            break
                if not profile_status:
                    for idx, ln in enumerate(lines):
                        if ln.strip().lower() == "about" and idx + 1 < len(lines):
                            nxt = lines[idx + 1].strip()
                            if nxt:
                                profile_status = nxt
                                break
                if not profile_status:
                    for ln in lines:
                        low = ln.lower()
                        if (
                            not ln
                            or low in ignored_exact
                            or ln == profile_name
                            or "end-to-end encrypted" in low
                            or re.search(r"\+\d", ln)
                            or re.search(r"\b\d{7,15}\b", ln)
                        ):
                            continue
                        if 2 <= len(ln) <= 120:
                            profile_status = ln
                            break
    finally:
        try:
            page.keyboard.press("Escape")
            page.wait_for_timeout(120)
            page.keyboard.press("Escape")
        except Exception:
            pass
    return {
        "profile_name": str(profile_name or "").strip(),
        "profile_status": str(profile_status or "").strip(),
        "phone_number": str(phone_number or "").strip(),
        "profile_opened": bool(opened_profile),
        "profile_open_method": profile_open_method,
    }


def save_whatsapp_session_snapshot(page, flow_name, user_data_dir, login_state=""):
    snapshot = {
        "profile_name": "",
        "profile_status": "",
        "phone_number": "",
        "profile_opened": False,
    }
    snapshot_error = ""
    try:
        snapshot = _collect_whatsapp_account_snapshot(page)
    except Exception as exc:
        snapshot_error = str(exc)
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = (
        f"{ts} | flow={flow_name} | profile_name={snapshot.get('profile_name') or '-'} | "
        f"status={snapshot.get('profile_status') or '-'} | "
        f"number={snapshot.get('phone_number') or '-'} | "
        f"profile_opened={snapshot.get('profile_opened')} | "
        f"profile_open_method={snapshot.get('profile_open_method') or '-'} | "
        f"login_state={str(login_state or '').strip() or '-'} | "
        f"snapshot_error={snapshot_error or '-'} | "
        f"user_data_dir={user_data_dir}"
    )
    session_file = Path(__file__).resolve().parent.parent / "data" / "session.txt"
    session_file.parent.mkdir(parents=True, exist_ok=True)
    with session_file.open("a", encoding="utf-8") as fh:
        fh.write(line + "\n")
    return snapshot, line


class RecoveryManager:
    def __init__(
        self,
        *,
        get_db_connection,
        get_db_schema,
        sql_module,
        ensure_scrape_runs_table,
        save_scrape_group_row,
        is_scrape_running,
    ):
        self.get_db_connection = get_db_connection
        self.get_db_schema = get_db_schema
        self.sql = sql_module
        self.ensure_scrape_runs_table = ensure_scrape_runs_table
        self.save_scrape_group_row = save_scrape_group_row
        self.is_scrape_running = is_scrape_running
        self.state = {}
        self.reset()

    def reset(self):
        self.state = {
            "running": False,
            "last_error": None,
            "last_result": None,
            "logs": [],
            "base_scrap_id": "",
            "recovery_scrap_id": "",
            "group_name": "",
            "scrapped_contacts_count": 0,
            "new_contacts_count": 0,
            "new_contacts": [],
            "started_at": None,
            "finished_at": None,
        }

    def reset_if_idle(self):
        if not self.state["running"]:
            self.reset()

    def _log(self, message):
        ts = datetime.now().strftime("%H:%M:%S")
        self.state["logs"].append(f"[{ts}] {message}")
        if len(self.state["logs"]) > 300:
            self.state["logs"] = self.state["logs"][-300:]
        print(f"[RECOVERY] {message}")

    def _normalize_group_key(self, text):
        if text is None:
            return ""
        cleaned = str(text).strip().lower()
        return "".join(ch for ch in cleaned if ch.isalnum())

    def _group_name_matches(self, candidate_name, target_name):
        cand = self._normalize_group_key(candidate_name)
        target = self._normalize_group_key(target_name)
        if not cand or not target:
            return False
        if cand == target:
            return True
        # Fallback to containment because WhatsApp titles often include suffixes/prefixes.
        return cand in target or target in cand

    def _read_row_title(self, row):
        title_node = row.locator("span[title]").first
        row_title = ""
        if title_node.count() > 0:
            row_title = (title_node.get_attribute("title") or "").strip()
        if not row_title:
            row_title = (row.inner_text() or "").splitlines()[0].strip()
        return row_title

    def _find_target_group_row(self, page, target_group_name):
        rows_selector = "div[aria-label='Chat list'][role='grid'] > div[role='row']"
        chat_grid = page.locator("div[aria-label='Chat list'][role='grid']").first
        seen_titles = set()
        stagnant_rounds = 0

        for _ in range(120):
            rows = page.locator(rows_selector)
            visible_count = rows.count()
            if visible_count <= 0:
                page.wait_for_timeout(300)
                continue

            newly_seen = 0
            for idx in range(visible_count):
                rows = page.locator(rows_selector)
                if idx >= rows.count():
                    break
                row = rows.nth(idx)
                row.wait_for(state="visible", timeout=20000)
                row.scroll_into_view_if_needed(timeout=20000)
                row_title = self._read_row_title(row)
                if row_title and row_title not in seen_titles:
                    seen_titles.add(row_title)
                    newly_seen += 1

                if self._group_name_matches(row_title, target_group_name):
                    return row, row_title, len(seen_titles)

            if newly_seen == 0:
                stagnant_rounds += 1
            else:
                stagnant_rounds = 0

            if stagnant_rounds >= 8:
                break

            # Scroll down to force WhatsApp virtual list to load additional groups.
            try:
                chat_grid.evaluate("(el) => { el.scrollTop = el.scrollTop + Math.max(500, el.clientHeight - 60); }")
            except Exception:
                try:
                    rows.last.scroll_into_view_if_needed(timeout=20000)
                except Exception:
                    pass
            page.wait_for_timeout(450)

        return None, "", len(seen_titles)

    def _get_left_search_box(self, page):
        candidates = [
            page.locator(
                "div[role='textbox'][contenteditable='true'][aria-label*='Search' i]"
            ).first,
            page.locator("div[contenteditable='true'][data-tab='3']").first,
            page.locator("div[contenteditable='true'][title*='Search' i]").first,
            page.locator("div[aria-label='Search input textbox']").first,
        ]
        for box in candidates:
            try:
                if box.count() == 0:
                    continue
                box.wait_for(state="visible", timeout=1500)
                return box
            except Exception:
                continue
        return None

    def _clear_left_search_box(self, page, search_box):
        try:
            search_box.click(timeout=1500)
            page.keyboard.press("Control+A")
            page.keyboard.press("Backspace")
            page.wait_for_timeout(200)
        except Exception:
            pass

    def _find_target_group_by_search(self, page, target_group_name):
        search_box = self._get_left_search_box(page)
        if not search_box:
            self._log("Search box not found; using scroll scan fallback.")
            return None, ""

        self._log(f"Searching group by name: {target_group_name}")
        try:
            search_box.click(timeout=2000)
            page.keyboard.press("Control+A")
            page.keyboard.press("Backspace")
            search_box.type(str(target_group_name), delay=35, timeout=6000)
            page.wait_for_timeout(700)
        except Exception:
            self._log("Could not type in search box; using scroll scan fallback.")
            return None, ""

        rows_selector = "div[aria-label='Chat list'][role='grid'] > div[role='row']"
        rows = page.locator(rows_selector)
        visible_count = rows.count()
        if visible_count <= 0:
            self._clear_left_search_box(page, search_box)
            return None, ""

        best_row = None
        best_title = ""
        for idx in range(visible_count):
            rows = page.locator(rows_selector)
            if idx >= rows.count():
                break
            row = rows.nth(idx)
            row.wait_for(state="visible", timeout=8000)
            row_title = self._read_row_title(row)
            if not row_title:
                continue
            self._log(f"Search result check: {row_title}")
            if self._group_name_matches(row_title, target_group_name):
                best_row = row
                best_title = row_title
                break

        self._clear_left_search_box(page, search_box)
        return best_row, best_title

    def _ensure_all_contacts_table(self, db_conn):
        schema = self.get_db_schema()
        with db_conn.cursor() as cur:
            cur.execute(
                self.sql.SQL(
                    """
                    CREATE TABLE IF NOT EXISTS {schema_name}.all_contacts (
                        "Phone" TEXT,
                        "whatspp_group" TEXT,
                        "time" TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    )
                    """
                ).format(schema_name=self.sql.Identifier(schema))
            )
            cur.execute(
                self.sql.SQL(
                    'ALTER TABLE {schema_name}.all_contacts ADD COLUMN IF NOT EXISTS "Phone" TEXT'
                ).format(schema_name=self.sql.Identifier(schema))
            )
            cur.execute(
                self.sql.SQL(
                    'ALTER TABLE {schema_name}.all_contacts ADD COLUMN IF NOT EXISTS "whatspp_group" TEXT'
                ).format(schema_name=self.sql.Identifier(schema))
            )
            cur.execute(
                self.sql.SQL(
                    'ALTER TABLE {schema_name}.all_contacts ADD COLUMN IF NOT EXISTS "whatsapp_group" TEXT'
                ).format(schema_name=self.sql.Identifier(schema))
            )
            cur.execute(
                self.sql.SQL(
                    'ALTER TABLE {schema_name}.all_contacts ADD COLUMN IF NOT EXISTS "time" TIMESTAMPTZ NOT NULL DEFAULT NOW()'
                ).format(schema_name=self.sql.Identifier(schema))
            )

    def _get_all_contacts_group_columns(self, db_conn):
        schema = self.get_db_schema()
        with db_conn.cursor() as cur:
            cur.execute(
                """
                SELECT column_name, is_nullable
                FROM information_schema.columns
                WHERE table_schema = %s
                  AND table_name = 'all_contacts'
                """,
                (schema,),
            )
            cols = {}
            for row in cur.fetchall():
                if not row or not row[0]:
                    continue
                cols[row[0]] = (str(row[1]).upper() == "YES")
            return cols

    def _get_existing_group_phones(self, db_conn, group_name):
        schema = self.get_db_schema()
        cols = self._get_all_contacts_group_columns(db_conn)
        has_whatspp = "whatspp_group" in cols
        has_whatsapp = "whatsapp_group" in cols

        if has_whatspp and has_whatsapp:
            where_sql = '("whatspp_group" = %s OR "whatsapp_group" = %s)'
            params = (group_name, group_name)
        elif has_whatspp:
            where_sql = '"whatspp_group" = %s'
            params = (group_name,)
        else:
            where_sql = '"whatsapp_group" = %s'
            params = (group_name,)

        with db_conn.cursor() as cur:
            cur.execute(
                self.sql.SQL(
                    """
                    SELECT "Phone"
                    FROM {schema_name}.all_contacts
                    WHERE {where_sql}
                      AND "Phone" IS NOT NULL
                    """
                ).format(
                    schema_name=self.sql.Identifier(schema),
                    where_sql=self.sql.SQL(where_sql),
                ),
                params,
            )
            values = []
            for row in cur.fetchall():
                if not row or len(row) == 0:
                    continue
                raw = row[0]
                if raw is None:
                    continue
                phone = str(raw).strip()
                if phone:
                    values.append(phone)
            return set(values)

    def _insert_new_group_phones(self, db_conn, group_name, phones):
        schema = self.get_db_schema()
        cols = self._get_all_contacts_group_columns(db_conn)
        has_whatspp = "whatspp_group" in cols
        has_whatsapp = "whatsapp_group" in cols
        inserted = 0
        with db_conn.cursor() as cur:
            for phone in phones:
                if has_whatspp and has_whatsapp:
                    cur.execute(
                        self.sql.SQL(
                            """
                            INSERT INTO {schema_name}.all_contacts
                            ("Phone", "whatspp_group", "whatsapp_group", "time")
                            VALUES (%s, %s, %s, NOW())
                            """
                        ).format(schema_name=self.sql.Identifier(schema)),
                        (phone, group_name, group_name),
                    )
                elif has_whatspp:
                    cur.execute(
                        self.sql.SQL(
                            """
                            INSERT INTO {schema_name}.all_contacts
                            ("Phone", "whatspp_group", "time")
                            VALUES (%s, %s, NOW())
                            """
                        ).format(schema_name=self.sql.Identifier(schema)),
                        (phone, group_name),
                    )
                else:
                    cur.execute(
                        self.sql.SQL(
                            """
                            INSERT INTO {schema_name}.all_contacts
                            ("Phone", "whatsapp_group", "time")
                            VALUES (%s, %s, NOW())
                            """
                        ).format(schema_name=self.sql.Identifier(schema)),
                        (phone, group_name),
                    )
                inserted += 1
        return inserted

    def _generate_unique_recovery_scrap_id(self, db_conn, digits=6, max_attempts=300):
        schema = self.get_db_schema()
        lower = 10 ** (max(1, int(digits)) - 1)
        upper = (10 ** max(1, int(digits))) - 1
        with db_conn.cursor() as cur:
            for _ in range(max_attempts):
                numeric = str(random.randint(lower, upper))
                candidate = f"GRP-{numeric}"
                cur.execute(
                    self.sql.SQL(
                        """
                        SELECT 1
                        FROM {schema_name}.scrape_group_runs
                        WHERE scrap_id = %s
                        LIMIT 1
                        """
                    ).format(schema_name=self.sql.Identifier(schema)),
                    (candidate,),
                )
                if cur.fetchone() is None:
                    return candidate
        return f"GRP-{str(int(datetime.now().timestamp() * 1000))[-max(6, int(digits)):]}"

    def _run_recovery_job(self, base_scrap_id, target_group_name):
        self.reset()
        self.state["running"] = True
        self.state["base_scrap_id"] = base_scrap_id
        self.state["group_name"] = target_group_name
        self.state["started_at"] = datetime.now().isoformat()
        self._log(f"Starting recovery. Base scrap_id={base_scrap_id}, group={target_group_name}")

        browser = None
        db_conn = None
        try:
            db_conn = self.get_db_connection()
            self.ensure_scrape_runs_table(db_conn)
            self._ensure_all_contacts_table(db_conn)
            self.state["recovery_scrap_id"] = self._generate_unique_recovery_scrap_id(
                db_conn, digits=6
            )
            self._log(f"Recovery Scrap ID: {self.state['recovery_scrap_id']}")

            user_data_dir = get_playwright_user_data_dir()

            with sync_playwright() as p:
                launch_kwargs = get_playwright_launch_kwargs(default_headless=False)
                self._log(
                    "Playwright config -> "
                    f"headless={launch_kwargs.get('headless')} "
                    f"start_maximized={'args' in launch_kwargs} "
                    f"no_viewport={launch_kwargs.get('no_viewport', False)} "
                    f"slow_mo={launch_kwargs.get('slow_mo', 0)}ms"
                )
                self._log(f"Playwright user_data_dir: {user_data_dir}")
                browser = p.chromium.launch_persistent_context(
                    user_data_dir=str(user_data_dir),
                    **launch_kwargs,
                )
                page = browser.pages[0] if browser.pages else browser.new_page()
                self._log("Opening WhatsApp Web...")
                page.goto("https://web.whatsapp.com")
                login_selector = _wait_for_any_selector(
                    page,
                    (
                        "[data-testid='chat-list']",
                        "div[aria-label='Chat list']",
                        "#pane-side",
                    ),
                    timeout_ms=5000,
                )
                login_state = "reused_logged_in" if login_selector else "logged_in_after_wait"
                if not login_selector:
                    _wait_for_any_selector(
                        page,
                        (
                            "[data-testid='chat-list']",
                            "div[aria-label='Chat list']",
                            "#pane-side",
                        ),
                        timeout_ms=120000,
                    )
                self._log("WhatsApp loaded.")
                try:
                    _, session_line = save_whatsapp_session_snapshot(
                        page=page,
                        flow_name="recovery_worker",
                        user_data_dir=str(user_data_dir),
                        login_state=login_state,
                    )
                    self._log(f"Session snapshot saved -> {session_line}")
                except Exception as session_exc:
                    self._log(f"Session snapshot warning: {session_exc}")

                if not open_group_and_members(page):
                    raise RuntimeError("Could not open Groups filter.")

                initial_visible = page.locator(
                    "div[aria-label='Chat list'][role='grid'] > div[role='row']"
                ).count()
                self._log(f"Initially visible groups: {initial_visible}")

                found_row, row_title = self._find_target_group_by_search(
                    page, target_group_name
                )
                scanned_count = 0
                found = found_row is not None
                if not found:
                    found_row, row_title, scanned_count = self._find_target_group_row(
                        page, target_group_name
                    )
                    found = found_row is not None
                self._log(f"Groups scanned while searching: {scanned_count}")

                if found:
                    self._log(f"Found target group in list: {row_title}")
                    found_row.click(timeout=20000)
                    page.wait_for_timeout(900)
                    actual_group_name = row_title or target_group_name
                    self.state["group_name"] = actual_group_name

                    if not open_group_info(page):
                        raise RuntimeError(
                            f"Could not open group info for {actual_group_name}"
                        )
                    metadata = extract_group_metadata(page, group_name=actual_group_name)
                    if not open_members_from_group_info(page):
                        raise RuntimeError(
                            f"Could not open members for {actual_group_name}"
                        )

                    contacts = extract_member_contacts(page)
                    return_to_group_list(page)

                    normalized_contacts = []
                    for c in contacts:
                        if c is None:
                            continue
                        value = str(c).strip()
                        if value:
                            normalized_contacts.append(value)
                    normalized_contacts = list(dict.fromkeys(normalized_contacts))
                    self.state["scrapped_contacts_count"] = len(normalized_contacts)
                    self._log(
                        f"Scrapped contacts in group now: {self.state['scrapped_contacts_count']}"
                    )

                    existing = self._get_existing_group_phones(db_conn, actual_group_name)
                    new_contacts = [c for c in normalized_contacts if c not in existing]
                    inserted = self._insert_new_group_phones(
                        db_conn, actual_group_name, new_contacts
                    )
                    save_group_metadata_to_postgres(
                        actual_group_name,
                        {
                            **metadata,
                            "group_name": actual_group_name,
                            "source_scrap_id": self.state["recovery_scrap_id"],
                            "last_scraped_at": self.state["started_at"],
                        },
                    )
                    self.state["new_contacts"] = new_contacts
                    self.state["new_contacts_count"] = inserted
                    self._log(f"Newly joined contacts found: {inserted}")

                    self.save_scrape_group_row(
                        db_conn=db_conn,
                        scrap_id=self.state["recovery_scrap_id"],
                        group_index=1,
                        groups_total=1,
                        group_name=actual_group_name,
                        scrapped_contacts_count=self.state["scrapped_contacts_count"],
                        total_contacts_in_loop=inserted,
                        imported_groups_in_loop=1,
                        loop_started_at=self.state["started_at"],
                    )
                if not found:
                    raise RuntimeError(
                        f"Group not found on WhatsApp list: {target_group_name}"
                    )

            self.state["last_result"] = (
                f"Recovery complete for {self.state['group_name']}. "
                f"New numbers found: {self.state['new_contacts_count']}."
            )
            self._log(self.state["last_result"])

        except Exception as exc:
            self.state["last_error"] = str(exc)
            self._log(f"Error: {exc}")
            traceback.print_exc()
        finally:
            try:
                if browser:
                    browser.close()
            except Exception:
                pass
            try:
                if db_conn:
                    db_conn.close()
            except Exception:
                pass
            self.state["running"] = False
            self.state["finished_at"] = datetime.now().isoformat()

    def start(self, base_scrap_id, target_group_name, mode="by_scrap_id"):
        if self.state["running"] or self.is_scrape_running():
            return False, "Another scrape/recovery job is already running."
        if self.sql is None:
            return (
                False,
                "psycopg2 is not installed. Install it with: pip install psycopg2-binary",
            )
        mode = str(mode or "by_scrap_id").strip().lower()
        if mode not in ("manual", "by_scrap_id"):
            mode = "by_scrap_id"
        if mode == "by_scrap_id" and not base_scrap_id:
            return False, "scrap_id is required for 'Select scrap id + group' mode."
        if not target_group_name:
            return False, "group_name is required."

        threading.Thread(
            target=self._run_recovery_job,
            args=(base_scrap_id, target_group_name),
            daemon=True,
        ).start()
        return True, None

    def status(self):
        return {
            "running": self.state["running"],
            "last_error": self.state["last_error"],
            "last_result": self.state["last_result"],
            "base_scrap_id": self.state["base_scrap_id"],
            "recovery_scrap_id": self.state["recovery_scrap_id"],
            "group_name": self.state["group_name"],
            "scrapped_contacts_count": self.state["scrapped_contacts_count"],
            "new_contacts_count": self.state["new_contacts_count"],
            "new_contacts": self.state["new_contacts"],
            "logs": self.state["logs"],
            "started_at": self.state["started_at"],
            "finished_at": self.state["finished_at"],
        }
