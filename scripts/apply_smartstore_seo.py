#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""미진입 키워드 상품의 SEO를 스마트스토어 판매자센터에 반영."""

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import config  # noqa: F401 — .env 로드

from smartstore_seller import apply_smartstore_seo, seller_credentials


def _log(msg: str) -> None:
    try:
        print(msg, flush=True)
    except UnicodeEncodeError:
        print(msg.encode("cp949", errors="replace").decode("cp949"), flush=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="스마트스토어 판매자센터 SEO 자동 반영")
    parser.add_argument("--all", action="store_true", help="전체 상품 (기본: 미진입 키워드 상품만)")
    parser.add_argument("--limit", type=int, default=0, help="처리 상품 수 제한 (테스트용)")
    parser.add_argument("--headless", action="store_true", help="헤드리스 (캡차 시 실패 가능)")
    args = parser.parse_args()

    sid, _ = seller_credentials()
    if not sid:
        _log("[FAIL] SMARTSTORE_SELLER_ID / SMARTSTORE_SELLER_PASSWORD 가 .env에 없습니다.")
        return 1

    _log(f"[START] 판매자센터 SEO 반영 (계정: {sid})")
    result = apply_smartstore_seo(
        unranked_only=not args.all,
        headless=args.headless,
        limit=args.limit or None,
        logger=_log,
    )

    if not result.get("ok"):
        _log(f"[FAIL] {result.get('error') or result.get('hint') or 'unknown'}")
        for row in result.get("applied") or []:
            _log(f"   · {row.get('product_id')}: {row.get('error') or row.get('changed')}")
        return 1

    _log(f"[DONE] {result.get('success_count', 0)}/{result.get('total', 0)}건")
    for row in result.get("applied") or []:
        if row.get("ok"):
            _log(f"   · {row.get('product_id')}: {', '.join(row.get('changed') or [])}")
        else:
            _log(f"   · {row.get('product_id')}: 실패 — {row.get('error')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
