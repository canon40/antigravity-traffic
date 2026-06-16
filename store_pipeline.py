# -*- coding: utf-8 -*-
"""스마트스토어 마케팅 파이프라인: 크롤 → DB → RAG 에이전트."""

from __future__ import annotations

import asyncio
from typing import Any, Callable

from store_keyword_crawler import crawl_and_save_keywords
from store_marketing_agent import generate_store_assets


async def run_store_pipeline(
    product_concept: str,
    category: str,
    *,
    seed_keywords: list[str] | None = None,
    crawl: bool = True,
    use_playwright: bool = True,
    api_key: str | None = None,
    log_fn: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    """전체 파이프라인 실행."""
    keywords_data: list[dict[str, Any]] | None = None

    if crawl:
        crawl_res = await crawl_and_save_keywords(
            category,
            seed_keywords=seed_keywords,
            use_playwright=use_playwright,
            log_fn=log_fn,
        )
        if not crawl_res.get("ok"):
            return {"ok": False, "error": crawl_res.get("error") or "키워드 수집 실패", "stage": "crawl"}
        keywords_data = crawl_res.get("keywords") or []

    gen_res = await generate_store_assets(
        product_concept,
        category,
        api_key=api_key,
        keywords_override=keywords_data,
        log_fn=log_fn,
    )
    if not gen_res.get("ok"):
        return {**gen_res, "stage": "generate"}

    return {
        "ok": True,
        "report": gen_res.get("text", ""),
        "tags_for_blog": gen_res.get("tags_for_blog", ""),
        "keywords_used": gen_res.get("keywords_used") or [],
    }


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="스마트스토어 마케팅 파이프라인")
    parser.add_argument("--category", default="자동차용품")
    parser.add_argument(
        "--concept",
        default="자가시공 가능한 고순도 폴리시라잔 성분 프리미엄 유리막 코팅제",
    )
    parser.add_argument("--seeds", default="", help="쉼표 구분 시드 키워드")
    parser.add_argument("--no-crawl", action="store_true")
    parser.add_argument("--no-playwright", action="store_true")
    args = parser.parse_args()

    seeds = [s.strip() for s in args.seeds.split(",") if s.strip()]

    def _log(m: str) -> None:
        print(m)

    result = asyncio.run(
        run_store_pipeline(
            args.concept,
            args.category,
            seed_keywords=seeds or None,
            crawl=not args.no_crawl,
            use_playwright=not args.no_playwright,
            log_fn=_log,
        )
    )

    if not result.get("ok"):
        print("오류:", result.get("error"))
        raise SystemExit(1)

    print("\n" + "=" * 50)
    print("★ 스마트스토어 마케팅 리포트 ★")
    print("=" * 50)
    print(result.get("report", ""))
    if result.get("tags_for_blog"):
        print("\n[블로그 키워드용]", result["tags_for_blog"])


if __name__ == "__main__":
    main()
