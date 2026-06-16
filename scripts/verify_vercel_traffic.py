# -*- coding: utf-8 -*-
"""Vercel 트래픽 연동 검증 스크립트 — 로컬·설정·모듈 import 점검."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _check(name: str, ok: bool, detail: str = "") -> dict:
    return {"name": name, "ok": ok, "detail": detail}


def main() -> int:
    results: list[dict] = []

    # 1) 모듈 import
    try:
        from vercel_traffic_client import (
            health_check,
            load_vercel_config,
            normalize_health_url,
            normalize_traffic_url,
            trigger_traffic,
            VercelTrafficScheduler,
        )

        results.append(_check("import_vercel_traffic_client", True))
    except Exception as exc:
        results.append(_check("import_vercel_traffic_client", False, str(exc)))
        _print_report(results)
        return 1

    # 2) URL 정규화
    cases = [
        ("https://x.vercel.app", "https://x.vercel.app/api/traffic"),
        ("https://x.vercel.app/api", "https://x.vercel.app/api/traffic"),
        ("https://x.vercel.app/api/traffic", "https://x.vercel.app/api/traffic"),
    ]
    url_ok = all(normalize_traffic_url(a) == b for a, b in cases)
    results.append(_check("normalize_traffic_url", url_ok, str(cases)))

    health_cases = [
        ("https://x.vercel.app/api/traffic", "https://x.vercel.app/api/health"),
    ]
    h_ok = all(normalize_health_url(a) == b for a, b in health_cases)
    results.append(_check("normalize_health_url", h_ok, str(health_cases)))

    # 3) accounts.json 로드
    cfg = load_vercel_config(ROOT / "accounts.json")
    results.append(
        _check(
            "load_vercel_config",
            isinstance(cfg, dict) and "vercel_mode" in cfg,
            json.dumps({k: cfg.get(k) for k in ("vercel_enabled", "vercel_mode", "vercel_api_url")}, ensure_ascii=False),
        )
    )

    # 4) 로컬 HTTP 방문 (네트워크)
    try:
        outcome = trigger_traffic(
            "https://smartstore.naver.com",
            config={**cfg, "vercel_mode": "local", "vercel_enabled": True},
        )
        local = (outcome.get("results") or {}).get("local") or {}
        elapsed = (local.get("result") or {}).get("elapsed_sec")
        results.append(
            _check(
                "local_traffic_visit",
                bool(outcome.get("ok")),
                f"elapsed_sec={elapsed}, status={(local.get('result') or {}).get('status_code')}",
            )
        )
    except Exception as exc:
        results.append(_check("local_traffic_visit", False, str(exc)))

    # 5) vercel_traffic 서버리스 모듈
    vt = ROOT / "vercel_traffic"
    try:
        sys.path.insert(0, str(vt))
        from traffic_session import run_traffic_session

        r = run_traffic_session("https://smartstore.naver.com", timeout_sec=8.0)
        results.append(
            _check(
                "traffic_session_module",
                bool(r.get("ok")),
                f"elapsed={r.get('elapsed_sec')}s code={r.get('status_code')}",
            )
        )
    except Exception as exc:
        results.append(_check("traffic_session_module", False, str(exc)))

    # 6) 클라우드 헬스 (URL 있을 때만)
    api_url = (cfg.get("vercel_api_url") or "").strip()
    mode = (cfg.get("vercel_mode") or "local").lower()
    if api_url and mode in ("cloud", "both"):
        try:
            hc = health_check({**cfg, "vercel_api_url": api_url})
            results.append(
                _check(
                    "cloud_health_check",
                    bool(hc.get("ok")),
                    f"status={hc.get('status_code')} url={hc.get('url')}",
                )
            )
        except Exception as exc:
            results.append(_check("cloud_health_check", False, str(exc)))
    else:
        try:
            hc = health_check({**cfg, "vercel_mode": "local"})
            results.append(
                _check(
                    "health_check_local",
                    bool(hc.get("ok")),
                    hc.get("body", {}).get("message", ""),
                )
            )
        except Exception as exc:
            results.append(_check("health_check_local", False, str(exc)))

    # 7) GUI/mobile 연동 파일 존재
    for rel in (
        "blog_gui_tabs.py",
        "blog_main.py",
        "blog_daily_weekday.py",
        "mobile_server.py",
        "vercel_traffic/api/index.py",
    ):
        p = ROOT / rel
        results.append(_check(f"file_exists:{rel}", p.is_file(), str(p)))

    _print_report(results)
    failed = [r for r in results if not r["ok"]]
    return 1 if failed else 0


def _print_report(results: list[dict]) -> None:
    print("=== Vercel Traffic Verification ===")
    for r in results:
        mark = "PASS" if r["ok"] else "FAIL"
        line = f"[{mark}] {r['name']}"
        if r.get("detail"):
            line += f" - {r['detail']}"
        try:
            print(line)
        except UnicodeEncodeError:
            print(line.encode("ascii", errors="replace").decode("ascii"))
    passed = sum(1 for r in results if r["ok"])
    print(f"--- {passed}/{len(results)} passed ---")


if __name__ == "__main__":
    raise SystemExit(main())
