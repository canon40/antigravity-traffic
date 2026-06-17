# -*- coding: utf-8
"""로그인 필요·봇 감지 시 사용자 알림 (Windows·웹훅·알림 파일)."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parent.parent
_ALERT = Path.home() / ".jarvis" / "ALERT_LOGIN_REQUIRED.json"


def _notify_cfg() -> dict[str, Any]:
    try:
        cfg = json.loads((_ROOT / "config" / "blog_automation.json").read_text(encoding="utf-8"))
        return cfg.get("notify") or {}
    except Exception:
        return {}


def _windows_popup(title: str, message: str) -> bool:
    if sys.platform != "win32":
        return False
    try:
        safe = message.replace("'", "''").replace('"', '`"')[:900]
        t = title.replace("'", "''")[:80]
        ps = (
            f"[System.Reflection.Assembly]::LoadWithPartialName('System.Windows.Forms') | Out-Null; "
            f"[System.Windows.Forms.MessageBox]::Show('{safe}','{t}',"
            f"'OK','Warning')"
        )
        subprocess.Popen(
            ["powershell", "-NoProfile", "-Command", ps],
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        return True
    except Exception:
        return False


def _webhook_post(payload: dict[str, Any]) -> bool:
    url = (
        (_notify_cfg().get("webhook_url") or "")
        or (os.environ.get("JARVIS_NOTIFY_WEBHOOK") or "")
        or (os.environ.get("JARVIS_N8N_NOTIFY_URL") or "")
    ).strip()
    if not url:
        return False
    try:
        import requests

        r = requests.post(url, json=payload, timeout=15)
        return r.status_code < 400
    except Exception:
        return False


def alert_login_required(
    platform: str,
    *,
    reason: str = "bot_or_captcha",
    detail: str = "",
    wait_manual: bool = True,
    on_status: Any = None,
) -> dict[str, Any]:
    """
    카톡/n8n 웹훅·Windows 팝업·알림 파일.
    n8n에서 카카오 알림톡 연동 시 webhook_url 설정.
    """
    emit = on_status or print
    msg = (
        f"[JARVIS] {platform} 로그인 필요\n"
        f"사유: {reason}\n"
        f"{detail}\n\n"
        "브라우저에서 직접 로그인해 주세요."
    )
    payload = {
        "event": "blog_login_required",
        "platform": platform,
        "reason": reason,
        "detail": detail,
        "message": msg,
        "timestamp": time.time(),
        "alert_file": str(_ALERT),
    }
    _ALERT.parent.mkdir(parents=True, exist_ok=True)
    _ALERT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    emit("\n" + "!" * 50)
    emit(msg)
    emit(f"알림 파일: {_ALERT}")
    emit("!" * 50 + "\n")

    _windows_popup(f"JARVIS — {platform} 로그인", msg[:800])
    wh_ok = _webhook_post(payload)
    if wh_ok:
        emit("[알림] webhook 전송 OK (n8n→카톡 등 연동 가능)")

    return {"ok": True, "alert_file": str(_ALERT), "webhook_sent": wh_ok, "waiting_manual": wait_manual}
