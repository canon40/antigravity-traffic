# -*- coding: utf-8 -*-
"""Autoblog 설정을 Supabase에 업로드 (비밀번호·API 키 제외)."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

_JARVIS_ROOT = Path(os.environ.get("JARVIS_ROOT", r"D:\@code\javis"))


def _import_jarvis_supabase():
    root = str(_JARVIS_ROOT)
    if root not in sys.path:
        sys.path.insert(0, root)
    from integrations.supabase_jarvis_mobile import (  # type: ignore
        sanitize_config,
        supabase_enabled,
        upsert_preset,
    )

    return sanitize_config, supabase_enabled, upsert_preset


def push_autoblog_preset(
    config: dict[str, Any],
    *,
    name: str = "canon4040 Autoblog",
    preset_id: str = "",
    device_label: str = "pc-blog_main",
) -> dict[str, Any]:
    """자동화 시작 시 현재 설정을 Supabase 프리셋으로 저장."""
    try:
        sanitize_config, supabase_enabled, upsert_preset = _import_jarvis_supabase()
    except Exception as e:
        return {"ok": False, "error": f"JARVIS Supabase 모듈 로드 실패: {e}"}

    if not supabase_enabled():
        return {"ok": False, "error": "SUPABASE 미설정 (javis/.env)"}

    safe = sanitize_config(config)
    return upsert_preset(
        name=name,
        program_key="canon_autoblog",
        config_json=safe,
        preset_id=preset_id or None,
        is_default=True,
        device_label=device_label,
        sort_order=100,
    )
