from pathlib import Path
import re
import os

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright
from core.group_db_exporter import save_group_contacts_to_postgres


PHONE_RE = re.compile(r"\+\d[\d\s]{6,}\d")
MEMBER_COUNT_RE = re.compile(r"(\d[\d,]*)\s+members?\b", re.IGNORECASE)
COMMUNITY_PANEL_MARKERS = (
    "groups in this community",
    "manage groups",
    "add groups",
    "community settings",
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


def _first_nonempty_text(page, selectors, timeout_ms=800):
    for selector in selectors:
        try:
            node = page.locator(selector).first
            if node.count() == 0:
                continue
            node.wait_for(state="visible", timeout=timeout_ms)
            text = (node.inner_text() or "").strip()
            if text:
                return text
        except Exception:
            continue
    return ""


def extract_group_metadata(page, group_name="", timeout_ms=4000):
    metadata = {
        "group_name": (group_name or "").strip(),
        "description": "",
        "members_label": "",
        "members_count": None,
        "created_by": "",
        "created_on": "",
        "invite_link": "",
    }

    try:
        page.wait_for_timeout(350)

        description = _first_nonempty_text(
            page,
            [
                "div[role='textbox'][contenteditable='false']",
                "div[aria-label*='Description' i] span[dir='auto']",
                "div:has-text('Description') + div span[dir='auto']",
            ],
            timeout_ms=900,
        )
        if description and description.lower() != (group_name or "").strip().lower():
            metadata["description"] = description

        members_label = _first_nonempty_text(
            page,
            [
                "div[role='button'][aria-label*='members' i]:not([aria-label*='add member' i])",
                "div[role='button']:has-text('members'):not(:has-text('Add member'))",
            ],
            timeout_ms=1200,
        )
        if members_label:
            metadata["members_label"] = members_label
            match = MEMBER_COUNT_RE.search(members_label)
            if match:
                try:
                    metadata["members_count"] = int(match.group(1).replace(",", ""))
                except Exception:
                    metadata["members_count"] = None

        panel_text = ""
        try:
            panel_text = (page.locator("#app").inner_text(timeout=1200) or "").strip()
        except Exception:
            panel_text = ""

        if panel_text:
            created_match = re.search(
                r"(?:Created by|created by)\s+([^\n]+)",
                panel_text,
                re.IGNORECASE,
            )
            if created_match:
                metadata["created_by"] = created_match.group(1).strip()

            created_on_match = re.search(
                r"(?:Created on|created on)\s+([^\n]+)",
                panel_text,
                re.IGNORECASE,
            )
            if created_on_match:
                metadata["created_on"] = created_on_match.group(1).strip()

            invite_match = re.search(r"(https://chat\.whatsapp\.com/[A-Za-z0-9]+)", panel_text)
            if invite_match:
                metadata["invite_link"] = invite_match.group(1).strip()

        return metadata
    except Exception:
        return metadata


def click_groups_filter(page, timeout_ms=30000):
    try:
        tablist = page.locator("div[role='tablist'][aria-label='chat-list-filters']")
        tablist.wait_for(state="visible", timeout=timeout_ms)
        page.wait_for_timeout(700)

        selectors = [
            page.locator("#group-filter").first,
            page.get_by_role("tab", name="Groups").first,
            page.locator("button:has-text('Groups')").first,
        ]
        for target in selectors:
            if target.count() == 0:
                continue
            target.wait_for(state="visible", timeout=timeout_ms)
            target.click(timeout=timeout_ms)
            return True
        return False
    except PlaywrightTimeoutError:
        return False


def open_group_info(page, timeout_ms=20000):
    try:
        header = page.locator("#main header").first
        header.wait_for(state="visible", timeout=timeout_ms)
        header.click(timeout=timeout_ms)
        return True
    except PlaywrightTimeoutError:
        return False


def is_community_group_info(page, timeout_ms=1200):
    """
    Detect community info panel using community-specific sections.
    This lets us skip quickly instead of waiting for missing members controls.
    """
    try:
        panel_text = (page.locator("#app").inner_text(timeout=timeout_ms) or "").lower()
    except Exception:
        return False
    return any(marker in panel_text for marker in COMMUNITY_PANEL_MARKERS)


def open_members_from_group_info(page, timeout_ms=20000):
    if is_community_group_info(page, timeout_ms=900):
        return False

    try:
        members_button = page.locator(
            "div[role='button'][aria-label*='members' i]:not([aria-label*='add member' i]), "
            "div[role='button']:has-text('members'):not(:has-text('Add member'))"
        ).first
        # Fast first pass to avoid wasting time on communities/non-group screens.
        try:
            members_button.wait_for(state="visible", timeout=1400)
        except PlaywrightTimeoutError:
            if is_community_group_info(page, timeout_ms=900):
                return False
            members_button.wait_for(state="visible", timeout=timeout_ms)
        members_button.click(timeout=timeout_ms)

        members_modal = page.locator("div[data-animate-modal-body='true']").first
        members_modal.wait_for(state="visible", timeout=timeout_ms)
        return True
    except PlaywrightTimeoutError:
        return False


def extract_member_contacts(page, timeout_ms=20000):
    contacts = set()

    try:
        members_modal = page.locator("div[data-animate-modal-body='true']").first
        members_modal.wait_for(state="visible", timeout=timeout_ms)

        rows = members_modal.locator("div[role='listitem']")
        rows.first.wait_for(state="visible", timeout=timeout_ms)

        # Start from top
        rows.first.evaluate(
            """
            (row) => {
              let node = row.parentElement;
              while (node && node !== document.body) {
                if (node.scrollHeight > node.clientHeight + 5) {
                  node.scrollTop = 0;
                  return;
                }
                node = node.parentElement;
              }
            }
            """
        )
        page.wait_for_timeout(500)

        print("Scraping numbers...\n")

        no_new_rounds = 0
        no_move_rounds = 0

        for _ in range(600):
            before_total = len(contacts)

            # Primary: number spans in visible rows
            number_nodes = members_modal.locator("span[dir='auto'][title^='+']")
            for i in range(number_nodes.count()):
                raw = (number_nodes.nth(i).get_attribute("title") or "").strip()
                if not raw:
                    continue
                m = PHONE_RE.search(raw)
                if m:
                    number = re.sub(r"\s+", " ", m.group(0)).strip()
                    if number not in contacts:
                        contacts.add(number)
                        print("FOUND:", number)

            # Fallback: visible text nodes
            fallback_nodes = members_modal.locator("div[role='listitem'] span[dir='auto']")
            for i in range(fallback_nodes.count()):
                raw = (fallback_nodes.nth(i).inner_text() or "").strip()
                if not raw:
                    continue
                m = PHONE_RE.search(raw)
                if m:
                    number = re.sub(r"\s+", " ", m.group(0)).strip()
                    if number not in contacts:
                        contacts.add(number)
                        print("FOUND:", number)

            # Click View all if shown
            view_all = members_modal.locator("div[role='button']:has-text('View all')").first
            if view_all.count() > 0:
                try:
                    view_all.click(timeout=1200)
                    page.wait_for_timeout(500)
                except Exception:
                    pass

            # Scroll real virtualized list ancestor
            move_info = rows.first.evaluate(
                """
                (row) => {
                  let node = row.parentElement;
                  while (node && node !== document.body) {
                    if (node.scrollHeight > node.clientHeight + 5) {
                      const before = node.scrollTop;
                      const step = Math.max(280, Math.floor(node.clientHeight * 0.9));
                      node.scrollTop = Math.min(before + step, node.scrollHeight);
                      const after = node.scrollTop;
                      const atEnd = after >= node.scrollHeight - node.clientHeight - 2;
                      return { moved: after > before, atEnd, before, after, client: node.clientHeight, full: node.scrollHeight };
                    }
                    node = node.parentElement;
                  }
                  return { moved: false, atEnd: false, before: 0, after: 0, client: 0, full: 0 };
                }
                """
            )
            print("SCROLL:", move_info)
            print("Collected so far:", len(contacts))

            if len(contacts) == before_total:
                no_new_rounds += 1
            else:
                no_new_rounds = 0

            if not move_info.get("moved", False):
                no_move_rounds += 1
            else:
                no_move_rounds = 0

            if move_info.get("atEnd", False) and no_new_rounds >= 12:
                print("Reached end of members list")
                break

            if no_move_rounds >= 10 and no_new_rounds >= 12:
                print("No further movement in list")
                break

            # wheel nudge while hovering list area
            rows.first.hover()
            page.mouse.wheel(0, 1200)
            page.wait_for_timeout(450)

        return sorted(contacts)

    except PlaywrightTimeoutError:
        print("Members modal not found")
        return []


def open_group_and_members(page):
    page.wait_for_selector("#pane-side", timeout=30000)
    return click_groups_filter(page)


def get_open_chat_title(page, fallback_name="", timeout_ms=8000):
    """
    Read the currently opened chat title from the top header in the main pane.
    This avoids picking community subtitle text from the left chat list row.
    """
    try:
        header = page.locator("#main header").first
        header.wait_for(state="visible", timeout=timeout_ms)

        candidate_selectors = [
            "span[dir='auto']",
            "h1",
            "div[title]",
        ]

        for selector in candidate_selectors:
            nodes = header.locator(selector)
            count = nodes.count()
            for i in range(count):
                raw = (nodes.nth(i).inner_text() or "").strip()
                if not raw:
                    continue
                # Skip obvious non-title helper text if encountered.
                if raw.lower() in {"online", "typing..."}:
                    continue
                return raw
    except PlaywrightTimeoutError:
        pass

    return fallback_name


def return_to_group_list(page, timeout_ms=20000):
    """Close members modal/group info and return focus to left groups list."""
    try:
        # Close members modal if open.
        members_modal = page.locator("div[data-animate-modal-body='true']").first
        if members_modal.count() > 0:
            try:
                close_btn = members_modal.locator("button[aria-label='Close'], div[role='button'][aria-label='Close']").first
                if close_btn.count() > 0:
                    close_btn.click(timeout=1500)
                else:
                    page.keyboard.press("Escape")
            except Exception:
                page.keyboard.press("Escape")
            page.wait_for_timeout(500)

        # Close group info side panel if still open.
        if page.locator("text=Group info").count() > 0:
            page.keyboard.press("Escape")
            page.wait_for_timeout(500)

        page.wait_for_selector("div[aria-label='Chat list'][role='grid'] > div[role='row']", timeout=timeout_ms)
    except Exception:
        # Last resort
        page.keyboard.press("Escape")
        page.wait_for_timeout(700)


def extract_all_groups(
    page,
    on_group_complete=None,
    should_skip_group=None,
    on_group_skipped=None,
):
    """Loop all visible groups in Groups tab and extract contacts per group."""
    results = []
    rows_selector = "div[aria-label='Chat list'][role='grid'] > div[role='row']"

    group_rows = page.locator(rows_selector)
    total_groups = group_rows.count()
    print(f"Total groups found: {total_groups}")

    for idx in range(total_groups):
        group_rows = page.locator(rows_selector)
        if idx >= group_rows.count():
            break

        row = group_rows.nth(idx)
        row.wait_for(state="visible", timeout=20000)
        row.scroll_into_view_if_needed(timeout=20000)

        title_node = row.locator("span[title]").first
        row_name_fallback = (
            (title_node.get_attribute("title") or f"group-{idx + 1}").strip()
            if title_node.count() > 0
            else f"group-{idx + 1}"
        )
        print(f"\nProcessing group {idx + 1}/{total_groups}: {row_name_fallback}")

        if callable(should_skip_group):
            try:
                if should_skip_group(row_name_fallback):
                    print(f"Skipping group (already in DB): {row_name_fallback}")
                    if callable(on_group_skipped):
                        on_group_skipped(
                            {"group": row_name_fallback, "reason": "already_exists"}
                        )
                    continue
            except Exception as exc:
                print(f"Skip-check warning for {row_name_fallback}: {exc}")

        row.click(timeout=20000)
        page.wait_for_timeout(900)
        group_name = get_open_chat_title(page, fallback_name=row_name_fallback)
        print(f"Opened chat title: {group_name}")

        if callable(should_skip_group):
            try:
                if should_skip_group(group_name):
                    print(f"Skipping group (already in DB): {group_name}")
                    if callable(on_group_skipped):
                        on_group_skipped(
                            {"group": group_name, "reason": "already_exists"}
                        )
                    return_to_group_list(page)
                    continue
            except Exception as exc:
                print(f"Skip-check warning for {group_name}: {exc}")

        if not open_group_info(page):
            print(f"Could not open group info for {group_name}")
            return_to_group_list(page)
            continue

        metadata = extract_group_metadata(page, group_name=group_name)

        if not open_members_from_group_info(page):
            if is_community_group_info(page, timeout_ms=900):
                print(f"Skipping community (no members list): {group_name}")
                if callable(on_group_skipped):
                    on_group_skipped({"group": group_name, "reason": "community"})
            else:
                print(f"Could not open members for {group_name}")
                if callable(on_group_skipped):
                    on_group_skipped(
                        {"group": group_name, "reason": "members_not_found"}
                    )
            return_to_group_list(page)
            continue

        contacts = extract_member_contacts(page)
        item = {"group": group_name, "contacts": contacts, "metadata": metadata}
        results.append(item)
        print(f"Collected {len(contacts)} numbers from {group_name}")
        if callable(on_group_complete):
            try:
                on_group_complete(item)
            except Exception as exc:
                print(f"Could not save group {group_name}: {exc}")

        return_to_group_list(page)

    return results


def main():
    user_data_dir = get_playwright_user_data_dir()

    with sync_playwright() as p:
        launch_kwargs = get_playwright_launch_kwargs(default_headless=False)
        print(
            "Playwright config -> "
            f"headless={launch_kwargs.get('headless')} "
            f"start_maximized={'args' in launch_kwargs} "
            f"no_viewport={launch_kwargs.get('no_viewport', False)} "
            f"slow_mo={launch_kwargs.get('slow_mo', 0)}ms"
        )
        print(f"Playwright user_data_dir: {user_data_dir}")
        browser = p.chromium.launch_persistent_context(
            user_data_dir=str(user_data_dir),
            **launch_kwargs,
        )

        page = browser.pages[0] if browser.pages else browser.new_page()
        page.goto("https://web.whatsapp.com")

        print("Scan QR if needed...")
        page.wait_for_selector("#pane-side", timeout=120000)
        print("Logged in")

        if open_group_and_members(page):
            created_tables = []

            def save_one_group_result(item):
                table_name = save_group_contacts_to_postgres(
                    item.get("group", "group"), item.get("contacts", [])
                )
                created_tables.append(table_name)
                print(f"Saved DB table: {table_name}")

            all_group_results = extract_all_groups(
                page, on_group_complete=save_one_group_result
            )

            print("\n==== FINAL GROUP CONTACTS ====\n")
            grand_total = 0
            for item in all_group_results:
                print(f"[{item['group']}]")
                for c in item["contacts"]:
                    print(c)
                print(f"Group total: {len(item['contacts'])}\n")
                grand_total += len(item["contacts"])

            print(f"Groups processed: {len(all_group_results)}")
            print(f"Grand total numbers (all groups): {grand_total}")
            print("\nCreated/updated DB tables:")
            for table_name in created_tables:
                print(table_name)
        else:
            print("Could not open members list")

        input("\nPress ENTER to close...")
        browser.close()


if __name__ == "__main__":
    main()
