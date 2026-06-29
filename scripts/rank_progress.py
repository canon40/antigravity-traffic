#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""순위 진입 현황 — 몇 위까지 작업됐는지 한눈에 출력."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env", override=True)

from rank_tracker import build_rank_overview, get_keyword_rank_summary, load_config, load_rank_overview


def _log(msg: str) -> None:
    try:
        print(msg, flush=True)
    except UnicodeEncodeError:
        print(msg.encode("cp949", errors="replace").decode("cp949"), flush=True)


def main() -> int:
    overview = load_rank_overview()
    config = load_config()
    summary = get_keyword_rank_summary(config)
    ranked = [s for s in summary if s.get("bucket") == "ranked"]
    unranked = [s for s in summary if s.get("bucket") != "ranked"]
    total = len(summary)

    _log("=" * 58)
    _log("  나눔랩 키워드 순위 진행 현황")
    _log("=" * 58)

    if overview:
        stale = " (오래됨 — run_rank_report.bat 재실행 권장)" if overview.get("_stale") else ""
        _log(f"\n[전체 스캔] {overview.get('scanned_at', '?')}{stale}")
        _log(
            f"  100위 이내: {overview.get('ranked_top100', 0)}/{overview.get('total', total)} "
            f"({overview.get('progress_pct', 0)}%)"
        )
        _log(
            f"  TOP10 {overview.get('ranked_top10', 0)} · "
            f"TOP50 {overview.get('ranked_top50', 0)} · "
            f"100위 밖 {overview.get('outside_top100', 0)} · "
            f"미노출 {overview.get('not_found', 0)}"
        )
        txt = overview.get("report_txt") or str(ROOT / "generated_content" / "rank_report_latest.txt")
        _log(f"  상세 리포트: {txt}")
    else:
        _log("\n[전체 스캔] 아직 없음 → run_rank_report.bat 실행 (약 15분)")

    _log(f"\n[현재 기준] 순위 진입 {len(ranked)}개 / 미진입 {len(unranked)}개 / 전체 {total}개")

    if ranked:
        _log("\n--- 100위 이내 ---")
        for item in sorted(ranked, key=lambda x: x.get("last_rank") or 9999):
            _log(f"  {item.get('last_rank'):>3}위 | {item['keyword']} ({item.get('product_name') or ''})")

    if unranked:
        _log("\n--- 미진입 (다음 작업 대상) ---")
        for item in unranked[:25]:
            label = item.get("status_label") or "미진입"
            _log(f"  {label:14} | {item['keyword']}")
        if len(unranked) > 25:
            _log(f"  ... 외 {len(unranked) - 25}개")

    _log("\n[순위 올리기 작업]")
    _log("  1) run_rank_boost.bat     — SEO동기화 + 순위추적 + 트래픽 12회")
    _log("  2) run_smartstore_seo.bat — 판매자센터 메타·태그 반영")
    _log("  3) run_permacoat_blog.bat   — Gemini SEO 블로그")
    _log("=" * 58)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
