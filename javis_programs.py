# -*- coding: utf-8 -*-
"""JARVIS·Traffic 프로그램 카탈로그 및 로컬 실행."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable

from hub_runtime import is_cloud_hub
from javis_serverless import cloud_runtime, is_vercel_runtime, resolve_cloud_action, run_serverless_program

_ROOT = Path(__file__).resolve().parent
_CATALOG_PATH = _ROOT / "data" / "programs_catalog.json"

CATEGORIES: dict[str, str] = {
    "traffic": "트래픽 · SEO 허브",
    "seo": "SEO · 순위",
    "blog": "블로그 · 콘텐츠",
    "video": "영상 · 숏츠",
    "studio": "스튜디오 · 상세페이지",
    "agent": "JARVIS 에이전트",
    "ops": "연동 · 점검",
}


# 로컬 번들·JARVIS 외부 경로에 bat이 없을 때 login2 루트의 대체 런처
_LOCAL_BAT_FALLBACKS: dict[str, str] = {
    "run_블로그_전체.bat": "run_블로그_전체.bat",
    "run_블로그_자동.bat": "run_블로그_자동.bat",
    "run_blog_post.bat": "run_blog_post.bat",
}


def _resolve_jarvis_root() -> Path:
    bundled = _ROOT / "javis"
    external = Path(os.environ.get("JARVIS_ROOT", r"D:\@code\javis"))
    bundled_count = len(list(bundled.glob("run_*.bat"))) if bundled.is_dir() else 0
    external_count = len(list(external.glob("run_*.bat"))) if external.is_dir() else 0
    if bundled_count > 0:
        return bundled.resolve()
    if external_count > 0:
        return external.resolve()
    for path in (external, bundled):
        if path.is_dir() and any(path.glob("run_*.bat")):
            return path.resolve()
    if external.is_dir() and not str(external).startswith("/app"):
        return external.resolve()
    return _ROOT.resolve()


JARVIS_ROOT = _resolve_jarvis_root()

# UI·JARVIS 호출 호환 (카탈로그 ID 변경 대비)
PROGRAM_ID_ALIASES: dict[str, str] = {
    "traffic_blog_studio": "traffic_autoblog_gui",
    "local_run_gui": "traffic_autoblog_gui",
    "local_run_blog_post": "traffic_blog_post",
}


def _load_catalog_raw() -> dict[str, Any]:
    if not _CATALOG_PATH.is_file():
        return {}
    try:
        with open(_CATALOG_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def _load_catalog_programs() -> list[dict[str, Any]]:
    data = _load_catalog_raw()
    programs = data.get("programs") or []
    return [p for p in programs if isinstance(p, dict) and p.get("launcher")]


def _launcher_path(entry: dict[str, Any]) -> Path | None:
    rel = entry.get("launcher") or ""
    if not rel:
        return None
    source = entry.get("source", "local")
    launcher_key = entry.get("launcher") or rel
    if source == "javis":
        fallback = _LOCAL_BAT_FALLBACKS.get(launcher_key)
        if fallback:
            local = _ROOT / fallback
            if local.is_file():
                return local
        path = JARVIS_ROOT / rel
        if path.is_file():
            return path
        if fallback:
            return local if local.is_file() else None
        return None
    path = _ROOT / rel
    return path if path.is_file() else None


def _bridge_health() -> dict[str, Any]:
    port = int(os.environ.get("CANON_AUTOBLOG_PORT", "8790"))
    try:
        import urllib.request

        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/javis/health", timeout=1) as resp:
            resp.read()
        return {"ok": True, "port": port, "detail": "Autoblog 브리지 실행 중"}
    except Exception:
        return {"ok": False, "port": port, "detail": "Autoblog GUI 미실행 (run_gui.bat)"}


def _filter_workspace(programs: list[dict[str, Any]], workspace: str | None) -> list[dict[str, Any]]:
    ws = (workspace or "all").strip().lower()
    if ws in ("", "all"):
        return programs
    return [p for p in programs if (p.get("workspace") or "").lower() == ws]


def _venv_ready() -> bool:
    return (_ROOT / ".venv" / "Scripts" / "python.exe").is_file()


def _effective_runtime(entry: dict[str, Any], path: Path | None, on_cloud: bool) -> str:
    from javis_serverless import resolve_cloud_action

    action = resolve_cloud_action(entry)
    if action == "local_hint":
        return "local_only"
    if path and _can_run_local_bat(path) and not on_cloud:
        return "local"
    if action and action != "local_hint":
        return "cloud"
    return "local" if path else "local_only"


def get_catalog(*, workspace: str | None = None) -> dict[str, Any]:
    programs = _load_catalog_programs()
    programs = _filter_workspace(programs, workspace)

    on_cloud = is_cloud_hub() or sys.platform != "win32" or str(JARVIS_ROOT).startswith("/app")
    items = []
    for entry in programs:
        path = _launcher_path(entry)
        cloud_action = _default_cloud_action(entry)
        runtime = _effective_runtime(entry, path, on_cloud)
        local_ok = path is not None
        cloud_ok = cloud_action is not None and cloud_action not in ("local_hint",)
        if on_cloud:
            available = bool(cloud_ok or cloud_action == "local_hint")
        else:
            available = local_ok or bool(cloud_ok)
        items.append({
            **entry,
            "category_label": CATEGORIES.get(entry.get("category", ""), entry.get("category", "")),
            "available": available,
            "runtime": runtime,
            "cloud_action": cloud_action,
            "launcher_path": str(path) if path else None,
        })

    bundled = (_ROOT / "javis").is_dir()
    meta = _load_catalog_raw()
    return {
        "workspace": workspace or "all",
        "jarvis_root": str(JARVIS_ROOT),
        "jarvis_installed": JARVIS_ROOT.is_dir() and any(JARVIS_ROOT.glob("run_*.bat")),
        "jarvis_bundled": bundled,
        "jarvis_remote": meta.get("jarvis_remote", "https://github.com/FatihMakes/Mark-XXXIX.git"),
        "catalog_path": str(_CATALOG_PATH),
        "catalog_count": len(_load_catalog_programs()),
        "categories": CATEGORIES,
        "programs": items,
        "bridge": _bridge_health(),
        "cloud_mode": on_cloud,
        "local_hub": not on_cloud and sys.platform == "win32",
        "venv_ready": _venv_ready(),
        "setup_hint": (
            "run_install.bat 실행 후 run.bat 으로 http://127.0.0.1:5000 을 여세요."
            if not _venv_ready() and not on_cloud
            else (
                "Cloudtype·Vercel — bat은 PC에서만 실행됩니다. "
                "「클라우드 실행」은 순위·SEO·블로그 초안 생성입니다. "
                "실제 네이버 발행: PC에서 run_gui.bat"
                if on_cloud
                else "로컬 허브 — 실행 버튼이 PC의 run_*.bat 을 엽니다."
            )
        ),
        "cloud_programs": sum(1 for p in items if p.get("runtime") == "cloud"),
        "traffic_count": sum(1 for p in items if p.get("workspace") == "traffic"),
        "javis_count": sum(1 for p in items if p.get("workspace") == "javis"),
    }



def _can_run_local_bat(path: Path | None) -> bool:
    """Windows PC 로컬 허브에서만 .bat 직접 실행."""
    return (
        not is_cloud_hub()
        and sys.platform == "win32"
        and path is not None
        and path.is_file()
        and path.suffix.lower() == ".bat"
    )


def _default_cloud_action(entry: dict[str, Any]) -> str:
    action = resolve_cloud_action(entry)
    if action:
        return action
    ws = (entry.get("workspace") or "").lower()
    if ws == "javis":
        return "javis_proxy"
    if ws == "traffic":
        return "hub_status"
    return "programs_check"


def _must_use_serverless(path: Path | None) -> bool:
    """Cloudtype·Vercel·Linux — .bat 대신 서버 액션. Windows 로컬 PC만 bat."""
    if is_cloud_hub():
        return True
    if sys.platform != "win32":
        return True
    if path is None:
        return True
    if path.suffix.lower() == ".bat":
        return not path.is_file()
    return True


def launch_program(program_id: str, *, logger: Callable[[str], None] | None = None) -> dict[str, Any]:
    program_id = PROGRAM_ID_ALIASES.get(program_id, program_id)
    programs = _load_catalog_programs()
    entry = next((p for p in programs if p["id"] == program_id), None)
    if not entry:
        return {"success": False, "error": "알 수 없는 프로그램 ID"}

    path = _launcher_path(entry)
    log = logger or (lambda _m: None)

    if _must_use_serverless(path) or not _can_run_local_bat(path):
        return run_serverless_program(program_id, entry, log)

    cwd = path.parent
    try:
        subprocess.Popen(
            ["cmd", "/c", "start", "", str(path)],
            cwd=str(cwd),
            creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP,
            close_fds=True,
        )
    except OSError as exc:
        log(f"로컬 bat 실행 실패 → 클라우드 대체: {exc}")
        return run_serverless_program(program_id, entry, log)
    return {
        "success": True,
        "message": f"{entry['name']} 실행 요청됨 (PC)",
        "launcher": str(path),
        "workspace": entry.get("workspace"),
    }
