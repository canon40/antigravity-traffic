# -*- coding: utf-8 -*-
"""Playwright Chromium 사전 점검·자동 설치 (GUI/pythonw 환경 포함)."""

from __future__ import annotations

import asyncio
import os
import subprocess
import sys

_ROOT = os.path.dirname(os.path.abspath(__file__))


def python_exe() -> str:
    """pythonw.exe 로 실행 중이면 동일 venv 의 python.exe 를 사용."""
    exe = sys.executable
    if exe.lower().endswith("pythonw.exe"):
        alt = os.path.join(os.path.dirname(exe), "python.exe")
        if os.path.isfile(alt):
            return alt
    return exe


async def _probe_async() -> bool:
    try:
        from playwright.async_api import async_playwright

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            await browser.close()
        return True
    except Exception:
        return False


def probe_playwright() -> bool:
    try:
        return asyncio.run(_probe_async())
    except Exception:
        return False


def install_chromium(log=None) -> bool:
    log = log or (lambda _m: None)
    py = python_exe()
    log("   🔧 Playwright Chromium 설치 중... (최초 1회, 수 분 걸릴 수 있음)")
    try:
        proc = subprocess.run(
            [py, "-m", "playwright", "install", "chromium"],
            cwd=_ROOT,
            capture_output=True,
            text=True,
            timeout=600,
        )
    except Exception as e:
        log(f"   ❌ Playwright 설치 실패: {e}")
        return False
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "").strip()[:240]
        log(f"   ❌ Playwright 설치 실패: {detail or proc.returncode}")
        return False
    log("   ✅ Playwright Chromium 설치 완료")
    return True


def ensure_playwright_ready(log=None, *, auto_install: bool = True) -> bool:
    """브라우저 자동화 전 호출. 실패 시 False."""
    log = log or (lambda _m: None)
    if probe_playwright():
        return True
    if not auto_install:
        log("   ⛔ Playwright 미설치 — run_fix_playwright.bat 실행 필요")
        return False
    if not install_chromium(log):
        return False
    ok = probe_playwright()
    if not ok:
        log("   ⛔ Playwright 점검 실패 — run_fix_playwright.bat 실행 후 재시도")
    return ok
