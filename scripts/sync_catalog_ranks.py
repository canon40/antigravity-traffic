#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""config.defaults.json(대시보드 69키워드) 전수 순위 조회 → rank_latest_summary·history 반영."""

from __future__ import annotations

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
    _keyword_entries,
    _naver_api_credentials,
    _product_name_for,
    append_history,
    build_completion_report,
    build_rank_overview,
    check_product_rank,
    get_last_rank,
    is_ranked,
    save_rank_overview,
)

DEFAULTS = ROOT / "config.defaults.json"


def _log(msg: str) -> None:
    try:
        print(msg, flush=True)
    except UnicodeEncodeError:
        print(msg.encode("cp949", errors="replace").decode("cp949"), flush=True)


def _rank_label(rank: int | None, threshold: int = 100, status: str = "") -> str:
    if rank is None:
        return "조회 실패" if status in ("error", "api_error") else "미조회"
    if rank >= 999:
        return "520위 밖 (미노출)"
    if is_ranked(rank, threshold):
        return f"{rank}위"
    return f"{rank}위 (100위 밖)"


def _load_defaults_config() -> dict:
    return json.loads(DEFAULTS.read_text(encoding="utf-8"))


def run_catalog_scan(*, max_pages: int = 13, delay_sec: float = 0.7) -> list[dict]:
    cid, secret = _naver_api_credentials()
    if not cid or not secret:
        _log("[FAIL] .env 에 NAVER_CLIENT_ID / NAVER_CLIENT_SECRET 필요")
        return []

    config = _load_defaults_config()
    entries = _keyword_entries(config)
    threshold = int(config.get("traffic_rank_threshold") or 100)
    results: list[dict] = []

    _log(f"대시보드 카탈로그 {len(entries)}개 키워드 순위 조회...")

    for i, entry in enumerate(entries, 1):
        kw = entry["keyword"]
        store = entry["store_name"]
        pid = entry.get("product_id") or ""
        prev = get_last_rank(kw, store)
        product_name = _product_name_for(config, pid)

        if pid:
            rank, status = check_product_rank(kw, pid, max_pages=max_pages)
        else:
            rank, status = None, "no_product_id"

        if status == "blocked":
            _log(f"  [{i}/{len(entries)}] {kw} — HTTP 403 (중단)")
            break

        if rank is None and status == "not_found":
            rank = 999
        elif rank is None and status in ("error", "timeout", "connection", "api_error"):
            rank = 999

        row = {
            "keyword": kw,
            "product_id": pid,
            "product_name": product_name,
            "store_name": store,
            "rank": rank,
            "prev_rank": prev,
            "status": status or "ok",
            "rank_label": _rank_label(rank, threshold, status or ""),
            "in_top100": is_ranked(rank, threshold),
        }
        results.append(row)

        if rank is not None and status != "blocked":
            append_history(kw, store, rank, prev, "카탈로그순위조회", row["rank_label"])

        _log(f"  [{i}/{len(entries)}] {kw} → {row['rank_label']}")
        if i < len(entries):
            time.sleep(delay_sec)

    return results


def main() -> int:
    results = run_catalog_scan()
    if not results:
        return 1

    overview = save_rank_overview(results)
    report = build_completion_report(results)

    _log("")
    _log("=" * 60)
    _log(report.get("summary", "완료"))
    _log(
        f"100위 이내 {overview['ranked_top100']}/{overview['total']} "
        f"({overview['progress_pct']}%) · TOP10 {overview['ranked_top10']}"
    )
    _log("--- 진입 키워드 ---")
    for r in sorted([x for x in results if x.get("in_top100")], key=lambda x: x.get("rank") or 9999):
        _log(f"  {r['rank_label']:12} | {r['keyword']}")
    _log("=" * 60)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
