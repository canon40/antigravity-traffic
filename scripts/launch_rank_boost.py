#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""SEO 반영 후 순위 추적 + 미진입 키워드 트래픽 부스트 (로컬)."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import config  # noqa: F401 — .env

from rank_tracker import (
    build_completion_report,
    get_keyword_rank_summary,
    load_config,
    split_keywords_by_rank,
    track_all_keywords,
)
from rank_persistence import load_hub_state, save_hub_state

try:
    from vercel_traffic.traffic_session import run_traffic_session
    from vercel_traffic.traffic_targets import pick_traffic_url
except ImportError:
    sys.path.insert(0, str(ROOT / "vercel_traffic"))
    from traffic_session import run_traffic_session
    from traffic_targets import pick_traffic_url


def _log(msg: str) -> None:
    try:
        print(msg, flush=True)
    except UnicodeEncodeError:
        print(msg.encode("cp949", errors="replace").decode("cp949"), flush=True)


def _run_traffic_burst(count: int, interval_sec: float) -> None:
    state = load_hub_state()
    state["traffic_enabled"] = True
    state["auto_enabled"] = True
    save_hub_state(state)

    cfg = load_config()
    unranked, ranked = split_keywords_by_rank(cfg)
    _log(f"[트래픽] 미진입 {len(unranked)} / 유지 {len(ranked)}")

    for i in range(count):
        url, state = pick_traffic_url(cfg, state, advance=True)
        referer = state.get("traffic_referer_url") or "https://m.naver.com/"
        mode = state.get("last_traffic_mode") or "boost"
        kw = state.get("last_traffic_keyword") or ""
        _log(f"  [{i + 1}/{count}] {mode} | {kw or '-'} | {url[:70]}...")
        try:
            outcome = run_traffic_session(url, referer_url=referer)
            ok = outcome.get("ok")
            _log(f"    → HTTP {outcome.get('status_code')} ({'OK' if ok else 'FAIL'})")
        except Exception as exc:
            _log(f"  [WARN] 트래픽 실패: {exc}")
        save_hub_state(state)
        if i + 1 < count:
            time.sleep(interval_sec)


def main() -> int:
    parser = argparse.ArgumentParser(description="순위 부스트 런치")
    parser.add_argument("--traffic", type=int, default=12, help="트래픽 방문 횟수")
    parser.add_argument("--traffic-interval", type=float, default=25.0, help="방문 간격(초)")
    parser.add_argument("--no-rank", action="store_true", help="순위 추적 생략")
    parser.add_argument("--no-traffic", action="store_true", help="트래픽 생략")
    args = parser.parse_args()

    sync_script = ROOT / "scripts" / "sync_listing_keywords.py"
    if sync_script.is_file():
        _log("=== 1) listings → config 동기화 ===")
        import subprocess

        rc = subprocess.call([sys.executable, str(sync_script)])
        if rc != 0:
            return rc

    if not args.no_rank:
        _log("=== 2) 우선 키워드 순위 추적 ===")
        results = track_all_keywords(logger=_log, serverless=True)
        report = build_completion_report(results)
        _log(report.get("summary") or "")

        summary = get_keyword_rank_summary(load_config())
        unranked = [s for s in summary if s.get("bucket") == "unranked"]
        ranked = [s for s in summary if s.get("bucket") == "ranked"]
        _log(f"--- 현황: 미진입 {len(unranked)} / 순위유지 {len(ranked)} ---")
        for item in unranked[:15]:
            _log(
                f"  · {item.get('keyword')} ({item.get('product_name')}) "
                f"→ {item.get('status_label')}"
            )
        if len(unranked) > 15:
            _log(f"  ... 외 {len(unranked) - 15}개")

    if not args.no_traffic and args.traffic > 0:
        _log(f"=== 3) 미진입 우선 트래픽 {args.traffic}회 ===")
        _run_traffic_burst(args.traffic, args.traffic_interval)

    _log("=== 완료 ===")
    _log("24시간 자동: run.bat 으로 허브 실행 (순위·트래픽 백그라운드)")
    _log("Cloudtype: main 브랜치 push 후 대시보드 /api/status 확인")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
