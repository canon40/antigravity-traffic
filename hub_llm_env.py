# -*- coding: utf-8 -*-
"""블로그 글 생성용 LLM 환경 (accounts.json → Gemini)."""

from __future__ import annotations

import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ACCOUNTS = ROOT / "accounts.json"


def apply_blog_llm_env() -> dict[str, str]:
    """accounts.json → Gemini 등 로컬 블로그 LLM 환경."""
    os.environ["BLOG_API_SPARING"] = "0"
    os.environ.setdefault("BLOG_TEXT_PROVIDER", "gemini")

    key = ""
    if ACCOUNTS.is_file():
        try:
            data = json.loads(ACCOUNTS.read_text(encoding="utf-8"))
            key = (data.get("gemini_key") or data.get("vertex_api_key") or "").strip()
        except Exception:
            pass

    if key:
        if not os.environ.get("GEMINI_API_KEY"):
            os.environ["GEMINI_API_KEY"] = key
        if not os.environ.get("GOOGLE_API_KEY"):
            os.environ["GOOGLE_API_KEY"] = key

    return {
        "api_sparing": os.environ.get("BLOG_API_SPARING", ""),
        "has_gemini_key": "yes" if (os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")) else "no",
    }
