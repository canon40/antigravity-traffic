# -*- coding: utf-8 -*-
"""네이버 쇼핑·검색 키워드 수집 (Playwright + 시드 키워드 폴백)."""

from __future__ import annotations

import asyncio
import re
from typing import Any

from store_supabase import upsert_keywords

# 카테고리별 기본 시드 (크롤 실패·차단 시 폴백)
_CATEGORY_SEEDS: dict[str, list[dict[str, Any]]] = {
    "자동차용품": [
        {"keyword": "자동차 유리막 코팅제", "monthly_search_volume": 12500, "competition_index": 1.2},
        {"keyword": "차량용 세라믹 코팅", "monthly_search_volume": 8400, "competition_index": 0.9},
        {"keyword": "폴리시라잔 코팅제", "monthly_search_volume": 4200, "competition_index": 0.5},
        {"keyword": "자가시공 코팅제", "monthly_search_volume": 6100, "competition_index": 1.1},
    ],
    "리빙": [
        {"keyword": "욕실 코팅제", "monthly_search_volume": 9800, "competition_index": 1.0},
        {"keyword": "싱크대 코팅", "monthly_search_volume": 7200, "competition_index": 0.8},
        {"keyword": "리빙코트", "monthly_search_volume": 5400, "competition_index": 0.6},
        {"keyword": "곰팡이 방지 코팅", "monthly_search_volume": 3900, "competition_index": 0.7},
    ],
    "바이크용품": [
        {"keyword": "바이크 유리막 코팅", "monthly_search_volume": 3100, "competition_index": 0.5},
        {"keyword": "오토바이 코팅제", "monthly_search_volume": 2800, "competition_index": 0.6},
    ],
}


def _parse_related_keywords(text: str, *, base_volume: int = 3000) -> list[dict[str, Any]]:
    """연관 검색어 텍스트에서 키워드 후보 추출."""
    parts = re.split(r"[,|\n]+", text or "")
    out: list[dict[str, Any]] = []
    for i, p in enumerate(parts):
        kw = re.sub(r"\s+", " ", p).strip()
        if len(kw) < 2 or len(kw) > 40:
            continue
        vol = max(500, base_volume - i * 200)
        out.append({
            "keyword": kw,
            "monthly_search_volume": vol,
            "competition_index": round(0.4 + (i * 0.1), 2),
        })
        if len(out) >= 8:
            break
    return out


async def _crawl_naver_related(category: str, seed: str) -> list[dict[str, Any]]:
    """네이버 검색 연관 키워드 영역 스크래핑 시도."""
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        return []

    query = seed or category
    url = "https://search.naver.com/search.naver?where=nexearch&query=" + query

    async with async_playwright() as p:
        iphone = p.devices.get("iPhone 14 Pro Max", {})
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(**iphone) if iphone else await browser.new_context()
        page = await context.new_page()
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=25000)
            await asyncio.sleep(1.5)

            related_text = ""
            for sel in (
                ".related_srch a",
                "#nx_related_keywords a",
                "a[href*='query=']",
            ):
                loc = page.locator(sel)
                if await loc.count() > 0:
                    texts = await loc.all_text_contents()
                    related_text = ", ".join(t.strip() for t in texts if t.strip())
                    if related_text:
                        break

            if not related_text:
                return []

            return _parse_related_keywords(related_text)
        except Exception:
            return []
        finally:
            await browser.close()


async def crawl_and_save_keywords(
    category: str,
    *,
    seed_keywords: list[str] | None = None,
    use_playwright: bool = True,
    log_fn=None,
) -> dict[str, Any]:
    """
    카테고리 키워드를 수집해 Supabase/로컬에 저장.
    Playwright 실패 시 시드·카테고리 기본값으로 폴백.
    """
    cat = (category or "").strip()
    if not cat:
        return {"ok": False, "error": "카테고리가 비어 있습니다."}

    def _log(msg: str) -> None:
        if log_fn:
            try:
                log_fn(msg)
            except Exception:
                pass

    collected: list[dict[str, Any]] = []
    seeds = [s.strip() for s in (seed_keywords or []) if s.strip()]
    if not seeds:
        seeds = [cat]

    if use_playwright:
        _log(f"[크롤러] 네이버 연관 키워드 수집 시도: {seeds[0]}")
        crawled = await _crawl_naver_related(cat, seeds[0])
        for row in crawled:
            collected.append({"category": cat, **row})

    if not collected:
        _log("[크롤러] 웹 수집 결과 없음 — 시드/기본 키워드 사용")
        base = _CATEGORY_SEEDS.get(cat, _CATEGORY_SEEDS.get("자동차용품", []))
        for row in base:
            collected.append({"category": cat, **row})
        for seed in seeds[:3]:
            if not any(r.get("keyword") == seed for r in collected):
                collected.append({
                    "category": cat,
                    "keyword": seed,
                    "monthly_search_volume": 2500,
                    "competition_index": 0.8,
                })

    # 중복 제거
    seen: set[str] = set()
    unique: list[dict[str, Any]] = []
    for row in collected:
        kw = row.get("keyword", "")
        if kw in seen:
            continue
        seen.add(kw)
        unique.append(row)

    save_res = upsert_keywords(unique)
    return {
        "ok": save_res.get("ok", False),
        "count": len(unique),
        "keywords": unique,
        "save": save_res,
        "error": save_res.get("error"),
    }
