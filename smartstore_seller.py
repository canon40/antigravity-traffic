# -*- coding: utf-8 -*-
"""스마트스토어 판매자센터 — 검색설정(태그·Page Title·Meta Description) 자동 반영.

로컬 PC + Playwright 전용. Cloudtype/Vercel에서는 실행 불가.
자격증명: 환경변수 SMARTSTORE_SELLER_ID / SMARTSTORE_SELLER_PASSWORD (또는 NAVER_ID / NAVER_PW)
"""

from __future__ import annotations

import asyncio
import os
import random
from typing import Any, Callable

from rank_tracker import load_config, split_keywords_by_rank
from seo_auto_fix import ensure_product_seo, find_product

Logger = Callable[[str], None] | None

SELLER_HOME = "https://sell.smartstore.naver.com/"


def seller_credentials() -> tuple[str, str]:
    seller_id = (
        os.environ.get("SMARTSTORE_SELLER_ID", "").strip()
        or os.environ.get("NAVER_ID", "").strip()
        or os.environ.get("NAVER_ID1", "").strip()
    )
    seller_pw = (
        os.environ.get("SMARTSTORE_SELLER_PASSWORD", "").strip()
        or os.environ.get("NAVER_PW", "").strip()
        or os.environ.get("NAVER_PW1", "").strip()
    )
    return seller_id, seller_pw


def products_to_apply(*, unranked_only: bool = True) -> list[dict[str, Any]]:
    """config + 순위 기준으로 판매자센터에 반영할 상품 목록."""
    config = load_config()
    if unranked_only:
        unranked, _ranked = split_keywords_by_rank(config)
        pids: list[str] = []
        seen: set[str] = set()
        for row in unranked:
            pid = str(row.get("product_id") or "").strip()
            if pid and pid not in seen:
                seen.add(pid)
                pids.append(pid)
    else:
        pids = [
            str(p.get("id") or "").strip()
            for p in (config.get("products") or [])
            if isinstance(p, dict) and p.get("id")
        ]

    items: list[dict[str, Any]] = []
    for pid in pids:
        ensure_product_seo(config, pid)
        config = load_config()
        hit = find_product(config, product_id=pid)
        if not hit:
            continue
        product, _ = hit
        items.append(
            {
                "product_id": pid,
                "name": (product.get("name") or "").strip(),
                "meta_title": (product.get("meta_title") or product.get("name") or "")[:70],
                "meta_description": (product.get("meta_description") or "")[:160],
                "tags": list(product.get("tags") or [])[:10],
            }
        )
    return items


def _product_edit_urls(product_id: str) -> list[str]:
    pid = str(product_id).strip()
    return [
        f"{SELLER_HOME}#/products/origin-product/update/no/{pid}",
        f"{SELLER_HOME}#/products/origin-products/{pid}",
        f"{SELLER_HOME}#/products/manage/detail?productNo={pid}",
        f"{SELLER_HOME}#/products/update?productNo={pid}",
    ]


async def _open_product_edit(page, product_id: str, log: Logger) -> bool:
    pid = str(product_id).strip()

    # 1) 상품관리에서 검색
    try:
        await page.goto(f"{SELLER_HOME}#/products/manage", wait_until="domcontentloaded", timeout=60000)
        await _delay(2.5, 4.0)
        for sel in (
            "input[placeholder*='상품명']",
            "input[placeholder*='상품번호']",
            "input[placeholder*='검색']",
            "input[type='search']",
        ):
            box = page.locator(sel).first
            if await box.count() > 0:
                await box.fill(pid)
                await page.keyboard.press("Enter")
                await _delay(2.0, 3.0)
                break
        for sel in (
            f"a:has-text('{pid}')",
            "button:has-text('수정')",
            "a:has-text('수정')",
            "button:has-text('상품 수정')",
        ):
            btn = page.locator(sel).first
            if await btn.count() > 0:
                await btn.click(timeout=8000)
                await _delay(2.5, 4.0)
                return True
    except Exception as exc:
        if log:
            log(f"   [WARN] 상품관리 검색 실패: {exc}")

    # 2) 직접 URL
    for url in _product_edit_urls(pid):
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=60000)
            await _delay(3.0, 4.5)
            body = (await page.content())[:8000]
            if pid in body or "검색" in body or "Page Title" in body or "Meta" in body:
                return True
        except Exception:
            continue
    return False


async def _fill_inputs_near_text(page, anchor: str, value: str) -> bool:
    if not value:
        return False
    try:
        section = page.locator(f"text={anchor}").first
        if await section.count() == 0:
            return False
        container = section.locator("xpath=ancestor::div[contains(@class,'form') or contains(@class,'row') or contains(@class,'item')][1]")
        if await container.count() == 0:
            container = section.locator("xpath=..")
        inp = container.locator("input, textarea").first
        if await inp.count() > 0:
            await inp.fill(value)
            return True
    except Exception:
        pass
    return False


