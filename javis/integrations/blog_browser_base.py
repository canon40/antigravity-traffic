# -*- coding: utf-8
"""블로그 플랫폼 공통 Playwright — 수동 로그인 후 세션 유지."""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any, Callable, TypeVar

_ROOT = Path(__file__).resolve().parent.parent

T = TypeVar("T")


def run_sync_playwright_job(fn: Callable[[], T], *, timeout_sec: int = 1200) -> T:
    """asyncio 루프 안에서 sync Playwright 호출 시 별도 스레드에서 실행."""
    import asyncio
    import concurrent.futures

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return fn()

    with concurrent.futures.ThreadPoolExecutor(
        max_workers=1, thread_name_prefix="jarvis-blog-pw"
    ) as pool:
        return pool.submit(fn).result(timeout=timeout_sec)


def _cfg_platform(name: str) -> dict[str, Any]:
    import json

    cfg = json.loads((_ROOT / "config" / "blog_automation.json").read_text(encoding="utf-8"))
    return (cfg.get("platforms") or {}).get(name) or {}


def browser_dir(platform: str, *, override_rel: str | None = None) -> Path:
    rel = (override_rel or _cfg_platform(platform).get("browser_dir") or f".jarvis/{platform}_browser").strip()
    p = _ROOT / rel if not rel.startswith("~") else Path.home() / rel.replace("~", "").lstrip("/\\")
    p.mkdir(parents=True, exist_ok=True)
    return p


def login_timeout(platform: str) -> int:
    try:
        return int(_cfg_platform(platform).get("login_timeout_sec") or 600)
    except ValueError:
        return 600


def headless() -> bool:
    return os.environ.get("JARVIS_BLOG_HEADLESS", "0").strip().lower() in ("1", "true", "yes")


def wait_for_url_change(
    page: Any,
    *,
    bad_url_checker: Callable[[str], bool],
    on_status: Callable[[str], None] | None = None,
    timeout_sec: int = 600,
    message: str = "로그인을 완료해 주세요.",
) -> bool:
    emit = on_status or print
    deadline = time.time() + timeout_sec
    emit("\n" + "=" * 50)
    emit(f"[대기] {message}")
    emit("★ 로그인·2FA·캡차는 직접 완료 ★")
    emit("=" * 50 + "\n")
    while time.time() < deadline:
        try:
            url = page.url or ""
        except Exception:
            url = ""
        if url and not bad_url_checker(url):
            emit(f"[인증 성공] {url[:90]}")
            return True
        time.sleep(2.5)
    emit(f"[타임아웃] {timeout_sec}초 초과")
    return False


def launch_context(platform: str, *, browser_dir_rel: str | None = None) -> tuple[Any, Any, Any]:
    """Returns (playwright, context, page). Caller must close context."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as e:
        raise RuntimeError("playwright 필요: pip install playwright && playwright install chromium") from e

    p = sync_playwright().start()
    ctx = p.chromium.launch_persistent_context(
        user_data_dir=str(browser_dir(platform, override_rel=browser_dir_rel)),
        headless=headless(),
        locale="ko-KR",
        viewport={"width": 1400, "height": 900},
        user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/131.0.0.0 Safari/537.36"
        ),
        args=[
            "--disable-blink-features=AutomationControlled",
            "--no-first-run",
            "--no-default-browser-check",
        ],
        ignore_default_args=["--enable-automation"],
    )
    page = ctx.pages[0] if ctx.pages else ctx.new_page()
    try:
        page.add_init_script(
            """
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
            window.chrome = window.chrome || { runtime: {} };
            """
        )
    except Exception:
        pass
    return p, ctx, page


def strip_underline_html(html: str) -> str:
    import re

    h = html or ""
    h = re.sub(r"</?u>", "", h, flags=re.I)
    h = re.sub(r'text-decoration\s*:\s*underline[^;]*;?', "", h, flags=re.I)
    h = re.sub(r"<span[^>]*>\s*</span>", "", h, flags=re.I)
    return h


def plain_body(text: str) -> str:
    import re

    t = strip_underline_html(text)
    t = re.sub(r"<br\s*/?>", "\n", t, flags=re.I)
    t = re.sub(r"</p>", "\n\n", t, flags=re.I)
    t = re.sub(r"<[^>]+>", "", t)
    t = re.sub(r"\n{3,}", "\n\n", t)
    return t.strip()


def _copy_clipboard(page: Any, text: str) -> None:
    try:
        import pyperclip

        pyperclip.copy(text)
    except Exception:
        page.evaluate("""(t) => navigator.clipboard.writeText(t)""", text)


def paste_in_locator(locator: Any, text: str, *, strip_underline: bool = True) -> None:
    """특정 에디터 영역에만 붙여넣기 (제목 칸 오염 방지)."""
    body = plain_body(text) if strip_underline else text
    _copy_clipboard(locator.page, body)
    locator.click(timeout=8000)
    locator.page.wait_for_timeout(200)
    locator.press("Control+A")
    locator.press("Backspace")
    locator.page.wait_for_timeout(150)
    # 네이버 SE: 무서식 붙여넣기가 막히는 경우가 많아 Ctrl+V 우선
    locator.press("Control+V")
    locator.page.wait_for_timeout(500)


def fill_title_editable(locator: Any, title: str) -> bool:
    """제목 영역에만 짧은 제목 입력."""
    t = (title or "").strip()[:200]
    if not t:
        return False
    try:
        locator.click(timeout=8000)
        locator.page.wait_for_timeout(200)
        locator.press("Control+A")
        locator.press("Backspace")
        locator.page.wait_for_timeout(100)
        try:
            locator.fill(t)
            return True
        except Exception:
            locator.press_sequentially(t, delay=35)
            return True
    except Exception:
        return False


def paste_plain_text(page: Any, text: str, *, strip_underline: bool = True) -> None:
    """레거시 — 가능하면 paste_in_locator 사용."""
    body = plain_body(text) if strip_underline else text
    _copy_clipboard(page, body)
    page.keyboard.press("Control+A")
    page.keyboard.press("Backspace")
    page.keyboard.press("Control+Shift+V")
    page.wait_for_timeout(400)
    if strip_underline:
        page.evaluate(
            """() => {
              document.querySelectorAll('u, [style*="underline"]').forEach(el => {
                const p = el.parentNode;
                while (el.firstChild) p.insertBefore(el.firstChild, el);
                p.removeChild(el);
              });
              document.querySelectorAll('[style]').forEach(el => {
                if (el.style && el.style.textDecoration === 'underline')
                  el.style.textDecoration = 'none';
              });
            }"""
        )


def upload_files_input(page: Any, paths: list[str], *, input_selector: str = "input[type='file']") -> bool:
    files = [str(Path(p)) for p in paths if p and Path(p).is_file()]
    if not files:
        return False
    try:
        loc = page.locator(input_selector)
        if loc.count() == 0:
            return False
        loc.first.set_input_files(files)
        page.wait_for_timeout(1500)
        return True
    except Exception:
        return False
