# -*- coding: utf-8 -*-
"""
canon4040 Autoblog GUI — JARVIS blog_auto_panel 클론 (웹 UI, 포트 8790).

JARVIS integrations/canon_autoblog_bridge.py 가 호출:
  GET  /api/javis/health
  POST /api/javis/start
"""

from __future__ import annotations

import json
import os
import sys
import threading
import traceback
import webbrowser
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from flask import Flask, jsonify, render_template, request

_ROOT = Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

PORT = int(os.environ.get("CANON_AUTOBLOG_PORT", "8790"))
JARVIS_ROOT = Path(os.environ.get("JARVIS_ROOT", r"D:\@code\javis")).resolve()

from hub_llm_env import apply_blog_llm_env

apply_blog_llm_env()

app = Flask(__name__, template_folder="templates")
_logs: list[str] = []
_job_lock = threading.Lock()
_job_running = False
_last_report: dict[str, Any] = {}


def _log(msg: str) -> None:
    line = f"[{datetime.now().strftime('%H:%M:%S')}] {msg}"
    enc = getattr(sys.stdout, "encoding", None) or "utf-8"
    safe = line.encode(enc, errors="replace").decode(enc, errors="replace")
    print(safe, flush=True)
    _logs.append(line)
    if len(_logs) > 200:
        del _logs[: len(_logs) - 200]


def _ensure_jarvis_path() -> bool:
    if not JARVIS_ROOT.is_dir():
        _log(f"JARVIS_ROOT 없음: {JARVIS_ROOT}")
        return False
    root = str(JARVIS_ROOT)
    if root not in sys.path:
        sys.path.insert(0, root)
    return True


def _platforms_from_payload(p: dict[str, Any]) -> list[str] | None:
    if p.get("platforms") and isinstance(p["platforms"], list):
        return [str(x) for x in p["platforms"] if str(x).strip()]
    out: list[str] = []
    if p.get("use_tistory", True):
        out.append("tistory")
    if p.get("use_naver1", True) or p.get("use_naver2", True) or p.get("use_naver", True):
        out.append("naver")
    if p.get("use_google", False) or p.get("use_blogger", False):
        out.append("blogger")
    return out or None


def _run_pipeline(payload: dict[str, Any], *, manage_lock: bool = True) -> dict[str, Any]:
    global _last_report, _job_running
    kw = (payload.get("keyword") or payload.get("topic") or "").strip()
    if not kw:
        kws = payload.get("keywords")
        if isinstance(kws, list) and kws:
            kw = ", ".join(str(x).strip() for x in kws if str(x).strip())
    if not kw:
        return {"ok": False, "error": "키워드가 비어 있습니다."}

    try:
        from blog_pipeline_runner import run_pipeline

        _log(f"블로그 파이프라인 시작: {kw[:80]}")
        result = run_pipeline(payload, on_status=_log)
        _last_report = result if isinstance(result, dict) else {"ok": False, "raw": result}
        if _last_report.get("ok"):
            _log("블로그 파이프라인 완료")
        else:
            _log("실패: " + str(_last_report.get("error") or _last_report))
        return _last_report
    except Exception as e:
        _log(traceback.format_exc())
        _last_report = {"ok": False, "error": str(e), "keyword": kw}
        return _last_report
    finally:
        if manage_lock:
            with _job_lock:
                _job_running = False


def _start_async(payload: dict[str, Any]) -> dict[str, Any]:
    global _job_running
    keywords = payload.get("keywords")
    if isinstance(keywords, list) and len(keywords) > 1:
        kws = [str(x).strip() for x in keywords if str(x).strip()]
        if kws:
            payload = {**payload, "keywords": kws, "keyword": kws[0]}
            with _job_lock:
                if _job_running:
                    return {"ok": False, "error": "이미 블로그 작업이 실행 중입니다.", "busy": True}
                _job_running = True

            def _batch_worker() -> None:
                global _job_running
                try:
                    for i, kw in enumerate(kws, 1):
                        _log(f"배치 {i}/{len(kws)}: {kw}")
                        one = {**payload, "keyword": kw}
                        _run_pipeline(one, manage_lock=False)
                finally:
                    with _job_lock:
                        _job_running = False

            threading.Thread(target=_batch_worker, daemon=True).start()
            return {
                "ok": True,
                "message": f"키워드 {len(kws)}개 순차 실행을 시작했습니다.",
                "keywords": kws,
                "async": True,
            }

    with _job_lock:
        if _job_running:
            return {"ok": False, "error": "이미 블로그 작업이 실행 중입니다.", "busy": True}
        _job_running = True

    def _worker() -> None:
        try:
            _run_pipeline(payload)
        except Exception as e:
            _log(f"worker error: {e}")

    threading.Thread(target=_worker, daemon=True).start()
    kw = (payload.get("keyword") or "").strip()
    return {"ok": True, "message": "블로그 파이프라인을 시작했습니다.", "keyword": kw, "async": True}


