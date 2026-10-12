import asyncio
from datetime import datetime
from pathlib import Path

from playwright.async_api import TimeoutError, async_playwright

PROFILE_DIRS = [f"profile_{i}" for i in range(5)]
TARGET_NUMBERS = [
    "923140474096",
    "923210096644",
    "923214254505",
    "923244342333",
    "923170431427",
    "923214761119",
    "923325396161",
]
MESSAGE_TEXT = "HELLO"
WHATSAPP_WEB_URL = "https://web.whatsapp.com"
RESULT_FILE = Path(__file__).resolve().parent.parent / "data" / "result.txt"


def _normalize_phone(value: str) -> str:
    return "".join(ch for ch in str(value or "") if ch.isdigit())


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _init_result_file() -> None:
    header = (
        f"{_now()} | job=start | total_numbers={len(TARGET_NUMBERS)} | message={MESSAGE_TEXT}\n"
    )
    RESULT_FILE.write_text(header, encoding="utf-8")


def _append_result(line: str) -> None:
    with RESULT_FILE.open("a", encoding="utf-8") as fh:
        fh.write(line.rstrip() + "\n")


async def _is_whatsapp_logged_in(page) -> bool:
    selectors = [
        "#pane-side",
        "div[aria-label='Chat list']",
        "[data-testid='chat-list']",
    ]
    for selector in selectors:
        try:
            node = page.locator(selector).first
            if await node.count() > 0 and await node.is_visible():
                return True
        except Exception:
            continue
    return False


async def _fill_search_field(page, locator, text_value: str) -> bool:
    value = str(text_value or "")
    try:
        await locator.fill("")
        await locator.fill(value)
        return True
    except Exception:
        pass
    try:
        await locator.click(force=True)
        await page.keyboard.press("Control+A")
        await page.keyboard.press("Backspace")
        if value:
            await page.keyboard.type(value, delay=8)
        return True
    except Exception:
        return False


async def _click_send_button_like_main_debugging(page) -> bool:
    send_selectors = [
        "div[role='button'][aria-label='Send'][aria-disabled='false']",
        "button[aria-label='Send'][aria-disabled='false']",
        "div[aria-label='Send'][aria-disabled='false']",
        "span[data-icon='wds-ic-send-filled']",
        "span[data-icon='send']",
    ]
    for _ in range(8):
        for selector in send_selectors:
            try:
                locator = page.locator(selector)
                count = await locator.count()
            except Exception:
                count = 0
            for i in range(count):
                item = locator.nth(i)
                try:
                    if not await item.is_visible():
                        continue
                    try:
                        await item.click(force=True, timeout=1800)
                    except Exception:
                        await item.click(timeout=1800)
                    await page.wait_for_timeout(120)
                    return True
                except Exception:
                    continue
        await page.wait_for_timeout(120)
    return False


async def _open_contact_chat_from_search(page, target: str):
    target_text = str(target or "").strip()
    if not target_text:
        return False, "Empty target"

    try:
        await page.locator("button[aria-label*='New']").first.click(timeout=5000)
    except Exception:
        return False, "Could not click New chat button"

    search_box = page.locator("input[aria-label='Search name or number']")
    try:
        await search_box.wait_for(state="visible", timeout=5000)
    except Exception:
        return False, "Search box not visible"

    if not await _fill_search_field(page, search_box, target_text):
        return False, "Could not fill search field"

    await page.wait_for_timeout(220)
    results = page.locator("div[role='button'][tabindex='0']")
    invalid_text = page.locator("span:has-text('not on WhatsApp')")

    try:
        await results.first.wait_for(state="visible", timeout=4200)
        found = True
    except TimeoutError:
        found = False

    if not found:
        if await invalid_text.count() > 0:
            return False, "Not on WhatsApp"
        return False, "No result found"

    for i in range(await results.count()):
        item = results.nth(i)
        try:
            if not await item.is_visible():
                continue
            try:
                await item.click(timeout=1800)
            except Exception:
                await item.click(force=True, timeout=1800)
            await page.wait_for_timeout(250)
            return True, ""
        except Exception:
            continue

    return False, "No clickable result"


async def _send_plain_text_single_message(page, text_value: str) -> bool:
    text = str(text_value or "")
    msg_box = page.locator("div[contenteditable='true'][role='textbox']")
    try:
        await msg_box.first.wait_for(state="visible", timeout=5000)
    except Exception:
        return False

    try:
        await msg_box.first.click(force=True)
    except Exception:
        try:
            await page.locator("div[contenteditable='true'][role='textbox']").first.click(force=True)
        except Exception:
            pass

    try:
        await page.keyboard.press("Control+A")
        await page.keyboard.press("Backspace")
    except Exception:
        pass

    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    for idx, line in enumerate(lines):
        if idx > 0:
            await page.keyboard.press("Shift+Enter")
        if line:
            try:
                await page.keyboard.insert_text(line)
            except Exception:
                await page.keyboard.type(line, delay=0)

    if await _click_send_button_like_main_debugging(page):
        return True

    try:
        await page.keyboard.press("Enter")
        await page.wait_for_timeout(220)
        return True
    except Exception:
        return False


