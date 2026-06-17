# -*- coding: utf-8 -*-
"""JARVIS ↔ canon4040 Autoblog 연동 (HTTP 트리거 + 파일 트리거)."""

from __future__ import annotations

import json
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Callable

DEFAULT_PORT = int(os.environ.get("CANON_AUTOBLOG_PORT", "8790"))
TRIGGER_DIR = os.environ.get(
    "CANON_AUTOBLOG_TRIGGER_DIR",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), ".javis"),
)


def ensure_trigger_dir() -> str:
    os.makedirs(TRIGGER_DIR, exist_ok=True)
    return TRIGGER_DIR


def write_file_trigger(payload: dict[str, Any]) -> str:
    """GUI가 꺼져 있을 때 파일로 시작 요청을 남긴다."""
    ensure_trigger_dir()
    path = os.path.join(TRIGGER_DIR, "start_request.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    return path


def pop_pending_trigger() -> dict[str, Any] | None:
    """`.javis/start_request.json` — 읽고 삭제 (허브·GUI 폴링용)."""
    path = os.path.join(TRIGGER_DIR, "start_request.json")
    try:
        if not os.path.isfile(path):
            return None
        with open(path, "r", encoding="utf-8") as f:
            payload = json.load(f)
        os.remove(path)
        return payload if isinstance(payload, dict) else None
    except (OSError, json.JSONDecodeError):
        return None


class JavisBridgeServer:
    """blog_main GUI 프로세스 안에서 동작하는 경량 HTTP 서버."""

    def __init__(
        self,
        on_start: Callable[[dict[str, Any]], dict[str, Any]],
        *,
        port: int = DEFAULT_PORT,
        status_fn: Callable[[], dict[str, Any]] | None = None,
    ):
        self.port = port
        self.on_start = on_start
        self.status_fn = status_fn or (lambda: {"running": False})
        self._httpd: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        handler_cls = self._make_handler()
        self._httpd = ThreadingHTTPServer(("127.0.0.1", self.port), handler_cls)
        self._thread = threading.Thread(target=self._httpd.serve_forever, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        if self._httpd:
            self._httpd.shutdown()
            self._httpd = None

    def _make_handler(self):
        bridge = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, format, *args):
                return

            def _json(self, code: int, payload: dict):
                data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
                self.send_response(code)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def do_GET(self):
                if self.path == "/api/javis/status":
                    self._json(200, bridge.status_fn())
                    return
                if self.path == "/api/javis/health":
                    self._json(200, {"ok": True, "service": "canon_autoblog"})
                    return
                if self.path == "/api/javis/modules":
                    try:
                        from drawer.registry import agents_config, loaded_modules
                        from blog_constants import DRAWER_MODULES

                        cfg = agents_config()
                        self._json(200, {
                            "ok": True,
                            "modules": list(DRAWER_MODULES),
                            "workers": cfg.get("workers", {}),
                            "text_chain": cfg.get("text_chain", []),
                            "jarvis_model_routing": cfg.get("jarvis_model_routing", {}),
                            "loaded": loaded_modules(),
                        })
                    except Exception as e:
                        self._json(500, {"ok": False, "message": str(e)})
                    return
                if self.path.startswith("/api/javis/routing"):
                    try:
                        from drawer.model_router import summarize_model_route
                        import urllib.parse

                        qs = urllib.parse.urlparse(self.path).query
                        payload = {}
                        if qs:
                            for part in qs.split("&"):
                                if "=" in part:
                                    k, v = part.split("=", 1)
                                    payload[urllib.parse.unquote_plus(k)] = urllib.parse.unquote_plus(
                                        v
                                    )
                        self._json(200, {"ok": True, **summarize_model_route(payload or None)})
                    except Exception as e:
                        self._json(500, {"ok": False, "message": str(e)})
                    return
                self._json(404, {"ok": False, "message": "not found"})

            def do_POST(self):
                if self.path != "/api/javis/start":
                    self._json(404, {"ok": False, "message": "not found"})
                    return
                length = int(self.headers.get("Content-Length", "0"))
                raw = self.rfile.read(length) if length > 0 else b"{}"
                try:
                    payload = json.loads(raw.decode("utf-8"))
                except Exception:
                    self._json(400, {"ok": False, "message": "invalid json"})
                    return
                try:
                    result = bridge.on_start(payload)
                    self._json(200, result)
                except Exception as e:
                    self._json(400, {"ok": False, "message": str(e)})

        return Handler


class JavisFileWatcher:
    """`.javis/start_request.json` 폴링 — JARVIS가 GUI 없이 요청 파일만 쓸 때."""

    def __init__(self, root, on_start: Callable[[dict[str, Any]], None], interval_ms: int = 2000):
        self.root = root
        self.on_start = on_start
        self.interval_ms = interval_ms
        self._last_mtime = 0.0
        ensure_trigger_dir()

    def tick(self):
        path = os.path.join(TRIGGER_DIR, "start_request.json")
        try:
            if os.path.isfile(path):
                mtime = os.path.getmtime(path)
                if mtime > self._last_mtime:
                    self._last_mtime = mtime
                    with open(path, "r", encoding="utf-8") as f:
                        payload = json.load(f)
                    os.remove(path)
                    self.on_start(payload)
        except Exception:
            pass
        self.root.after(self.interval_ms, self.tick)

    def start(self):
        self.root.after(self.interval_ms, self.tick)
