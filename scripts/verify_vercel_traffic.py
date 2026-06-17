# -*- coding: utf-8 -*-
"""Cloudtype/Vercel 트래픽 모듈 검증 — traffic_session만 점검."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VT = ROOT / "vercel_traffic"
if str(VT) not in sys.path:
    sys.path.insert(0, str(VT))


def main() -> int:
    results = []
    try:
        from traffic_session import run_traffic_session

        r = run_traffic_session("https://smartstore.naver.com", timeout_sec=8.0)
        ok = bool(r.get("ok"))
        detail = f"code={r.get('status_code')} elapsed={r.get('elapsed_sec')}s"
        results.append(("traffic_session", ok, detail))
    except Exception as exc:
        results.append(("traffic_session", False, str(exc)))

    print("=== Traffic Session Verification ===")
    failed = 0
    for name, ok, detail in results:
        mark = "PASS" if ok else "FAIL"
        print(f"[{mark}] {name} - {detail}")
        if not ok:
            failed += 1
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
