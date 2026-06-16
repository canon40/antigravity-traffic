# -*- coding: utf-8 -*-
"""업무 대시보드 로컬 서버 — 클릭 한 번으로 블로그·DM·서이추 실행."""

from __future__ import annotations

import json
import socket
import sys
import threading
import webbrowser
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

_ROOT = Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

OPS_DIR = _ROOT / "data" / "ops"
LOG_PATH = _ROOT / "data" / "weekly_ops.log"
DEFAULT_PORT = 8770

_lock = threading.Lock()
_job_state = {
    "running": False,
    "task": "",
    "started_at": "",
    "last_task": "",
    "last_error": "",
    "last_ok": True,
}


def _tail_log(max_lines: int = 40) -> str:
    if not LOG_PATH.is_file():
        return "(로그 없음)"
    try:
        lines = LOG_PATH.read_text(encoding="utf-8", errors="replace").splitlines()
        return "\n".join(lines[-max_lines:])
    except Exception as e:
        return f"(로그 읽기 실패: {e})"


def _set_running(task: str) -> bool:
    with _lock:
        if _job_state["running"]:
            return False
        _job_state.update(
            {
                "running": True,
                "task": task,
                "started_at": datetime.now().isoformat(timespec="seconds"),
                "last_error": "",
            }
        )
        return True


def _finish(task: str, ok: bool, err: str = "") -> None:
    with _lock:
        _job_state.update(
            {
                "running": False,
                "task": "",
                "last_task": task,
                "last_ok": ok,
                "last_error": err,
            }
        )
    if task not in ("refresh",):
        try:
            from blog_weekly_ops import build_ops_dashboard, load_json, ROUTINE_PATH

            build_ops_dashboard(load_json(ROUTINE_PATH))
        except Exception:
            pass


def _run_in_thread(task: str, fn) -> None:
    def worker() -> None:
        try:
            fn()
            _finish(task, True)
        except Exception as e:
            from blog_weekly_ops import log

            log(f"❌ [{task}] {e}")
            _finish(task, False, str(e))

    threading.Thread(target=worker, daemon=True).start()


def _dispatch(action: str, force: bool = False) -> None:
    from blog_weekly_ops import (
        build_ops_dashboard,
        load_json,
        log,
        run_blog_pipeline,
        run_dm_pack_only,
        run_neighbor_only,
        run_weekly_ops,
        ROUTINE_PATH,
    )

    if action == "full":
        _run_in_thread("full", lambda: run_weekly_ops(force=False, open_browser=False))
    elif action == "force":
        _run_in_thread("force", lambda: run_weekly_ops(force=True, open_browser=False))
    elif action == "blog":
        _run_in_thread("blog", lambda: run_blog_pipeline(force=force))
    elif action == "neighbor":
        _run_in_thread("neighbor", run_neighbor_only)
    elif action == "dm":

        def _dm() -> None:
            run_dm_pack_only()
            build_ops_dashboard(load_json(ROUTINE_PATH))

        _run_in_thread("dm", _dm)
    elif action == "refresh":
        build_ops_dashboard(load_json(ROUTINE_PATH))
        log("대시보드 갱신")
        _finish("refresh", True)
    else:
        raise ValueError(f"unknown action: {action}")


class OpsHandler(BaseHTTPRequestHandler):
    def log_message(self, fmt: str, *args) -> None:
        if args and str(args[0]).startswith("4"):
            super().log_message(fmt, *args)

    def _json(self, code: int, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _file(self, path: Path, content_type: str) -> None:
        if not path.is_file():
            self.send_error(404)
            return
        data = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path in ("/", "/dashboard.html"):
            from blog_weekly_ops import build_ops_dashboard, load_json, ROUTINE_PATH

            build_ops_dashboard(load_json(ROUTINE_PATH))
            return self._file(OPS_DIR / "dashboard.html", "text/html; charset=utf-8")
        if path == "/api/status":
            with _lock:
                st = dict(_job_state)
            st["log_tail"] = _tail_log()
            return self._json(200, st)
        if path == "/dm_today.html":
            return self._file(OPS_DIR / "dm_today.html", "text/html; charset=utf-8")
        if path == "/dm_today.json":
            return self._file(OPS_DIR / "dm_today.json", "application/json; charset=utf-8")
        rel = path.lstrip("/")
        candidate = OPS_DIR / rel
        if candidate.is_file():
            ctype = "text/html; charset=utf-8" if candidate.suffix == ".html" else "application/octet-stream"
            return self._file(candidate, ctype)
        self.send_error(404)

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        if not path.startswith("/api/run/"):
            self.send_error(404)
            return
        action = path.split("/api/run/", 1)[-1].strip().lower()
        if not _set_running(action):
            return self._json(409, {"error": "이미 다른 작업이 실행 중입니다.", "task": _job_state.get("task")})
        try:
            _dispatch(action, force=action == "force")
            return self._json(200, {"ok": True, "action": action})
        except Exception as e:
            _finish(action, False, str(e))
            return self._json(400, {"error": str(e)})


def _find_port(start: int) -> int:
    for port in range(start, start + 20):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    raise RuntimeError(f"no free port in {start}..{start + 19}")


def serve_forever(port: int = DEFAULT_PORT, open_browser: bool = True) -> None:
    from blog_weekly_ops import build_ops_dashboard, load_json, ROUTINE_PATH

    OPS_DIR.mkdir(parents=True, exist_ok=True)
    build_ops_dashboard(load_json(ROUTINE_PATH))

    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("127.0.0.1", port))
    except OSError:
        port = _find_port(port)

    url = f"http://127.0.0.1:{port}/"
    httpd = ThreadingHTTPServer(("127.0.0.1", port), OpsHandler)

    if open_browser:
        threading.Timer(0.4, lambda: webbrowser.open(url)).start()

    print()
    print("  업무 대시보드 (클릭 실행)")
    print(f"  {url}")
    print("  종료: Ctrl+C")
    print()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n서버 종료")
        httpd.shutdown()


if __name__ == "__main__":
    serve_forever()
