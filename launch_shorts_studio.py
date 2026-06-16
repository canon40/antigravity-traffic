# -*- coding: utf-8 -*-
"""쇼츠 스튜디오 — 이미 떠 있으면 브라우저만, 없으면 서버 기동."""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
import webbrowser
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen
import json

ROOT = Path(__file__).resolve().parent
PORT = 8766
BASE = f"http://127.0.0.1:{PORT}"
URL = f"{BASE}/"


def _server_alive() -> bool:
    """lite status — bootstrap_v 플래그로 구버전( bootstrap 404 ) 서버 오탐 방지."""
    try:
        with urlopen(f"{BASE}/api/status?lite=1", timeout=5) as r:
            if r.status != 200:
                return False
            body = json.loads(r.read().decode("utf-8"))
            return body.get("bootstrap_v") == 1
    except (URLError, OSError, TimeoutError, ValueError, KeyError):
        return False


def _bootstrap_ready_once(timeout_sec: float = 30.0) -> bool:
    """Studio UI가 사용하는 /api/bootstrap 이 실제로 ok=True 를 반환하는지 확인."""
    try:
        with urlopen(f"{BASE}/api/bootstrap", timeout=timeout_sec) as r:
            if r.status != 200:
                return False
            body = json.loads(r.read().decode("utf-8"))
            return body.get("ok") is True
    except (URLError, OSError, TimeoutError, ValueError, KeyError):
        return False


def _wait_for_bootstrap(timeout_sec: float, interval: float = 0.5) -> bool:
    deadline = time.monotonic() + timeout_sec
    while time.monotonic() < deadline:
        if _bootstrap_ready_once(timeout_sec=min(30.0, max(5.0, deadline - time.monotonic()))):
            return True
        time.sleep(interval)
    return False


def _server_ready() -> bool:
    return _server_alive() and _bootstrap_ready_once()


def _port_taken() -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(("127.0.0.1", PORT)) == 0


def _pids_on_port(port: int) -> list[int]:
    pids: list[int] = []
    if sys.platform == "win32":
        try:
            out = subprocess.check_output(
                ["netstat", "-ano"],
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            token = f":{port}"
            for line in out.splitlines():
                if "LISTENING" not in line or token not in line:
                    continue
                parts = line.split()
                if not parts:
                    continue
                pid_s = parts[-1]
                if pid_s.isdigit():
                    pid = int(pid_s)
                    if pid != os.getpid():
                        pids.append(pid)
        except (OSError, subprocess.SubprocessError):
            return []
    else:
        try:
            out = subprocess.check_output(
                ["lsof", "-ti", f":{port}"],
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            for line in out.splitlines():
                line = line.strip()
                if line.isdigit():
                    pids.append(int(line))
        except (OSError, subprocess.SubprocessError, FileNotFoundError):
            return []
    return sorted(set(pids))


def _kill_port_listeners(port: int) -> bool:
    killed = False
    for pid in _pids_on_port(port):
        try:
            if sys.platform == "win32":
                subprocess.run(
                    ["taskkill", "/PID", str(pid), "/F"],
                    check=False,
                    capture_output=True,
                )
            else:
                subprocess.run(["kill", "-9", str(pid)], check=False, capture_output=True)
            killed = True
        except OSError:
            pass
    if killed:
        time.sleep(0.6)
    return killed


def _wait_for_server(timeout_sec: float = 60.0, interval: float = 0.35) -> bool:
    deadline = time.monotonic() + timeout_sec
    while time.monotonic() < deadline:
        if _server_alive():
            remaining = max(0.0, deadline - time.monotonic())
            return _wait_for_bootstrap(remaining, interval=0.5)
        time.sleep(interval)
    return False


def _start_server(py: Path) -> None:
    env = os.environ.copy()
    env.setdefault("PYTHONUTF8", "1")
    env.setdefault("PYTHONIOENCODING", "utf-8")
    env["SHORTS_STUDIO_NO_AUTO_BROWSER"] = "1"
    subprocess.Popen(
        [str(py), str(ROOT / "shorts_studio_server.py")],
        cwd=str(ROOT),
        env=env,
        creationflags=subprocess.CREATE_NEW_CONSOLE if sys.platform == "win32" else 0,
    )


def main() -> int:
    py = ROOT / ".venv" / "Scripts" / "python.exe"
    if not py.is_file():
        py = Path(sys.executable)

    if _server_ready():
        print(f"서버 실행 중. 브라우저 열기: {URL}")
        webbrowser.open(URL)
        return 0

    if _server_alive() and not _bootstrap_ready_once():
        print(
            f"포트 {PORT} 서버는 응답하지만 /api/bootstrap 이 준비되지 않았습니다. "
            "프로세스를 정리한 뒤 재시작합니다."
        )
        _kill_port_listeners(PORT)
        time.sleep(0.4)

    if _port_taken():
        print(
            f"포트 {PORT} 사용 중이나 스튜디오 API가 준비되지 않음 "
            f"(구버전 서버 또는 응답 없음) — 기존 프로세스 정리 후 재시작합니다."
        )
        _kill_port_listeners(PORT)
        time.sleep(0.4)
        if _server_ready():
            print(f"서버 복구됨. 브라우저 열기: {URL}")
            webbrowser.open(URL)
            return 0

    print(f"쇼츠 스튜디오 서버 시작 중 ({URL})")
    _start_server(py)
    if not _wait_for_server():
        print(
            f"서버가 60초 안에 준비되지 않습니다 (/api/status 또는 /api/bootstrap).\n"
            "새로 열린 콘솔 창의 오류 메시지를 확인하세요."
        )
        return 1
    print(f"서버 준비 완료. 브라우저 열기: {URL}")
    webbrowser.open(URL)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
