# -*- coding: utf-8 -*-
"""상세페이지 로컬 미리보기 서버 — 브라우저에서 바로 확인."""

from __future__ import annotations

import argparse
import http.server
import socket
import subprocess
import sys
import threading
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PREVIEW = ROOT / "preview"
BUILD = ROOT / "build_preview.py"
DEFAULT_PORT = 8765


def _find_port(start: int) -> int:
    for port in range(start, start + 20):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    raise RuntimeError(f"no free port in {start}..{start + 19}")


def _run_build() -> None:
    subprocess.run([sys.executable, str(BUILD)], cwd=str(ROOT.parent.parent), check=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="퍼마코트 바이크 상세페이지 미리보기 서버")
    parser.add_argument("--no-build", action="store_true", help="빌드 생략 (기존 HTML만 서빙)")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help=f"포트 (기본 {DEFAULT_PORT})")
    parser.add_argument(
        "--sku",
        default="",
        help="바로 열 SKU (예: bike_quick, bike_titan). 비우면 목록 index.html",
    )
    args = parser.parse_args()

    if not args.no_build:
        print("[build] 콘티 → 상세 HTML 생성...")
        _run_build()

    if not PREVIEW.is_dir():
        PREVIEW.mkdir(parents=True, exist_ok=True)

    port = args.port
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("127.0.0.1", port))
    except OSError:
        port = _find_port(args.port)
        print(f"[port] {args.port} 사용 중 → {port} 로 변경")

    page = "index.html"
    if args.sku:
        sku = args.sku if args.sku.endswith(".html") else f"{args.sku}.html"
        if not (PREVIEW / sku).exists():
            print(f"ERROR: {PREVIEW / sku} 없음. --no-build 없이 다시 실행하세요.", file=sys.stderr)
            sys.exit(1)
        page = sku

    url = f"http://127.0.0.1:{port}/{page}"

    class QuietHandler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *a, **kw):
            super().__init__(*a, directory=str(PREVIEW), **kw)

        def log_message(self, fmt: str, *log_args) -> None:
            if log_args and str(log_args[0]).startswith("4"):
                super().log_message(fmt, *log_args)

    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", port), QuietHandler)

    def _open_browser() -> None:
        webbrowser.open(url)

    threading.Timer(0.35, _open_browser).start()

    print()
    print("  상세페이지 미리보기")
    print(f"  {url}")
    print("  목록: http://127.0.0.1:{port}/index.html")
    print("  종료: Ctrl+C")
    print()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n[stop] 서버 종료")
        httpd.shutdown()


if __name__ == "__main__":
    main()
