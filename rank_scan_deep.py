# -*- coding: utf-8 -*-
"""Playwright 기반 네이버 쇼핑 딥 순위 스캔 (1000위 초과 · 로컬 PC 전용)."""
from __future__ import annotations

import random
import time
from typing import Callable

from rank_tracker import (
    MAX_SCAN_DEPTH,
    MOBILE_UA,
    NAVER_API_MAX_START,
    RANKS_PER_PAGE,
    _extract_ordered_product_ids,
    _shopping_search_url,
)

try:
    from playwright.sync_api import sync_playwright

    _PW_OK = True
except ImportError:
    _PW_OK = False

try:
    from playwright_stealth import stealth_sync

    _STEALTH_OK = True
except ImportError:
    _STEALTH_OK = False

DEFAULT_DEEP_PAGES = MAX_SCAN_DEPTH // RANKS_PER_PAGE  # 250 ≒ 10000위
ITEMS_PER_PAGE = RANKS_PER_PAGE

_EXTRACT_JS = """() => {
    const links = Array.from(document.querySelectorAll(
        'a[href*="/products/"], a[href*="smartstore.naver.com"]'
    ));
    const seen = new Set();
    const ordered = [];
    for (const a of links) {
        const href = a.href || '';
        const m = href.match(/\\/products\\/(\\d+)/);
        if (m && !seen.has(m[1])) {
            seen.add(m[1]);
            ordered.push(m[1]);
        }
    }
    return ordered;
}"""


def playwright_available() -> bool:
    return _PW_OK


def _page_product_ids(page, html: str) -> list[str]:
    try:
        ids = page.evaluate(_EXTRACT_JS)
        if ids:
            return ids
    except Exception:
        pass
    return _extract_ordered_product_ids(html)


def check_product_rank_deep(
    keyword: str,
    product_id: str,
    *,
    max_pages: int = DEFAULT_DEEP_PAGES,
    start_page: int = 1,
    rank_offset: int = 0,
    logger: Callable[[str], None] | None = None,
    headless: bool = True,
) -> int | None:
    """
    Playwright 모바일 페이징 — 1000위 초과 구간은 start_page=26, rank_offset=1000 권장.
    Cloudtype/Vercel에서는 실행하지 마세요.
    """
    if not _PW_OK:
        raise RuntimeError("playwright 미설치 — pip install playwright && playwright install chromium")

    def log(msg: str) -> None:
        if logger:
            logger(msg)

    product_id = str(product_id).strip()
    keyword = keyword.strip()
    depth = min(max_pages * ITEMS_PER_PAGE, MAX_SCAN_DEPTH)
    log(
        f"🔍 [Playwright 딥스캔] '{keyword}' 상품 {product_id} "
        f"(페이지 {start_page}~{max_pages} · 최대 {depth}위)"
    )

    cumulative_rank = rank_offset

    with sync_playwright() as p:
        device = p.devices.get("Galaxy S9+") or p.devices["Pixel 5"]
        ctx_args = {k: v for k, v in device.items() if k != "default_browser_type"}
        ctx_args["user_agent"] = MOBILE_UA
        browser = p.chromium.launch(
            headless=headless,
            args=["--disable-blink-features=AutomationControlled", "--no-sandbox"],
        )
        context = browser.new_context(**ctx_args, locale="ko-KR", timezone_id="Asia/Seoul")
        page = context.new_page()
        if _STEALTH_OK:
            stealth_sync(page)

        try:
            page.goto("https://m.naver.com/", wait_until="domcontentloaded", timeout=20_000)
            time.sleep(random.uniform(1.0, 2.0))
        except Exception:
            pass

        try:
            for page_num in range(start_page, max_pages + 1):
                start = (page_num - 1) * ITEMS_PER_PAGE + 1
                url = _shopping_search_url(keyword, start=start)
                log(f"   📄 [deep] {page_num}페이지 (start={start})")

                try:
                    page.goto(url, wait_until="networkidle", timeout=30_000, referer="https://m.naver.com/")
                    time.sleep(random.uniform(1.2, 2.0))
                    page.mouse.wheel(0, 800)
                    time.sleep(random.uniform(0.5, 1.0))
                    try:
                        page.wait_for_selector(
                            'a[href*="/products/"], a[href*="smartstore"]',
                            timeout=8_000,
                        )
                    except Exception:
                        pass
                    html = page.content()
                except Exception as exc:
                    log(f"   ⚠️ 페이지 로드 실패 — {exc}")
                    break

                if "captcha" in html.lower() or "비정상적인" in html:
                    log("   ⚠️ 봇 차단(Captcha) — 중단")
                    break

                page_ids = _page_product_ids(page, html)
                if not page_ids:
                    log(f"   ⚠️ {page_num}페이지 결과 없음 — 탐색 종료")
                    break

                for pid in page_ids:
                    cumulative_rank += 1
                    if pid == product_id:
                        log(f"✅ [deep] 상품 {product_id}: {cumulative_rank}위 ({page_num}페이지)")
                        return cumulative_rank

                if page_num < max_pages:
                    time.sleep(random.uniform(0.6, 1.2))
        finally:
            browser.close()

    log(f"⚠️ [deep] 상품 {product_id} {cumulative_rank}위 이후 미발견")
    return None
