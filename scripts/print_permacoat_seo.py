#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""퍼마코트 자동차·바이크 판매자센터 SEO 가이드 출력."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LISTINGS = ROOT / "data" / "smartstore_listings.json"


def _log(msg: str) -> None:
    try:
        print(msg, flush=True)
    except UnicodeEncodeError:
        print(msg.encode("cp949", errors="replace").decode("cp949"), flush=True)


def main() -> int:
    doc = json.loads(LISTINGS.read_text(encoding="utf-8"))
    lines = doc.get("product_lines") or {}
    car_info = lines.get("car") or {}
    bike_info = lines.get("bike") or {}

    _log("=" * 60)
    _log("퍼마코트 SEO 가이드 — 자동차 vs 바이크")
    _log("=" * 60)
    _log(f"자동차: {car_info.get('display_name')} = {car_info.get('category_ko')}")
    _log(f"바이크: {bike_info.get('display_name')} = {bike_info.get('category_ko')}")
    _log("")

    for cat, label in (("car", "🚗 자동차"), ("bike", "🏍️ 바이크")):
        _log(f"\n{'=' * 60}\n{label} 상품\n{'=' * 60}")
        for row in doc.get("listings") or []:
            if row.get("category") != cat:
                continue
            sid = row.get("seller_id")
            seo = row.get("seo") or {}
            url = f"https://sell.smartstore.naver.com/#/products/edit/{sid}"
            _log(f"\n[{sid}] {row.get('title')}")
            _log(f"  URL: {url}")
            _log(f"  상품명 유지 — 검색설정만 아래 입력")
            _log(f"  Page Title: {seo.get('page_title', '-')}")
            _log(f"  Meta: {seo.get('meta_description', '-')}")
            tags = seo.get("tags") or []
            _log(f"  태그: {', '.join(tags)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