def _drain_file_triggers() -> None:
    try:
        from javis_bridge import pop_pending_trigger

        pending = pop_pending_trigger()
        if pending:
            _log("파일 트리거 수신 — 자동 시작")
            _start_async(pending)
    except Exception:
        pass


@app.route("/")
def index():
    return render_template("blog_studio.html", jarvis_root=str(JARVIS_ROOT), port=PORT)


@app.route("/api/javis/health")
def javis_health():
    try:
        from blog_pipeline_runner import jarvis_pipeline_available

        jarvis_ok = jarvis_pipeline_available()
    except Exception:
        jarvis_ok = JARVIS_ROOT.is_dir()
    return jsonify({
        "ok": True,
        "service": "canon4040-autoblog",
        "port": PORT,
        "jarvis_root": str(JARVIS_ROOT),
        "jarvis_installed": jarvis_ok,
        "standalone": True,
        "job_running": _job_running,
        "llm": apply_blog_llm_env(),
    })


@app.route("/api/javis/start", methods=["POST"])
def javis_start():
    payload = request.get_json(silent=True) or {}
    return jsonify(_start_async(payload))


@app.route("/api/blog/status")
def blog_status():
    try:
        from blog_pipeline_runner import jarvis_pipeline_available

        if jarvis_pipeline_available():
            from integrations.blog_auto_pipeline import format_status_ko

            return jsonify({"ok": True, "text": format_status_ko(), "mode": "jarvis"})
        return jsonify({
            "ok": True,
            "text": "단독 모드 — accounts.json·GUI 설정으로 실행됩니다.",
            "mode": "standalone",
        })
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})


@app.route("/api/blog/last")
def blog_last():
    report = dict(_last_report) if _last_report else {}
    try:
        from blog_pipeline_runner import jarvis_pipeline_available

        if jarvis_pipeline_available() and not report:
            from integrations.blog_auto_pipeline import load_last_blog_report

            report = load_last_blog_report() or {}
    except Exception:
        pass
    return jsonify({"ok": True, "report": report, "job_running": _job_running})


@app.route("/api/blog/keywords", methods=["GET", "POST"])
def blog_keywords():
    from hub_accounts import keywords_from_accounts, parse_keywords_text, save_accounts_keywords

    if request.method == "GET":
        kws = keywords_from_accounts()
        return jsonify({"keywords": kws, "keywords_text": "\n".join(kws), "count": len(kws)})
    data = request.get_json(silent=True) or {}
    raw = data.get("keywords_text", data.get("keywords", ""))
    if isinstance(raw, list):
        kws = parse_keywords_text(", ".join(str(x) for x in raw))
    else:
        kws = parse_keywords_text(str(raw or ""))
    save_accounts_keywords(kws)
    try:
        from hub_accounts import sync_accounts_keywords_to_config

        sync_accounts_keywords_to_config()
    except Exception:
        pass
    return jsonify({"success": True, "keywords": kws, "count": len(kws)})


@app.route("/api/blog/run", methods=["POST"])
def blog_run():
    payload = request.get_json(silent=True) or {}
    if payload.get("sync"):
        return jsonify(_run_pipeline(payload))
    return jsonify(_start_async(payload))


@app.route("/api/logs")
def api_logs():
    return jsonify({"logs": _logs[-80:]})


def register_blog_routes(flask_app: Flask, *, url_prefix: str = "") -> None:
    """SEO 허브(app.py)에 블로그 스튜디오 API 마운트."""
    prefix = (url_prefix or "").rstrip("/")

    def _route(rule: str, **kwargs):
        path = f"{prefix}{rule}" if prefix else rule
        return flask_app.route(path, **kwargs)

    @_route("/api/blog/status")
    def blog_status_embed():
        return blog_status()

    @_route("/api/blog/last")
    def blog_last_embed():
        return blog_last()

    @_route("/api/blog/run", methods=["POST"])
    def blog_run_embed():
        return blog_run()

    @_route("/api/blog/logs")
    def blog_logs_embed():
        return api_logs()

    @_route("/api/blog/keywords", methods=["GET", "POST"])
    def blog_keywords_embed():
        return blog_keywords()

    @_route("/api/javis/health")
    def javis_health_embed():
        return javis_health()

    @_route("/api/javis/start", methods=["POST"])
    def javis_start_embed():
        return javis_start()


def main() -> None:
    _drain_file_triggers()
    url = f"http://127.0.0.1:{PORT}/"
    _log(f"canon4040 Autoblog GUI — {url}")
    threading.Timer(1.2, lambda: webbrowser.open(url)).start()
    # 로그 폴링, 상태 폴링, 실행 요청이 겹쳐도 응답 정체(하얀 화면)를 막기 위해 멀티스레드로 실행.
    app.run(host="0.0.0.0", port=PORT, debug=False, use_reloader=False, threaded=True)


if __name__ == "__main__":
    main()
