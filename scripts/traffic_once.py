# -*- coding: utf-8 -*-
"""상품 URL로 트래픽 1회 실행 (GUI 없이)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from vercel_traffic_client import load_vercel_config, trigger_traffic


def main() -> int:
    p = argparse.ArgumentParser(description="Autoblog 트래픽 1회 (로컬/Vercel)")
    p.add_argument("--url", help="방문 URL (미지정 시 accounts.json product_url)")
    p.add_argument("--mode", choices=("local", "cloud", "both"), help="실행 모드")
    p.add_argument("--accounts", default=str(ROOT / "accounts.json"), help="설정 파일")
    args = p.parse_args()

    cfg = load_vercel_config(args.accounts)
    if args.mode:
        cfg["vercel_mode"] = args.mode

    def log(msg: str) -> None:
        print(msg)

    outcome = trigger_traffic(args.url, config=cfg, log=log)
    print(json.dumps(outcome, ensure_ascii=False, indent=2))
    return 0 if outcome.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