async def _delay(lo: float = 0.4, hi: float = 1.2) -> None:
    await asyncio.sleep(random.uniform(lo, hi))


async def _is_seller_dashboard(page) -> bool:
    url = page.url or ""
    if "nid.naver.com" in url:
        return False
    try:
        if await page.get_by_text("로그인하기", exact=False).count() > 0:
            return False
        if await page.get_by_text("지금 시작하기", exact=False).count() > 0:
            return False
    except Exception:
        pass
    if "#/" in url and "sell.smartstore.naver.com" in url:
        return True
    try:
        if await page.locator("text=상품관리").count() > 0:
            return True
        if await page.locator("text=판매관리").count() > 0:
            return True
    except Exception:
        pass
    return False


async def _login_naver(page, seller_id: str, seller_pw: str, log: Logger) -> bool:
    if log:
        log(f"[로그인] 판매자센터 ({seller_id})")
    await page.goto(SELLER_HOME, wait_until="domcontentloaded", timeout=60000)
    await _delay(1.5, 2.5)

    if await _is_seller_dashboard(page):
        if log:
            log("[OK] 이미 로그인된 세션")
        return True

    # 랜딩 페이지 → 로그인하기
    for sel in (
        "a:has-text('로그인하기')",
        "button:has-text('로그인하기')",
        "a:has-text('로그인')",
        "button:has-text('로그인')",
    ):
        btn = page.locator(sel).first
        if await btn.count() > 0:
            try:
                await btn.click(timeout=8000)
                await _delay(1.0, 2.0)
                break
            except Exception:
                continue

    if "nid.naver.com" in (page.url or ""):
        try:
            await page.wait_for_selector("#id", timeout=20000)
            await page.fill("#id", seller_id)
            await _delay(0.3, 0.6)
            await page.fill("#pw", seller_pw)
            await _delay(0.3, 0.6)
            for sel in (".btn_login", "#log\\.login", "button[type='submit']"):
                btn = page.locator(sel).first
                if await btn.count() > 0:
                    await btn.click()
                    break
            else:
                await page.keyboard.press("Enter")
            await _delay(2.0, 4.0)
        except Exception as exc:
            if log:
                log(f"[WARN] 자동 로그인 실패 — 브라우저에서 직접 완료: {exc}")
            if log:
                log("   90초 대기 중…")
            await asyncio.sleep(90)

    deadline = asyncio.get_event_loop().time() + 120
    while asyncio.get_event_loop().time() < deadline:
        if await _is_seller_dashboard(page):
            if log:
                log("[OK] 판매자센터 로그인 완료")
            return True
        if "sell.smartstore.naver.com" in (page.url or "") and "nid.naver.com" not in (page.url or ""):
            await page.goto(f"{SELLER_HOME}#/home/dashboard", wait_until="domcontentloaded", timeout=60000)
            await _delay(2.0, 3.0)
            if await _is_seller_dashboard(page):
                if log:
                    log("[OK] 대시보드 진입")
                return True
        await asyncio.sleep(2)

    if log:
        log("[FAIL] 로그인 시간 초과")
    return False


async def _fill_by_label(page, labels: list[str], value: str) -> bool:
    if not value:
        return False
    for label in labels:
        try:
            loc = page.get_by_label(label, exact=False)
            if await loc.count() > 0:
                await loc.first.fill(value)
                return True
        except Exception:
            pass
        try:
            loc = page.locator(f"input[placeholder*='{label}'], textarea[placeholder*='{label}']")
            if await loc.count() > 0:
                await loc.first.fill(value)
                return True
        except Exception:
            pass
    return False


async def _fill_tags(page, tags: list[str]) -> bool:
    if not tags:
        return False
    tag_text = ",".join(tags[:10])
    for label in ("태그", "검색태그", "상품 태그"):
        if await _fill_by_label(page, [label], tag_text):
            return True
    try:
        loc = page.locator("input[name*='tag'], input[id*='tag']").first
        if await loc.count() > 0:
            await loc.fill(tag_text)
            return True
    except Exception:
        pass
    return False


async def _scroll_to_search_section(page) -> None:
    for text in ("검색설정", "검색 설정", "Page Title", "Meta description", "메타"):
        try:
            el = page.get_by_text(text, exact=False).first
            if await el.count() > 0:
                await el.scroll_into_view_if_needed(timeout=5000)
                await _delay(0.5, 1.0)
                return
        except Exception:
            continue
    await page.mouse.wheel(0, 2400)
    await _delay()


