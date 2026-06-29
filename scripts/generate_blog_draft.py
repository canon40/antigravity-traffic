#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
키워드 → 블로그 초안 + 스마트스토어 링크 (반자동 발행용).

사용:
  python scripts/generate_blog_draft.py "퍼마코트 자동차"
  python scripts/generate_blog_draft.py "퍼마코트 바이크" --product-id 12655391634
  python scripts/generate_blog_draft.py "퍼마코트 자동차" --video "D:\\@code\\ai factory\\퍼마코트_자동차_shorts.mp4"
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from seo_content_builder import generate_content, save_content, save_blog_draft_files
from store_link_builder import format_blog_copy_paste, resolve_listing


def _log(msg: str) -> None:
    try:
        print(msg, flush=True)
    except UnicodeEncodeError:
        print(msg.encode("cp949", errors="replace").decode("cp949"), flush=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="블로그 초안 + 스마트스토어 링크 생성")
    parser.add_argument("keyword", help="예: 퍼마코트 자동차, 퍼마코트 바이크")
    parser.add_argument(
        "--workflow",
        default="blog_review",
        help="blog_review | product_detail | howto | benefit (기본: blog_review)",
    )
    parser.add_argument("--product-id", help="판매자센터 상품 ID (선택)")
    parser.add_argument("--video", help="숏폼 MP4 경로 (초안 메모에 포함)")
    parser.add_argument(
        "--seo",
        action="store_true",
        help="퍼마코트 SEO 전용 Gemini 블로그 (상품 ID 필수, permacoat_blog_seo.py)",
    )
    args = parser.parse_args()

    if args.seo:
        if not args.product_id:
            _log("[FAIL] --seo 모드는 --product-id 가 필요합니다.")
            return 1
        import importlib.util

        mod_path = ROOT / "scripts" / "permacoat_blog_seo.py"
        spec = importlib.util.spec_from_file_location("permacoat_blog_seo", mod_path)
        if not spec or not spec.loader:
            _log("[FAIL] permacoat_blog_seo.py 로드 실패")
            return 1
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        mod.generate_blog_draft(args.product_id, video_path=args.video)
        return 0

    keyword = args.keyword.strip()
    if not keyword:
        _log("[FAIL] 키워드를 입력하세요.")
        return 1

    listing = resolve_listing(keyword, args.product_id)
    _log(f"키워드: {keyword}")
    _log(f"매칭 상품: {listing.get('title')} (ID {listing.get('seller_id')})")
    _log(f"스토어 URL: {listing.get('url')}")

    result = generate_content(
        args.workflow,
        keyword,
        product_name=keyword,
        product_id=listing.get("seller_id"),
    )
    if not result.get("success"):
        _log(f"[FAIL] {result.get('error')}")
        return 1

    if args.video:
        result["video_path"] = str(Path(args.video).resolve())

    paths = save_blog_draft_files(result, product_id=listing.get("seller_id"))
    paste = format_blog_copy_paste(result)

    _log("")
    _log("=" * 58)
    _log("네이버 블로그 붙여넣기용 초안")
    _log("=" * 58)
    _log(paste)
    _log("=" * 58)
    _log(f"JSON: {paths.get('json')}")
    _log(f"TXT:  {paths.get('txt')}")
    _log("")
    _log("다음 단계 (반자동):")
    _log("  1. 네이버 블로그 글쓰기 열기")
    _log("  2. MP4 영상을 에디터에 드래그")
    _log("  3. 위 TXT 파일 내용 복사 → 붙여넣기 → 발행")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
