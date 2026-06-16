# -*- coding: utf-8 -*-
"""JARVIS ↔ canon4040 Autoblog 연동 상태 점검."""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

_ROOT = Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import config as cfg

JARVIS_ROOT = Path(os.environ.get("JARVIS_ROOT", r"D:\@code\javis"))
CFG_PATH = JARVIS_ROOT / "config" / "blog_automation.json"
PORT = int(os.environ.get("CANON_AUTOBLOG_PORT", "8790"))
GUI_URL = os.environ.get("CANON_AUTOBLOG_URL", f"http://127.0.0.1:{PORT}").rstrip("/")


def _ok(msg: str) -> None:
    print(f"  [OK] {msg}")


def _fail(msg: str) -> None:
    print(f"  [XX] {msg}")


def _warn(msg: str) -> None:
    print(f"  [!!] {msg}")


def _http_get(path: str, timeout: float = 4.0) -> dict | None:
    try:
        req = urllib.request.Request(f"{GUI_URL}{path}")
        with urllib.request.urlopen(req, timeout=timeout) as res:
            return json.loads(res.read().decode("utf-8"))
    except Exception:
        return None


def check_jarvis_path() -> bool:
    print("\n=== 1. JARVIS 경로 ===")
    if JARVIS_ROOT.is_dir():
        _ok(f"JARVIS_ROOT = {JARVIS_ROOT}")
    else:
        _fail(f"JARVIS 폴더 없음: {JARVIS_ROOT}")
        return False
    bridge = JARVIS_ROOT / "integrations" / "canon_autoblog_bridge.py"
    if bridge.is_file():
        _ok("canon_autoblog_bridge.py")
    else:
        _fail("canon_autoblog_bridge.py 없음")
        return False
    return True


def check_config() -> bool:
    print("\n=== 2. blog_automation.json ===")
    if not CFG_PATH.is_file():
        _fail(str(CFG_PATH))
        return False
    data = json.loads(CFG_PATH.read_text(encoding="utf-8"))
    canon = data.get("canon_autoblog") or {}
    if not canon.get("enabled", True):
        _warn("canon_autoblog.enabled = false")
    else:
        _ok("canon_autoblog 활성화")
    proj = Path(str(canon.get("project_path", "")))
    if proj.resolve() == _ROOT.resolve():
        _ok(f"project_path → login2")
    else:
        _warn(f"project_path = {proj}")
    url = str(canon.get("gui_url", GUI_URL))
    _ok(f"gui_url = {url}")
    return True


def check_env_bridge() -> bool:
    print("\n=== 3. 환경 변수 ===")
    gemini = (cfg.GEMINI_API_KEY or cfg.GOOGLE_API_KEY or "").strip()
    if gemini:
        _ok("Gemini (login2 ← JARVIS .env 병합)")
    else:
        _fail("Gemini API 키 없음")
    javis_env = JARVIS_ROOT / ".env"
    if javis_env.is_file():
        _ok("javis/.env 존재")
    else:
        _fail("javis/.env 없음")
    if cfg.SUPABASE_URL:
        _ok(f"login2 Supabase URL 설정")
    else:
        _warn("login2 SUPABASE_URL 없음")
    # JARVIS 쪽 Supabase (프리셋 업로드용)
    javis_supa = False
    if javis_env.is_file():
        for line in javis_env.read_text(encoding="utf-8").splitlines():
            if line.startswith("SUPABASE_URL=") and line.split("=", 1)[1].strip():
                javis_supa = True
                break
    if javis_supa:
        _ok("JARVIS Supabase 설정됨 (모바일 프리셋)")
    else:
        _warn("JARVIS .env 에 SUPABASE 없음 → sync_jarvis_env.py 실행")
    return bool(gemini)


def check_gui_bridge() -> bool:
    print("\n=== 4. Autoblog HTTP 브리지 ===")
    health = _http_get("/api/javis/health")
    if health and health.get("ok"):
        _ok(f"GUI 실행 중 ({GUI_URL})")
        status = _http_get("/api/javis/status") or {}
        running = status.get("running")
        _ok(f"status: running={running}")
        return True
    _warn(f"GUI 미실행 — run_gui.bat 실행 후 JARVIS에서 트리거 가능")
    _ok(f"대기 포트: {PORT} (/api/javis/start)")
    return False


def check_jarvis_trigger() -> bool:
    print("\n=== 5. JARVIS 트리거 모듈 ===")
    if str(JARVIS_ROOT) not in sys.path:
        sys.path.insert(0, str(JARVIS_ROOT))
    try:
        from integrations.canon_autoblog_bridge import _is_gui_alive, _load_canon_cfg

        c = _load_canon_cfg()
        alive = _is_gui_alive(str(c.get("gui_url", GUI_URL)))
        if alive:
            _ok("JARVIS → Autoblog health 확인")
        else:
            _warn("JARVIS health: GUI 꺼짐 (실행 시 자동 기동·파일 트리거)")
        return True
    except Exception as e:
        _fail(f"import 실패: {e}")
        return False


def main() -> int:
    print("JARVIS ↔ canon4040 Autoblog 연동 점검")
    ok = True
    ok &= check_jarvis_path()
    ok &= check_config()
    ok &= check_env_bridge()
    gui = check_gui_bridge()
    ok &= check_jarvis_trigger()

    print("\n=== 요약 ===")
    print("  JARVIS에서 「블로그 작성」→ login2 GUI 자동화")
    print(f"  HTTP POST {GUI_URL}/api/javis/start")
    print("  GUI 없을 때: .javis/start_request.json 파일 트리거")
    if not gui:
        print("\n  다음: run_gui.bat 실행 후 JARVIS 대시보드에서 블로그 작성 테스트")
    if not ok:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