async def _apply_one_product(page, item: dict[str, Any], log: Logger) -> dict[str, Any]:
    pid = item["product_id"]
    name = item.get("name") or pid
    if log:
        log(f"[SEO] 상품 반영: {name} ({pid})")

    if not await _open_product_edit(page, pid, log):
        try:
            os.makedirs(os.path.join(os.path.dirname(__file__), "data", "smartstore_debug"), exist_ok=True)
            shot = os.path.join(os.path.dirname(__file__), "data", "smartstore_debug", f"fail_{pid}.png")
            await page.screenshot(path=shot, full_page=True)
            if log:
                log(f"   [DEBUG] 스크린샷: {shot}")
        except Exception:
            pass
        return {"ok": False, "product_id": pid, "error": "product_page_not_opened"}

    await _scroll_to_search_section(page)
    changed: list[str] = []

    if await _fill_tags(page, item.get("tags") or []):
        changed.append("tags")
    title = item.get("meta_title") or ""
    desc = item.get("meta_description") or ""
    if await _fill_by_label(page, ["Page Title", "페이지 타이틀", "page title"], title):
        changed.append("page_title")
    elif await _fill_inputs_near_text(page, "Page Title", title):
        changed.append("page_title")
    elif await _fill_inputs_near_text(page, "페이지 타이틀", title):
        changed.append("page_title")

    if await _fill_by_label(
        page,
        ["Meta description", "메타 디스크립션", "메타 설명", "meta description"],
        desc,
    ):
        changed.append("meta_description")
    elif await _fill_inputs_near_text(page, "Meta description", desc):
        changed.append("meta_description")
    elif await _fill_inputs_near_text(page, "메타", desc):
        changed.append("meta_description")

    # 저장 버튼
    saved = False
    for sel in (
        "button:has-text('저장')",
        "button:has-text('수정')",
        "button:has-text('등록')",
        ".btn_save",
    ):
        btn = page.locator(sel).first
        if await btn.count() > 0:
            try:
                await btn.click(timeout=8000)
                saved = True
                await _delay(2.0, 3.0)
                break
            except Exception:
                continue

    if not changed:
        return {"ok": False, "product_id": pid, "error": "fields_not_found", "saved": saved}

    if log:
        log(f"   [OK] {name}: {', '.join(changed)}{' · 저장됨' if saved else ' · 저장 미확인'}")
    return {"ok": True, "product_id": pid, "changed": changed, "saved": saved}


async def apply_smartstore_seo_async(
    *,
    unranked_only: bool = True,
    headless: bool = False,
    limit: int | None = None,
    logger: Logger = None,
) -> dict[str, Any]:
    seller_id, seller_pw = seller_credentials()
    if not seller_id or not seller_pw:
        return {
            "ok": False,
            "error": "missing_credentials",
            "hint": ".env에 SMARTSTORE_SELLER_ID / SMARTSTORE_SELLER_PASSWORD 설정",
        }

    items = products_to_apply(unranked_only=unranked_only)
    if limit:
        items = items[: max(1, int(limit))]
    if not items:
        return {"ok": True, "applied": [], "message": "반영할 상품 없음"}

    try:
        from playwright.async_api import async_playwright
    except ImportError:
        return {"ok": False, "error": "playwright_not_installed"}

    from playwright_bootstrap import ensure_playwright_ready_async

    if not await ensure_playwright_ready_async(logger):
        return {"ok": False, "error": "playwright_browser_missing"}

    results: list[dict[str, Any]] = []
    async with async_playwright() as p:
        profile_dir = os.path.join(os.path.dirname(__file__), "data", "smartstore_profile")
        os.makedirs(profile_dir, exist_ok=True)
        context = await p.chromium.launch_persistent_context(
            profile_dir,
            headless=headless,
            viewport={"width": 1400, "height": 900},
            locale="ko-KR",
        )
        page = context.pages[0] if context.pages else await context.new_page()

        if not await _login_naver(page, seller_id, seller_pw, logger):
            await context.close()
            return {"ok": False, "error": "login_failed", "applied": results}

        for item in items:
            try:
                results.append(await _apply_one_product(page, item, logger))
            except Exception as exc:
                results.append({"ok": False, "product_id": item.get("product_id"), "error": str(exc)})
            await _delay(1.5, 2.5)

        await context.close()

    ok_count = sum(1 for r in results if r.get("ok"))
    return {
        "ok": ok_count > 0,
        "applied": results,
        "success_count": ok_count,
        "total": len(results),
        "partial": ok_count > 0 and ok_count < len(results),
    }


def apply_smartstore_seo(
    *,
    unranked_only: bool = True,
    headless: bool = False,
    limit: int | None = None,
    logger: Logger = None,
) -> dict[str, Any]:
    return asyncio.run(
        apply_smartstore_seo_async(
            unranked_only=unranked_only,
            headless=headless,
            limit=limit,
            logger=logger,
        )
    )
