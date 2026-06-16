# -*- coding: utf-8 -*-
"""JARVIS·로컬 프로그램 카탈로그 및 안전 실행."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parent
JARVIS_ROOT = Path(os.environ.get("JARVIS_ROOT", r"D:\@code\javis"))

CATEGORIES: dict[str, str] = {
    "seo": "SEO · 순위",
    "blog": "블로그 · 콘텐츠",
    "video": "영상 · 숏츠",
    "studio": "스튜디오 · 상세페이지",
    "agent": "JARVIS 에이전트",
    "ops": "연동 · 점검",
}

# source: local = anty traffic 루트 bat, javis = JARVIS_ROOT bat
PROGRAMS: list[dict[str, Any]] = [
    {
        "id": "web_hub",
        "name": "웹 SEO 허브 (현재)",
        "category": "seo",
        "source": "local",
        "launcher": "run.bat",
        "description": "순위 추적·SEO·블로그·JARVIS 런처 PWA 대시보드",
        "icon": "fa-gauge-high",
    },
    {
        "id": "autoblog_gui",
        "name": "Autoblog GUI",
        "category": "blog",
        "source": "local",
        "launcher": "run_gui.bat",
        "description": "네이버·티스토리 블로그 자동화 데스크톱 GUI",
        "icon": "fa-window-maximize",
    },
    {
        "id": "seo_pipeline",
        "name": "SEO 파이프라인",
        "category": "seo",
        "source": "local",
        "launcher": "run_seo_pipeline.bat",
        "description": "키워드·순위·콘텐츠 일괄 SEO 작업",
        "icon": "fa-diagram-project",
    },
    {
        "id": "content_factory",
        "name": "콘텐츠 팩토리",
        "category": "blog",
        "source": "local",
        "launcher": "run_content_factory.bat",
        "description": "상품·블로그용 콘텐츠 생성 파이프라인",
        "icon": "fa-industry",
    },
    {
        "id": "shorts_local",
        "name": "숏츠 팩토리 (로컬)",
        "category": "video",
        "source": "local",
        "launcher": "run_shorts_factory.bat",
        "description": "쇼핑·숏츠 영상 제작 (로컬 연동)",
        "icon": "fa-film",
    },
    {
        "id": "javis_connect",
        "name": "JARVIS 연동 점검",
        "category": "ops",
        "source": "local",
        "launcher": "run_javis_connect.bat",
        "description": "Supabase·환경변수 동기화 및 연결 확인",
        "icon": "fa-plug",
    },
    {
        "id": "programs_check",
        "name": "프로그램 점검",
        "category": "ops",
        "source": "local",
        "launcher": "run_programs_check.bat",
        "description": "Python·Ollama·Playwright·브리지 순차 점검",
        "icon": "fa-stethoscope",
    },
    {
        "id": "jarvis_ui",
        "name": "JARVIS UI v3",
        "category": "agent",
        "source": "javis",
        "launcher": "run_jarvis_ui_v3.bat",
        "description": "JARVIS 메인 Qt/Streamlit 통합 UI",
        "icon": "fa-robot",
    },
    {
        "id": "jarvis_video",
        "name": "동영상 스튜디오",
        "category": "video",
        "source": "javis",
        "launcher": "run_video_studio.bat",
        "description": "JARVIS 영상 제작·편집 스튜디오",
        "icon": "fa-video",
    },
    {
        "id": "jarvis_detail",
        "name": "상세페이지 스튜디오",
        "category": "studio",
        "source": "javis",
        "launcher": "run_detail_page_studio.bat",
        "description": "스마트스토어 상세페이지 AI 스튜디오",
        "icon": "fa-store",
    },
    {
        "id": "jarvis_shorts",
        "name": "숏츠 팩토리 (JARVIS)",
        "category": "video",
        "source": "javis",
        "launcher": "run_shorts_factory.bat",
        "description": "JARVIS 숏츠·쇼핑 영상 자동화",
        "icon": "fa-clapperboard",
    },
    {
        "id": "jarvis_blog",
        "name": "블로그 자동 (JARVIS)",
        "category": "blog",
        "source": "javis",
        "launcher": "run_블로그_자동.bat",
        "description": "JARVIS 블로그 자동 발행 파이프라인",
        "icon": "fa-blog",
    },
    {
        "id": "jarvis_workspace",
        "name": "워크스페이스",
        "category": "agent",
        "source": "javis",
        "launcher": "run_workspace.bat",
        "description": "JARVIS 멀티 에이전트 워크스페이스",
        "icon": "fa-sitemap",
    },
    {
        "id": "jarvis_unified",
        "name": "통합 스튜디오",
        "category": "studio",
        "source": "javis",
        "launcher": "run_unified_studio.bat",
        "description": "영상·이미지·콘텐츠 통합 스튜디오",
        "icon": "fa-cubes",
    },
    {
        "id": "jarvis_naver",
        "name": "네이버 하이브리드",
        "category": "seo",
        "source": "javis",
        "launcher": "run_naver_hybrid.bat",
        "description": "네이버 SEO·수익 하이브리드 파이프라인",
        "icon": "fa-n",
    },
    {
        "id": "jarvis_boot",
        "name": "JARVIS 바로시작",
        "category": "agent",
        "source": "javis",
        "launcher": "run_바로시작.bat",
        "description": "JARVIS 핵심 모듈 빠른 기동",
        "icon": "fa-bolt",
    },
]


def _launcher_path(entry: dict[str, Any]) -> Path | None:
    rel = entry.get("launcher") or ""
    if not rel:
        return None
    base = _ROOT if entry.get("source") == "local" else JARVIS_ROOT
    path = base / rel
    return path if path.is_file() else None


def _bridge_health() -> dict[str, Any]:
    port = int(os.environ.get("CANON_AUTOBLOG_PORT", "8790"))
    try:
        import urllib.request

        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/javis/health", timeout=1) as resp:
            data = resp.read().decode("utf-8")
        return {"ok": True, "port": port, "detail": "Autoblog 브리지 실행 중"}
    except Exception:
        return {"ok": False, "port": port, "detail": "Autoblog GUI 미실행 (run_gui.bat)"}


def get_catalog() -> dict[str, Any]:
    items = []
    for entry in PROGRAMS:
        path = _launcher_path(entry)
        items.append({
            **entry,
            "category_label": CATEGORIES.get(entry["category"], entry["category"]),
            "available": path is not None,
            "launcher_path": str(path) if path else None,
        })
    return {
        "jarvis_root": str(JARVIS_ROOT),
        "jarvis_installed": JARVIS_ROOT.is_dir(),
        "categories": CATEGORIES,
        "programs": items,
        "bridge": _bridge_health(),
    }


def launch_program(program_id: str) -> dict[str, Any]:
    entry = next((p for p in PROGRAMS if p["id"] == program_id), None)
    if not entry:
        return {"success": False, "error": "알 수 없는 프로그램 ID"}
    path = _launcher_path(entry)
    if not path:
        root = _ROOT if entry.get("source") == "local" else JARVIS_ROOT
        return {
            "success": False,
            "error": f"실행 파일 없음: {entry.get('launcher')} ({root})",
        }
    cwd = path.parent
    if sys.platform == "win32":
        subprocess.Popen(
            ["cmd", "/c", "start", "", str(path)],
            cwd=str(cwd),
            creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP,
            close_fds=True,
        )
    else:
        subprocess.Popen([str(path)], cwd=str(cwd), start_new_session=True)
    return {
        "success": True,
        "message": f"{entry['name']} 실행 요청됨",
        "launcher": str(path),
    }
