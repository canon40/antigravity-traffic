#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
전체 키워드 네이버 쇼핑 순위 일괄 조회 → CSV·TXT 리포트.

로컬 .env 의 NAVER_CLIENT_ID/SECRET 필요 (Cloudtype 미설정 시 PC에서 실행).
"""

from __future__ import annotations

import argparse
import csv
import shutil
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env", override=True)

from rank_tracker import (
    NOT_FOUND_RANK,
    _keyword_entries,
    _naver_api_credentials,
    _product_name_for,
    append_history,
    build_completion_report,
    build_rank_overview,
    check_product_rank,
    format_rank_label,
    get_last_rank,
    is_ranked,
    load_config,
    rank_depth_limit,
    rank_scan_max_pages,
    save_rank_overview,
)


def _log(msg: str) -> None:
    try:
        print(msg, flush=True)
    except UnicodeEncodeError:
        print(msg.encode("cp949", errors="replace").decode("cp949"), flush=True)


def _rank_label(rank: int | None, threshold: int = 100, status: str = "", *, scan_depth: int | None = None) -> str:
    if rank is None:
        if status == "no_product_id":
            return "상품ID 없음"
        if status in ("error", "timeout", "connection", "api_error"):
            return "조회 실패"
        return "미조회"
    return format_rank_label(rank, threshold=threshold, scan_depth=scan_depth)


def _check_with_retry(keyword: str, product_id: str, *, max_pages: int, retries: int = 3) -> tuple[int | None, str]:
    last_status = "error"
    rank: int | None = None
    for attempt in range(1, retries + 1):
        rank, status = check_product_rank(keyword, product_id, max_pages=max_pages)
        last_status = status or "ok"
        if last_status == "blocked":
            return rank, last_status
        if rank is not None or last_status == "not_found":
            return rank, last_status
        if last_status not in ("error", "timeout", "connection"):
            return rank, last_status or "error"
        if attempt < retries:
            time.sleep(1.2 * attempt)
    return rank, last_status or "api_error"


def run_full_rank_scan(*, max_pages: int | None = None, delay_sec: float = 0.8) -> list[dict]:
    cid, secret = _naver_api_credentials()
    if not cid or not secret:
        _log("[FAIL] .env 에 NAVER_CLIENT_ID / NAVER_CLIENT_SECRET 이 필요합니다.")
        return []

    config = load_config()
    if max_pages is None:
        max_pages = rank_scan_max_pages(config)
    depth = rank_depth_limit(max_pages, config)
    entries = _keyword_entries(config)
    threshold = int(config.get("traffic_rank_threshold") or 100)
    results: list[dict] = []

    _log(f"전체 {len(entries)}개 키워드 순위 조회 (최대 {depth}위까지)...")

    for i, entry in enumerate(entries, 1):
        kw = entry["keyword"]
        store = entry["store_name"]
        pid = entry.get("product_id") or ""
        prev = get_last_rank(kw, store)
        product_name = _product_name_for(config, pid)

        if pid:
            rank, status = _check_with_retry(kw, pid, max_pages=max_pages)
        else:
            rank, status = None, "no_product_id"

        if status == "blocked":
            _log(f"  [{i}/{len(entries)}] {kw} — HTTP 403 차단 (중단)")
            break

        if rank is None and status == "not_found":
            rank = NOT_FOUND_RANK
        elif rank is None and status in ("error", "timeout", "connection", "api_error"):
            rank = NOT_FOUND_RANK
            status = status or "api_error"

        row = {
            "keyword": kw,
            "product_id": pid,
            "product_name": product_name,
            "store_name": store,
            "rank": rank,
            "prev_rank": prev,
            "status": status or "ok",
            "rank_label": _rank_label(rank, threshold, status or "", scan_depth=depth),
            "in_top100": is_ranked(rank, threshold) if rank != NOT_FOUND_RANK else False,
            "scan_depth": depth,
        }
        results.append(row)

        if rank is not None and status != "blocked":
            append_history(kw, store, rank, prev, "전체순위조회", row["rank_label"])

        _log(f"  [{i}/{len(entries)}] {kw} → {row['rank_label']}")
        if i < len(entries):
            time.sleep(delay_sec)

    return results


def save_report(results: list[dict], out_dir: Path) -> dict[str, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    csv_path = out_dir / f"rank_report_{ts}.csv"
    txt_path = out_dir / f"rank_report_{ts}.txt"
    latest_csv = out_dir / "rank_report_latest.csv"
    latest_txt = out_dir / "rank_report_latest.txt"

    with csv_path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=[
                "keyword", "product_id", "product_name", "rank", "rank_label",
                "in_top100", "prev_rank", "store_name", "status",
            ],
        )
        w.writeheader()
        for r in results:
            w.writerow({k: r.get(k) for k in w.fieldnames})

    ranked = [r for r in results if r.get("in_top100")]
    unranked = [r for r in results if not r.get("in_top100")]
    overview = build_rank_overview(results)

    lines = [
        "=" * 60,
        f"나눔랩 전체 키워드 순위 리포트 — {datetime.now():%Y-%m-%d %H:%M}",
        "=" * 60,
        (
            f"조회 {overview['total']}개 · 100위 이내 {overview['ranked_top100']}개 "
            f"({overview['progress_pct']}%) · 100위 밖 {overview['outside_top100']}개 · "
            f"미노출 {overview['not_found']}개"
        ),
        "",
        f"## 진행 요약 — TOP10 {overview['ranked_top10']} · TOP50 {overview['ranked_top50']} · TOP100 {overview['ranked_top100']}",
        "",
        "## 100위 이내 (SEO 유효 · 트래픽 유지)",
        "",
    ]
    for r in sorted(ranked, key=lambda x: x.get("rank") or 9999):
        lines.append(f"  {r['rank_label']:12} | {r['keyword']} ({r.get('product_name') or r.get('product_id')})")

    lines.extend(["", "## 100위 밖 / 미노출 (트래픽·SEO 집중 대상)", ""])
    for r in unranked:
        lines.append(f"  {r['rank_label']:16} | {r['keyword']}")

    txt_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    shutil.copy2(csv_path, latest_csv)
    shutil.copy2(txt_path, latest_txt)
    save_rank_overview(results, report_paths={"csv": csv_path, "txt": txt_path})
    return {"csv": csv_path, "txt": txt_path, "latest_csv": latest_csv, "latest_txt": latest_txt}


def main() -> int:
    parser = argparse.ArgumentParser(description="전체 키워드 순위 리포트")
    parser.add_argument("--max-pages", type=int, default=25, help="키워드당 검색 페이지 (25=약 1000위)")
    parser.add_argument("--delay", type=float, default=0.8, help="키워드 간 대기(초)")
    args = parser.parse_args()

    results = run_full_rank_scan(max_pages=args.max_pages, delay_sec=args.delay)
    if not results:
        return 1

    paths = save_report(results, ROOT / "generated_content")
    report = build_completion_report(results)
    overview = build_rank_overview(results)

    _log("")
    _log("=" * 60)
    _log(report.get("summary", "완료"))
    _log(
        f"진행: 100위 이내 {overview['ranked_top100']}/{overview['total']} "
        f"({overview['progress_pct']}%) · TOP10 {overview['ranked_top10']} · TOP50 {overview['ranked_top50']}"
    )
    _log(f"CSV: {paths['csv']}")
    _log(f"TXT: {paths['txt']}")
    _log(f"최신: {paths['latest_txt']}")
    _log("=" * 60)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
