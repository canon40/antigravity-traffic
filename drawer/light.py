# -*- coding: utf-8 -*-
"""경량(서랍) 모드 — 필요한 워커만 켜고 RAM/CPU 절약."""

from __future__ import annotations

import os


def _env_on(name: str, default: str = "1") -> bool:
    v = os.environ.get(name, default).strip().lower()
    return v not in ("0", "false", "no", "off")


def light_gui() -> bool:
    """기본 ON: GUI는 가볍게, 무거운 것은 자동화 시에만."""
    return _env_on("BLOG_LIGHT_GUI", "1")


def lazy_tabs() -> bool:
    """탭을 처음 열 때만 생성."""
    return _env_on("BLOG_LAZY_TABS", "1")


def javis_bridge_enabled() -> bool:
    """JARVIS HTTP는 기본 OFF (경량 GUI). 켜려면 BLOG_JAVIS_BRIDGE=1."""
    if not light_gui():
        return _env_on("BLOG_JAVIS_BRIDGE", "1")
    return _env_on("BLOG_JAVIS_BRIDGE", "0")


def defer_browser() -> bool:
    """원고·이미지 완료 후에만 Chrome/Playwright 실행."""
    return _env_on("BLOG_DEFER_BROWSER", "1")


def browser_per_round() -> bool:
    """라운드마다 브라우저 열고 닫기 (대기 시간 중 Chrome 안 켜 둠)."""
    return _env_on("BLOG_BROWSER_PER_ROUND", "1")


def unload_after_job() -> bool:
    """작업 끝나면 서랍 캐시 비우기."""
    return _env_on("BLOG_UNLOAD_AFTER_JOB", "1")
