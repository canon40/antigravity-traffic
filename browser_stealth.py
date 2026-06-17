# -*- coding: utf-8 -*-
"""Playwright 브라우저 봇 탐지 완화 — 네이버 로그인용."""

STEALTH_INIT_SCRIPT = """
(() => {
  try {
    Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
  } catch (e) {}
  try {
    window.chrome = window.chrome || { runtime: {} };
  } catch (e) {}
  try {
    Object.defineProperty(navigator, 'languages', {
      get: () => ['ko-KR', 'ko', 'en-US', 'en'],
    });
  } catch (e) {}
})();
"""

BROWSER_LAUNCH_ARGS = [
    "--start-maximized",
    "--disable-blink-features=AutomationControlled",
    "--disable-infobars",
    "--no-first-run",
    "--no-default-browser-check",
]

IGNORE_AUTOMATION_ARGS = ["--enable-automation"]


async def apply_stealth_to_context(context) -> None:
    """persistent context 생성 직후 호출."""
    try:
        await context.add_init_script(STEALTH_INIT_SCRIPT)
    except Exception:
        pass
