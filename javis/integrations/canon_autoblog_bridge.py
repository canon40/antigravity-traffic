# -*- coding: utf-8 -*-
"""JARVIS → canon4040 Autoblog (login2/blog_main.py) 트리거."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable
from urllib import error, request

_ROOT = Path(__file__).resolve().parent.parent
_DEFAULT_PROJECT = Path(r"D:\@code\antigravity\blogauto\login2")
_CFG = _ROOT / "config" / "blog_automation.json"


def _load_canon_cfg() -> dict[str, Any]:
    base = {"enabled": True, "gui_url": "http://127.0.0.1:8790", "project_path": str(_DEFAULT_PROJECT)}
    if _CFG.is_file():
        try:
            data = json.loads(_CFG.read_text(encoding="utf-8"))
            canon = data.get("canon_autoblog") or {}
            if isinstance(canon, dict):
                base.update(canon)
        except Exception:
            pass
    env_path = os.environ.get("CANON_AUTOBLOG_PATH", "").strip()
    if env_path:
        base["project_path"] = env_path
    env_url = os.environ.get("CANON_AUTOBLOG_URL", "").strip()
    if env_url:
        base["gui_url"] = env_url
    return base


def _http_json(url: str, payload: dict | None = None, *, timeout: float = 8.0) -> dict[str, Any]:
    data = None
    headers = {"Content-Type": "application/json; charset=utf-8"}
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = request.Request(url, data=data, headers=headers, method="POST" if payload is not None else "GET")
    with request.urlopen(req, timeout=timeout) as res:
        return json.loads(res.read().decode("utf-8"))


def _is_gui_alive(gui_url: str) -> bool:
    try:
        r = _http_json(f"{gui_url.rstrip('/')}/api/javis/health", timeout=3.0)
        return bool(r.get("ok"))
    except Exception:
        return False


def _write_file_trigger_fallback(project: Path, payload: dict[str, Any]) -> dict[str, Any]:
    try:
        sys.path.insert(0, str(project))
        from javis_bridge import write_file_trigger  # type: ignore

        path = write_file_trigger(payload)
        return {
            "ok": True,
            "message": f"트리거 파일 저장: {path}. GUI가 뜨면 자동으로 자동화가 시작됩니다.",
            "backend": "canon_autoblog_file",
        }
    except Exception:
        trigger_dir = project / ".javis"
        trigger_dir.mkdir(parents=True, exist_ok=True)
        fpath = trigger_dir / "start_request.json"
        fpath.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return {
            "ok": True,
            "message": f"트리거 파일 저장: {fpath}. canon4040 오토 블로그 창이 뜨면 자동 시작됩니다.",
            "backend": "canon_autoblog_file",
        }


def _launch_gui(project_path: Path, on_status: Callable[[str], None] | None = None) -> bool:
    emit = on_status or (lambda _m: None)
    venv_py = project_path / ".venv" / "Scripts" / "python.exe"
    env_py = (os.environ.get("CANON_AUTOBLOG_PY") or "").strip()
    fallback_py = r"C:\Users\hymin\AppData\Local\Python\bin\python.exe"
    py_candidates = [
        str(venv_py),
        env_py,
        fallback_py,
        sys.executable,
        "python",
    ]
    # 일부 Windows venv는 pythonw.exe 런처가 깨져 팝업 오류를 띄울 수 있어
    # GUI 자동 실행도 python.exe 기준으로만 실행한다.
    def _is_valid_python(exe: str) -> bool:
        try:
            r = subprocess.run(
                [exe, "-V"],
                capture_output=True,
                text=True,
                timeout=4,
            )
            return r.returncode == 0
        except Exception:
            return False

    py = ""
    for cand in py_candidates:
        c = (cand or "").strip()
        if not c:
            continue
        if _is_valid_python(c):
            py = c
            break
    if not py:
        emit("사용 가능한 Python 실행 파일을 찾지 못했습니다.")
        return False
    web_main = project_path / "blog_studio_web.py"
    desktop_main = project_path / "blog_main.py"
    main_py = web_main if web_main.is_file() else desktop_main
    if not main_py.is_file():
        emit(f"canon Autoblog 경로 없음: {web_main} / {desktop_main}")
        return False

    try:
        if str(project_path) not in sys.path:
            sys.path.insert(0, str(project_path))
        from blog_single_instance import another_instance_running, focus_existing_window

        if another_instance_running():
            focus_existing_window()
            emit("canon4040 Autoblog — 이미 실행 중 (기존 창 사용)")
            return True
    except Exception:
        pass

    emit("canon4040 Autoblog GUI를 실행합니다...")
    if sys.platform == "win32":
        flags = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(
            subprocess, "CREATE_NEW_PROCESS_GROUP", 0
        )
        subprocess.Popen(
            [py, str(main_py)],
            cwd=str(project_path),
            shell=False,
            creationflags=flags,
        )
    else:
        subprocess.Popen([py, str(main_py)], cwd=str(project_path), start_new_session=True)
    return True


def trigger_canon_autoblog(
    parameters: dict[str, Any] | None = None,
    *,
    on_status: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    """JARVIS blog_auto 대신 canon4040 GUI 자동화를 시작."""
    emit = on_status or (lambda _m: None)
    cfg = _load_canon_cfg()
    if not cfg.get("enabled", True):
        return {"ok": False, "error": "canon_autoblog 비활성화됨 (config/blog_automation.json)"}

    p = parameters or {}
    if p.get("preset_id"):
        try:
            from integrations.supabase_jarvis_mobile import merge_preset_payload

            p = merge_preset_payload(str(p.get("preset_id")), p)
        except Exception:
            pass

    project = Path(str(cfg.get("project_path") or _DEFAULT_PROJECT))
    gui_url = str(cfg.get("gui_url") or "http://127.0.0.1:8790").rstrip("/")

    kw = (p.get("keyword") or p.get("topic") or "").strip()
    keywords = p.get("keywords")
    if not kw and isinstance(keywords, list) and keywords:
        kw = ", ".join(str(x).strip() for x in keywords if str(x).strip())

    payload: dict[str, Any] = {
        "source": "jarvis",
        "keyword": kw,
        "keywords": keywords if isinstance(keywords, list) else None,
        "post_type": p.get("post_type"),
        "product_choice": p.get("product_choice"),
        "product_url": p.get("product_url"),
        "use_naver1": p.get("use_naver1", True),
        "use_naver2": p.get("use_naver2", True),
        "use_tistory": p.get("use_tistory", True),
        "use_google": p.get("use_google", False),
        "count": int(p.get("count") or 1),
    }
    if p.get("text_provider"):
        payload["text_provider"] = p.get("text_provider")
    payload = {k: v for k, v in payload.items() if v is not None}

    if not _is_gui_alive(gui_url):
        if not _launch_gui(project, on_status=emit):
            return _write_file_trigger_fallback(project, payload)
        import time

        file_fb = _write_file_trigger_fallback(project, payload)
        emit(file_fb.get("message", "파일 트리거 저장됨"))
        for _ in range(20):
            time.sleep(0.5)
            if not _is_gui_alive(gui_url):
                continue
            try:
                emit("canon4040 Autoblog에 「블로그 작성」요청을 보냅니다...")
                result = _http_json(f"{gui_url}/api/javis/start", payload, timeout=10.0)
                result["backend"] = "canon_autoblog_gui"
                return result
            except error.URLError:
                break
        return file_fb

    try:
        emit("canon4040 Autoblog에 「블로그 작성」요청을 보냅니다...")
        result = _http_json(f"{gui_url}/api/javis/start", payload, timeout=10.0)
        result["backend"] = "canon_autoblog_gui"
        return result
    except error.URLError as e:
        emit("HTTP 실패 — 파일 트리거로 재시도합니다.")
        fb = _write_file_trigger_fallback(project, payload)
        if fb.get("ok"):
            fb["warning"] = str(e)
            return fb
        return {"ok": False, "error": f"Autoblog 트리거 실패: {e}", "backend": "canon_autoblog_gui"}
