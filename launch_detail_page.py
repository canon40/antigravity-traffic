# -*- coding: utf-8 -*-
"""상세페이지 스튜디오 — 서버 기동 후 /detail/ 만 열기."""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import webbrowser
from pathlib import Path
from urllib.error import URLError
from urllib.parse import quote
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parent
PORT = 8766
URL = f"http://127.0.0.1:{PORT}/detail/"


def _server_alive() -> bool:
    # /api/status 는 Ollama ping 으로 수 초 걸릴 수 있어 lite 엔드포인트 사용
    try:
        with urlopen(f"http://127.0.0.1:{PORT}/api/status?lite=1", timeout=2) as r:
            return r.status == 200
    except (URLError, OSError, TimeoutError):
        return False


def _port_taken() -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(("127.0.0.1", PORT)) == 0


def main() -> int:
    slug = ""
    if len(sys.argv) > 1:
        slug = sys.argv[1].strip()

    open_url = URL
    if slug:
        open_url = f"{URL}?slug={quote(slug, safe='')}"

    if _server_alive():
        print(f"서버 실행 중. 상세페이지 스튜디오: {open_url}")
        webbrowser.open(open_url)
        return 0

    py = ROOT / ".venv" / "Scripts" / "python.exe"
    if not py.is_file():
        py = Path(sys.executable)

    if _port_taken():
        print(f"포트 {PORT} 사용 중이나 API 응답 없음.")
        webbrowser.open(open_url)
        return 1

    print(f"스튜디오 서버 시작 중 → {open_url}")
    env = os.environ.copy()
    env.setdefault("PYTHONUTF8", "1")
    env.setdefault("PYTHONIOENCODING", "utf-8")
    subprocess.Popen(
        [str(py), str(ROOT / "shorts_studio_server.py")],
        cwd=str(ROOT),
        env=env,
        creationflags=subprocess.CREATE_NEW_CONSOLE if sys.platform == "win32" else 0,
    )
    import time

    for _ in range(30):
        if _server_alive():
            webbrowser.open(open_url)
            return 0
        time.sleep(0.3)
    print("서버가 아직 준비되지 않았습니다. 잠시 후 브라우저에서 직접 열어 주세요.")
    webbrowser.open(open_url)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