async def _send_hello_to_number(page, profile_name: str, target_number: str):
    phone = _normalize_phone(target_number)
    if not phone:
        return False, "Invalid phone"

    opened, open_err = await _open_contact_chat_from_search(page, phone)
    if not opened:
        try:
            await page.keyboard.press("Escape")
        except Exception:
            pass
        return False, open_err or "Search/open failed"

    sent = await _send_plain_text_single_message(page, MESSAGE_TEXT)
    if not sent:
        return False, "Could not click Send"

    await page.wait_for_timeout(500)
    return True, "sent"


async def _launch_instance(playwright, profile_dir: str):
    profile_path = Path(profile_dir).resolve()
    profile_path.mkdir(parents=True, exist_ok=True)

    context = await playwright.chromium.launch_persistent_context(
        user_data_dir=str(profile_path),
        headless=False,
        args=["--start-maximized"],
        no_viewport=True,
    )

    page = context.pages[0] if context.pages else await context.new_page()
    await page.goto(WHATSAPP_WEB_URL, wait_until="domcontentloaded")
    print(f"[{profile_dir}] Opened WhatsApp Web")

    return {
        "name": profile_dir,
        "context": context,
        "page": page,
        "send_count": 0,
        "logged_in": False,
    }


async def _refresh_logged_in(instances):
    logged = []
    for inst in instances:
        try:
            ok = await _is_whatsapp_logged_in(inst["page"])
        except Exception:
            ok = False
        inst["logged_in"] = ok
        if ok:
            logged.append(inst)
    return logged


async def _try_send_with_fallback(number: str, preferred, logged_profiles):
    # Try preferred profile first, then others.
    ordered = [preferred] + [p for p in logged_profiles if p is not preferred]
    for profile in ordered:
        name = profile["name"]
        ok, reason = await _send_hello_to_number(profile["page"], name, number)
        status = "sent" if ok else "failed"
        _append_result(
            f"{_now()} | profile={name} | number={number} | status={status} | reason={reason}"
        )
        print(f"[{name}] {number} -> {status} ({reason})")
        if ok:
            profile["send_count"] = int(profile.get("send_count") or 0) + 1
            return True, name
    return False, ""


async def run():
    _init_result_file()
    print("Opening 5 WhatsApp profile windows...")
    instances = []

    numbers = []
    seen = set()
    for raw in TARGET_NUMBERS:
        n = _normalize_phone(raw)
        if n and n not in seen:
            seen.add(n)
            numbers.append(n)

    if not numbers:
        print("No valid target numbers.")
        _append_result(f"{_now()} | job=stop | reason=no_valid_numbers")
        return

    pending = list(numbers)

    async with async_playwright() as p:
        for profile_dir in PROFILE_DIRS:
            try:
                instances.append(await _launch_instance(p, profile_dir))
            except Exception as exc:
                print(f"[{profile_dir}] Failed to open profile: {exc}")
                _append_result(f"{_now()} | profile={profile_dir} | status=launch_failed | reason={exc}")

        if not instances:
            print("No profile instance could be started.")
            _append_result(f"{_now()} | job=stop | reason=no_profiles_started")
            return

        print("Waiting for logged-in WhatsApp profiles...")
        idle_loops = 0
        while pending:
            logged_profiles = await _refresh_logged_in(instances)

            if not logged_profiles:
                idle_loops += 1
                if idle_loops % 5 == 0:
                    print("Still waiting login... no profile is logged in yet.")
                await asyncio.sleep(2)
                continue

            idle_loops = 0
            # Balance load across logged-in profiles so distribution is even.
            logged_profiles = sorted(
                logged_profiles,
                key=lambda x: (int(x.get("send_count") or 0), x.get("name") or ""),
            )

            # In one round, give one number per logged-in profile.
            current_round = pending[: len(logged_profiles)]
            for idx, number in enumerate(current_round):
                if not pending:
                    break
                preferred = logged_profiles[idx % len(logged_profiles)]
                ok, sender = await _try_send_with_fallback(number, preferred, logged_profiles)
                pending.pop(0)
                if not ok:
                    _append_result(
                        f"{_now()} | number={number} | status=not_sent | reason=all_logged_profiles_failed"
                    )

            await asyncio.sleep(0.4)

        summary = " | ".join(
            f"{inst['name']}={int(inst.get('send_count') or 0)}" for inst in instances if inst.get("logged_in")
        ) or "no_logged_profiles"
        _append_result(f"{_now()} | job=complete | distribution={summary}")
        print("Done: attempted all numbers. See result.txt")

        print("Keeping windows open for 30 seconds before closing...")
        await asyncio.sleep(30)

        for inst in instances:
            try:
                await inst["context"].close()
            except Exception:
                pass


if __name__ == "__main__":
    asyncio.run(run())
