# -*- coding: utf-8 -*-
"""YouTube 진화 스튜디오 — 서버 기동 후 /evolution/ 열기."""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import webbrowser
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parent
PORT = 8766
URL = f"http://127.0.0.1:{PORT}/evolution/"


def _server_alive() -> bool:
    try:
        with urlopen(f"http://127.0.0.1:{PORT}/api/status", timeout=2) as r:
            return r.status == 200
    except (URLError, OSError, TimeoutError):
        return False


def _port_taken() -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(("127.0.0.1", PORT)) == 0


def main() -> int:
    if _server_alive():
        print(f"서버 실행 중. YouTube 진화: {URL}")
        webbrowser.open(URL)
        return 0

    py = ROOT / ".venv" / "Scripts" / "python.exe"
    if not py.is_file():
        py = Path(sys.executable)

    if _port_taken():
        print(f"포트 {PORT} 사용 중. 브라우저만 엽니다.")
        webbrowser.open(URL)
        return 0

    print(f"스튜디오 서버 시작 중 → {URL}")
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
            webbrowser.open(URL)
            return 0
        time.sleep(0.3)
    webbrowser.open(URL)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
