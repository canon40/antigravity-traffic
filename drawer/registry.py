# -*- coding: utf-8 -*-
"""서랍(Drawer) — 필요할 때만 모듈을 import. 상시 메모리에 올리지 않음."""

from __future__ import annotations

import importlib
import json
import os
import sys
import threading
from typing import Any, Callable

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_CACHE: dict[str, Any] = {}
_LOCK = threading.Lock()
_LOADED_LOG: list[str] = []


def agents_config() -> dict:
    path = os.path.join(os.path.dirname(__file__), "agents.json")
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def loaded_modules() -> list[str]:
    return list(_LOADED_LOG)


def unload(module_id: str) -> None:
    """캐시에서 제거 (다음 호출 시 다시 로드)."""
    with _LOCK:
        _CACHE.pop(module_id, None)


def unload_all() -> None:
    with _LOCK:
        _CACHE.clear()


def _import_dotted(name: str):
    return importlib.import_module(name)


def get_worker(module_id: str) -> Any:
    """워커 모듈 lazy load. module_id: blog | store | neighbor | verify | wiki | content | automation"""
    alias = {
        "content": "blog_content_gen",
        "automation": "blog_automation_flow",
    }
    key = alias.get(module_id, module_id)
    with _LOCK:
        if key in _CACHE:
            return _CACHE[key]

    workers = (agents_config().get("workers") or {})
    spec = workers.get(module_id, {})
    imports = spec.get("imports") or [key if "." in key or key.endswith("_gen") else f"blog_{key}"]

    if module_id in ("blog", "automation"):
        mod = _import_dotted("blog_automation_flow")
    elif module_id == "content":
        mod = _import_dotted("blog_content_gen")
    elif module_id == "store":
        mod = _import_dotted("store_pipeline")
    elif module_id == "neighbor":
        mod = _import_dotted("naver_module")
    elif module_id == "verify":
        mod = _import_dotted("blog_content_gen")
    elif module_id == "wiki":
        mod = _import_dotted("drawer.wiki")
    else:
        first = imports[0] if imports else key
        mod = _import_dotted(first)

    with _LOCK:
        _CACHE[key] = mod
        if key not in _LOADED_LOG:
            _LOADED_LOG.append(key)
    return mod


def get_content_gen():
    return get_worker("content")


def get_automation_flow():
    return get_worker("automation")


def run_in_subprocess(module_id: str, argv: list[str] | None = None) -> int:
    """GUI와 분리해 워커만 subprocess로 실행 (store 등 무거운 작업)."""
    import subprocess

    cli = os.path.join(_ROOT, "drawer", "cli.py")
    py = sys.executable
    cmd = [py, cli, "invoke", module_id]
    if argv:
        cmd.extend(argv)
    return subprocess.call(cmd, cwd=_ROOT)


def with_worker(module_id: str, fn: Callable[[Any], Any]) -> Any:
    """워커를 로드한 뒤 콜백 실행."""
    mod = get_worker(module_id)
    return fn(mod)
