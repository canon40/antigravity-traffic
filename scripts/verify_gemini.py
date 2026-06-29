#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Gemini API 키 연동 확인 (.env + accounts.json)."""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env", override=True)

from hub_llm_env import apply_blog_llm_env

apply_blog_llm_env()


async def main() -> int:
    from blog_content_gen import verify_gemini_api_key

    key = (os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY") or "").strip()
    if not key:
        print("[FAIL] GEMINI_API_KEY 없음 — .env 또는 accounts.json gemini_key 확인")
        return 1
    suffix = key[-4:] if len(key) >= 4 else "?"
    print(f"[INFO] 키 길이={len(key)} · 끝={suffix}")
    ok, msg = await verify_gemini_api_key(key)
    if ok:
        safe = msg.encode("cp949", errors="replace").decode("cp949")
        print(f"[OK] {safe}")
        return 0
    safe = msg.encode("cp949", errors="replace").decode("cp949")
    print(f"[FAIL] {safe}")
    return 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
