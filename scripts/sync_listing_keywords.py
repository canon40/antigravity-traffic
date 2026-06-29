#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""판매자센터 SEO 반영 후 — listings → config 키워드·URL 동기화."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

LISTINGS_PATH = ROOT / "data" / "smartstore_listings.json"
CONFIG_PATH = ROOT / "config.json"
DEFAULT_STORE_SLUG = "nanumlab"

BIKE_KEYWORDS = {
    "바이크 디테일링",
    "Permacoat 바이크",
    "바이크 발수",
    "배기 열 코팅",
    "머플러 크롬 코팅",
    "바이크 레진",
    "오토바이 유리막 코팅",
    "바이크 코팅제",
    "퍼마코트 바이크",
    "오토바이 코팅",
    "오토바이 전용 코팅",
    "헬멧광택",
    "바이크 초발수",
}

CAR_ONLY_KEYWORDS = {
    "퍼마코트 자동차",
    "차량용 유리막코팅",
    "자동차 디테일링",
    "셀프 유리막 코팅",
    "자동차코팅제",
    "차량코팅",
    "딥글로스",
    "시즌오프",
}


def _log(msg: str) -> None:
    try:
        print(msg, flush=True)
    except UnicodeEncodeError:
        print(msg.encode("cp949", errors="replace").decode("cp949"), flush=True)


def _listing_url(store: str, seller_id: str) -> str:
    return f"https://smartstore.naver.com/{store}/products/{seller_id}"


def _merge_keyword(
    items: list[dict],
    *,
    keyword: str,
    store_name: str,
    product_id: str,
    seen: set[tuple[str, str, str]],
) -> int:
    key = (keyword.strip(), store_name.strip(), str(product_id).strip())
    if not key[0] or key in seen:
        return 0
    seen.add(key)
    items.append({"keyword": key[0], "store_name": key[1], "product_id": key[2]})
    return 1


def main() -> int:
    if not LISTINGS_PATH.is_file():
        _log(f"[FAIL] {LISTINGS_PATH} 없음")
        return 1
    if not CONFIG_PATH.is_file():
        _log(f"[FAIL] {CONFIG_PATH} 없음")
        return 1

    listings_doc = json.loads(LISTINGS_PATH.read_text(encoding="utf-8"))
    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    store = (listings_doc.get("store_name") or config.get("store_name") or "나눔랩").strip()
    store_slug = (config.get("store_slug") or DEFAULT_STORE_SLUG).strip()

    added_kw = 0
    fixed_kw = 0
    seen: set[tuple[str, str, str]] = set()

    for item in config.get("keywords") or []:
        if not isinstance(item, dict):
            continue
        kw = (item.get("keyword") or "").strip()
        sn = (item.get("store_name") or store).strip()
        pid = str(item.get("product_id") or "").strip()
        seen.add((kw, sn, pid))

    bike_pid = "12639296730"
    for item in config.get("keywords") or []:
        if not isinstance(item, dict):
            continue
        kw = (item.get("keyword") or "").strip()
        if kw in CAR_ONLY_KEYWORDS and str(item.get("product_id")) == "10713170202":
            item["product_id"] = bike_pid
            fixed_kw += 1
        if kw in BIKE_KEYWORDS and str(item.get("product_id")) == "10713170202":
            item["product_id"] = bike_pid
            fixed_kw += 1

    priority: list[dict] = []
    seen_priority: set[tuple[str, str, str]] = set()
    listing_urls: list[dict] = []

    for row in listings_doc.get("listings") or []:
        if not isinstance(row, dict):
            continue
        seller_id = str(row.get("seller_id") or "").strip()
        storefront_id = str(row.get("storefront_id") or seller_id).strip()
        title = (row.get("title") or "").strip()
        category = (row.get("category") or "").strip()
        if seller_id:
            listing_urls.append(
                {
                    "seller_id": seller_id,
                    "category": category,
                    "title": title,
                    "url": _listing_url(store_slug, seller_id),
                    "storefront_id": storefront_id,
                }
            )
        for kw in row.get("keywords") or []:
            added_kw += _merge_keyword(
                priority,
                keyword=str(kw),
                store_name=store,
                product_id=storefront_id,
                seen=seen_priority,
            )

    existing_priority = config.get("priority_keywords") or []
    for item in existing_priority:
        if isinstance(item, dict):
            _merge_keyword(
                priority,
                keyword=str(item.get("keyword") or ""),
                store_name=str(item.get("store_name") or store),
                product_id=str(item.get("product_id") or ""),
                seen=seen_priority,
            )

    config["priority_keywords"] = priority
    config["product_listings"] = listing_urls
    config["store_slug"] = store_slug
    config["traffic_rank_threshold"] = int(config.get("traffic_rank_threshold") or 100)
    config["priority_track_limit"] = max(int(config.get("priority_track_limit") or 10), len(priority))
    config["seo_synced_at"] = __import__("datetime").datetime.now().strftime("%Y-%m-%d %H:%M")

    CONFIG_PATH.write_text(json.dumps(config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    _log(f"[OK] priority_keywords: {len(priority)}개 (신규 {added_kw})")
    _log(f"[OK] 바이크 키워드 product_id 수정: {fixed_kw}건")
    _log(f"[OK] product_listings URL: {len(listing_urls)}개")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
