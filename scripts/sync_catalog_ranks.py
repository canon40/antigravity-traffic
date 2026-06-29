#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""config.defaults.json(대시보드 카탈로그) 전수 순위 조회 → rank_latest_summary·history 반영."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env", override=True)

from rank_tracker import (  # noqa: E402
    NOT_FOUND_RANK,
    _keyword_entries,
    _naver_api_credentials,
    _product_name_for,
    api_scan_max_pages,
    append_history,
    auto_deep_after_api,
    build_completion_report,
    build_rank_overview,
    check_product_rank,
    deep_scan_max_pages,
    format_rank_label,
    get_last_rank,
    is_ranked,
    rank_depth_limit,
    save_rank_overview,
)

DEFAULTS = ROOT / "config.defaults.json"


def _log(msg: str) -> None:
    try:
        print(msg, flush=True)
    except UnicodeEncodeError:
        print(msg.encode("cp949", errors="replace").decode("cp949"), flush=True)


def _load_defaults_config() -> dict:
    return json.loads(DEFAULTS.read_text(encoding="utf-8"))


def run_catalog_scan(
    *,
    max_pages: int | None = None,
    delay_sec: float = 0.7,
    use_deep: bool = False,
    auto_deep: bool = False,
) -> list[dict]:
    cid, secret = _naver_api_credentials()
    if not cid or not secret:
        _log("[FAIL] .env 에 NAVER_CLIENT_ID / NAVER_CLIENT_SECRET 필요")
        return []

    config = _load_defaults_config()
    do_deep = use_deep or (auto_deep and auto_deep_after_api(config, unlimited=True))
    if max_pages is None:
        max_pages = deep_scan_max_pages(config) if do_deep else api_scan_max_pages(config)
    depth = rank_depth_limit(max_pages, api_only=not do_deep)
    entries = _keyword_entries(config)
    threshold = int(config.get("traffic_rank_threshold") or 100)
    results: list[dict] = []

    if do_deep:
        mode = "API 1000위 → 미노출 Playwright 딥스캔 (자동)"
    else:
        mode = "NAVER API"
    _log(f"대시보드 카탈로그 {len(entries)}개 · {mode} · 최대 {depth}위까지 탐색...")

    for i, entry in enumerate(entries, 1):
        kw = entry["keyword"]
        store = entry["store_name"]
        pid = entry.get("product_id") or ""
        prev = get_last_rank(kw, store)
        product_name = _product_name_for(config, pid)

        if pid:
            rank, status = check_product_rank(
                kw,
                pid,
                max_pages=max_pages,
                config=config,
                use_deep=do_deep,
            )
        else:
            rank, status = None, "no_product_id"

        if status == "blocked":
            _log(f"  [{i}/{len(entries)}] {kw} — HTTP 403 (중단)")
            break

        stored_rank = rank
        if rank is None and status == "not_found":
            stored_rank = NOT_FOUND_RANK
        elif rank is None and status in ("error", "timeout", "connection", "api_error"):
            stored_rank = NOT_FOUND_RANK
            status = status or "api_error"

        label = format_rank_label(stored_rank, threshold=threshold, scan_depth=depth)
        row = {
            "keyword": kw,
            "product_id": pid,
            "product_name": product_name,
            "store_name": store,
            "rank": stored_rank,
            "prev_rank": prev,
            "status": status or "ok",
            "rank_label": label,
            "in_top100": is_ranked(rank, threshold),
            "scan_depth": depth,
        }
        results.append(row)

        if stored_rank is not None and status != "blocked":
            append_history(kw, store, stored_rank, prev, "카탈로그순위조회", label)

        _log(f"  [{i}/{len(entries)}] {kw} → {label}")
        if i < len(entries):
            time.sleep(delay_sec)

    return results


def main() -> int:
    parser = argparse.ArgumentParser(description="대시보드 카탈로그 순위 전수 조회")
    parser.add_argument("--max-pages", type=int, default=0, help="탐색 페이지 (기본 API 25=1000위)")
    parser.add_argument("--deep", action="store_true", help="(호환) --auto-deep 와 동일")
    parser.add_argument(
        "--auto-deep",
        action="store_true",
        help="API 1000위 후 미노출 키워드 Playwright 딥스캔 (로컬 기본)",
    )
    parser.add_argument("--api-only", action="store_true", help="API 1000위만 (딥스캔 생략)")
    parser.add_argument("--delay", type=float, default=0.7)
    args = parser.parse_args()
    max_pages = args.max_pages if args.max_pages > 0 else None
    auto_deep = (args.auto_deep or args.deep) and not args.api_only
    if not args.api_only and not args.auto_deep and not args.deep:
        auto_deep = auto_deep_after_api(_load_defaults_config(), unlimited=True)

    results = run_catalog_scan(
        max_pages=max_pages,
        delay_sec=args.delay,
        use_deep=args.deep and not auto_deep,
        auto_deep=auto_deep,
    )
    if not results:
        return 1

    overview = save_rank_overview(results)
    report = build_completion_report(
        [
            {
                "keyword": r["keyword"],
                "store_name": r["store_name"],
                "product_id": r["product_id"],
                "rank": normalize_rank_export(r.get("rank")),
                "prev_rank": r.get("prev_rank"),
                "detail": r.get("rank_label"),
                "success": True,
                "not_found": is_not_found_export(r.get("rank")),
                "scan_depth": r.get("scan_depth"),
            }
            for r in results
        ]
    )

    _log("")
    _log("=" * 60)
    _log(report.get("summary", "완료"))
    _log(
        f"100위 이내 {overview['ranked_top100']}/{overview['total']} "
        f"({overview['progress_pct']}%) · 탐색깊이 {overview.get('scan_depth')}위"
    )
    _log("--- 진입 키워드 ---")
    for r in sorted([x for x in results if x.get("in_top100")], key=lambda x: normalize_rank_export(x.get("rank")) or 9999):
        _log(f"  {r['rank_label']:20} | {r['keyword']}")
    _log("=" * 60)
    return 0


def normalize_rank_export(rank):
    from rank_tracker import normalize_rank
    return normalize_rank(rank)


def is_not_found_export(rank):
    from rank_tracker import is_not_found_rank
    return is_not_found_rank(rank) or rank is None


if __name__ == "__main__":
    raise SystemExit(main())
