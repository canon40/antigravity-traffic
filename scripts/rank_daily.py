# -*- coding: utf-8 -*-
"""순위 상승 일일 루틴 — 로컬 PC에서 실행 (전체 키워드 + SEO 점검)."""

from __future__ import annotations

import argparse
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from rank_tracker import build_completion_report, load_config, track_all_keywords
from seo_checker import run_full_audit


def _log(msg: str) -> None:
    try:
        print(msg, flush=True)
    except UnicodeEncodeError:
        print(msg.encode("cp949", errors="replace").decode("cp949", errors="replace"), flush=True)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="나눔랩 순위 일일 추적")
    p.add_argument("--priority-only", action="store_true", help="우선 키워드만 (웹 서버리스와 동일)")
    p.add_argument("--no-seo", action="store_true", help="SEO 점검 생략")
    args = p.parse_args(argv)

    config = load_config()
    n_kw = len(config.get("priority_keywords") or []) if args.priority_only else len(config.get("keywords") or [])
    _log(f"=== 순위 일일 추적 시작 ({n_kw}개 키워드) ===")

    results = track_all_keywords(logger=_log, serverless=args.priority_only)
    report = build_completion_report(results)
    _log(report["summary"])
    for item in report.get("items", []):
        if item.get("status") != "실패":
            _log(f"  · {item['keyword']}: {item.get('detail', '')}")

    if not args.no_seo:
        _log("--- SEO 체크리스트 ---")
        audit = run_full_audit(logger=_log)
        _log(f"평균 SEO {audit['summary'].get('average_score', 0)}점")

    _log("=== 완료 ===")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
