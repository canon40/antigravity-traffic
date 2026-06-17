# -*- coding: utf-8 -*-
"""Autoblog GUI 단일 인스턴스 — 중복 창 방지."""

from __future__ import annotations

import atexit
import sys

_MUTEX_NAME = "Global\\canon4040_autoblog_gui_v1"
_WINDOW_TITLE = "canon4040's Autoblog"
_mutex_handle = None


def _is_windows() -> bool:
    return sys.platform == "win32"


def _find_window(title: str) -> int:
    if not _is_windows():
        return 0
    try:
        import ctypes

        return int(ctypes.windll.user32.FindWindowW(None, title))
    except Exception:
        return 0


def _focus_existing_window() -> bool:
    if not _is_windows():
        return False
    try:
        import ctypes

        user32 = ctypes.windll.user32
        hwnd = user32.FindWindowW(None, _WINDOW_TITLE)
        if hwnd:
            user32.ShowWindow(hwnd, 9)  # SW_RESTORE
            user32.SetForegroundWindow(hwnd)
            return True
        return False
    except Exception:
        return False


def _show_already_running_message() -> None:
    if not _is_windows():
        print("canon4040's Autoblog is already running.", file=sys.stderr)
        return
    try:
        import ctypes

        ctypes.windll.user32.MessageBoxW(
            0,
            "Autoblog가 이미 실행 중입니다.\n기존 창을 사용해 주세요.",
            _WINDOW_TITLE,
            0x40,
        )
    except Exception:
        print("canon4040's Autoblog is already running.", file=sys.stderr)


def _gui_window_visible() -> bool:
    return _find_window(_WINDOW_TITLE) > 0


def _mutex_taken() -> bool:
    """다른 프로세스가 Autoblog mutex를 잡고 있는지."""
    if not _is_windows():
        return False
    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32
        SYNCHRONIZE = 0x00100000
        handle = kernel32.OpenMutexW(SYNCHRONIZE, False, _MUTEX_NAME)
        if handle:
            kernel32.CloseHandle(handle)
            return True
        return False
    except Exception:
        return False


def acquire_single_instance() -> bool:
    """
    True  → 이 프로세스가 GUI를 띄워도 됨
    False → 다른 인스턴스가 이미 실행 중 (기존 창 포커스 후 종료)
    """
    global _mutex_handle

    if _gui_window_visible():
        _focus_existing_window()
        _show_already_running_message()
        return False

    if not _is_windows():
        return True

    import ctypes

    kernel32 = ctypes.windll.kernel32
    ERROR_ALREADY_EXISTS = 183
    kernel32.SetLastError(0)
    handle = kernel32.CreateMutexW(None, True, _MUTEX_NAME)
    already = kernel32.GetLastError() == ERROR_ALREADY_EXISTS
    if already:
        if handle:
            kernel32.CloseHandle(handle)
        _focus_existing_window()
        _show_already_running_message()
        return False

    _mutex_handle = handle
    atexit.register(_release_mutex)
    return True


def _release_mutex() -> None:
    global _mutex_handle
    if _mutex_handle and _is_windows():
        try:
            import ctypes

            ctypes.windll.kernel32.CloseHandle(_mutex_handle)
        except Exception:
            pass
    _mutex_handle = None


def focus_existing_window() -> bool:
    """이미 떠 있는 Autoblog 창을 앞으로."""
    return _focus_existing_window()


def another_instance_running() -> bool:
    """외부 스크립트(bat/JARVIS)용 — GUI 창 또는 mutex 보유 프로세스."""
    return _gui_window_visible() or _mutex_taken()


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--check":
        if another_instance_running():
            focus_existing_window()
            raise SystemExit(0)
        raise SystemExit(1)
    if acquire_single_instance():
        raise SystemExit(0)
    raise SystemExit(2)
