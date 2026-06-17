# -*- coding: utf-8 -*-
"""Vercel(서버리스)에서 JARVIS·Traffic 프로그램 카탈로그 실행."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any, Callable

_ROOT = Path(__file__).resolve().parent

# 프로그램 ID → 클라우드 액션 (명시 매핑)
CLOUD_ACTION_BY_ID: dict[str, str] = {
    "traffic_web_hub": "hub_status",
    "traffic_rank_check": "track_now",
    "local_run_rank_check": "track_now",
    "traffic_seo_pipeline": "seo_pipeline",
    "traffic_content_factory": "content_generate",
    "traffic_javis_connect": "cloud_connect",
    "traffic_programs_check": "programs_check",
    "traffic_monitor_auto": "track_now",
    "traffic_autoblog_gui": "local_hint",
    "local_run_seo_hub_verify": "programs_check",
    "local_run_seo_hub": "hub_status",
    "javis_run_doctor": "programs_check",
    "javis_run_web_search": "keyword_analyze",
    "javis_run_naver_hybrid": "track_now",
    "javis_run_ai_briefing_seo": "content_generate",
    "javis_run_keyword_video": "content_generate",
    "javis_run_detail_page_studio": "content_generate",
    "javis_run_dashboard": "hub_status",
    "javis_run_블로그_전체": "blog_pipeline",
    "javis_run_블로그_자동": "blog_pipeline",
    "javis_run_blog_post": "blog_pipeline",
    "traffic_autoblog_gui": "blog_studio",
}


from hub_runtime import cloud_platform, is_cloud_hub


def is_vercel_runtime() -> bool:
    """클라우드 허브(Vercel·Cloudtype) — .bat 대신 서버 액션."""
    return is_cloud_hub()


def resolve_cloud_action(entry: dict[str, Any]) -> str | None:
    pid = (entry.get("id") or "").strip()
    if entry.get("cloud_action"):
        return str(entry["cloud_action"])
    if pid in CLOUD_ACTION_BY_ID:
        return CLOUD_ACTION_BY_ID[pid]

    launcher = (entry.get("launcher") or "").lower()
    cat = (entry.get("category") or "").lower()
    stem = launcher.replace("run_", "").replace(".bat", "")

    local_only_markers = (
        "gui",
        "playwright",
        "desktop",
        "mobile",
        "hermes",
        "lovable",
        "colab",
        "overnight",
        "tui",
        "install",
        "boot",
    )
    if any(m in stem for m in local_only_markers):
        return "local_hint"

    if cat == "seo" or any(k in stem for k in ("rank", "seo", "naver", "keyword", "hybrid")):
        return "track_now"
    if cat == "blog" or any(k in stem for k in ("blog", "briefing", "content", "detail", "블로그")):
        return "blog_pipeline" if "블로그" in stem or cat == "blog" else "content_generate"
    if cat == "video" or any(k in stem for k in ("video", "shorts", "youtube")):
        return "content_generate"
    if cat == "ops" or any(k in stem for k in ("check", "doctor", "connect", "sync", "verify")):
        return "programs_check"
    if entry.get("workspace") == "javis":
        return "javis_proxy"
    if entry.get("workspace") == "traffic":
        return "hub_status"
    return "javis_proxy"


def cloud_runtime(entry: dict[str, Any]) -> str:
    action = resolve_cloud_action(entry)
    if action and action != "local_hint":
        return "cloud"
    if is_vercel_runtime():
        return "local_only"
    return "local"


def _load_config_keywords() -> tuple[list[str], list[str]]:
    from rank_tracker import load_config

    cfg = load_config()
    return list(cfg.get("keywords") or []), list(cfg.get("priority_keywords") or [])


def _action_hub_status(entry: dict[str, Any], logger: Callable[[str], None]) -> dict[str, Any]:
    keywords, priority = _load_config_keywords()
    from rank_persistence import persistence_backend

    logger("☁️ SEO 허브 상태 확인")
    return {
        "action": "hub_status",
        "keywords": len(keywords),
        "priority_keywords": len(priority),
        "persistence": persistence_backend(),
        "program": entry.get("name"),
    }


def _action_track_now(entry: dict[str, Any], logger: Callable[[str], None]) -> dict[str, Any]:
    from rank_tracker import build_completion_report, track_all_keywords

    logger(f"☁️ 클라우드 순위 추적: {entry.get('name')}")
    try:
        results = track_all_keywords(logger=logger, serverless=True, keyword_batch_size=4)
        report = build_completion_report(results)
        return {"action": "track_now", "report": report, "tracked": len(results)}
    except Exception as exc:
        logger(f"⚠️ 순위 추적 일부 실패: {exc}")
        return {"action": "track_now", "warning": str(exc), "tracked": 0}


def _action_seo_pipeline(entry: dict[str, Any], logger: Callable[[str], None]) -> dict[str, Any]:
    from rank_tracker import build_completion_report, track_all_keywords
    from seo_checker import run_full_audit

    logger("☁️ SEO 파이프라인 (순위 + 체크리스트)")
    report = {"summary": "순위 추적 생략"}
    tracked = 0
    try:
        results = track_all_keywords(logger=logger, serverless=True, keyword_batch_size=6)
        report = build_completion_report(results)
        tracked = len(results)
    except Exception as exc:
        logger(f"⚠️ 순위 추적 생략: {exc}")
    audit = run_full_audit(logger=logger, product_limit=3)
    return {
        "action": "seo_pipeline",
        "report": report,
        "audit_summary": audit.get("summary"),
        "tracked": tracked,
    }


def _first_blog_keyword() -> str:
    keywords, priority = _load_config_keywords()
    if priority:
        if isinstance(priority[0], dict):
            return (priority[0].get("keyword") or "").strip() or "나눔랩 코팅"
        return str(priority[0]).strip()
    if keywords:
        if isinstance(keywords[0], dict):
            return (keywords[0].get("keyword") or "").strip() or "나눔랩 코팅"
        return str(keywords[0]).strip()
    try:
        from hub_accounts import keywords_from_accounts

        acc = keywords_from_accounts()
        if acc:
            return acc[0]
    except Exception:
        pass
    return "나눔랩 코팅"


def _action_blog_studio(entry: dict[str, Any], logger: Callable[[str], None]) -> dict[str, Any]:
    logger(f"☁️ 블로그 스튜디오: {entry.get('name')}")
    return {
        "action": "blog_studio",
        "url": "/blog-studio/",
        "message": "블로그 탭(스튜디오)에서 키워드 입력 후 실행하세요. PC에서는 run_gui.bat도 사용할 수 있습니다.",
    }


def _action_blog_pipeline(entry: dict[str, Any], logger: Callable[[str], None]) -> dict[str, Any]:
    """클라우드·로컬 공통 — 블로그 파이프라인 또는 PC 트리거."""
    keyword = _first_blog_keyword()
    publish = "전체" in (entry.get("name") or "") or "전체" in (entry.get("launcher") or "")
    payload = {
        "keyword": keyword,
        "dry_run": not publish,
        "skip_media": not publish,
        "platforms": ["tistory", "naver"],
        "publish": publish,
        "source": entry.get("id"),
    }
    logger(f"☁️ 블로그 파이프라인: {keyword[:60]} (발행={publish})")

    from hub_runtime import is_cloud_hub

    if not is_cloud_hub():
        try:
            from blog_studio_web import _start_async

            result = _start_async(payload)
            result["action"] = "blog_pipeline"
            result["keyword"] = keyword
            return result
        except Exception as exc:
            logger(f"블로그 파이프라인: {exc}")

    trigger_path = ""
    try:
        from javis_bridge import write_file_trigger

        trigger_path = write_file_trigger(payload)
        logger(f"PC 트리거 저장: {trigger_path}")
    except Exception as exc:
        logger(f"PC 트리거 실패: {exc}")

    if is_cloud_hub():
        payload_gen = _action_content_generate(entry, logger)
        payload_gen["action"] = "blog_pipeline"
        payload_gen["keyword"] = keyword
        payload_gen["message"] = (
            f"클라우드에서 블로그 초안을 생성했습니다 (키워드: {keyword}). "
            "PC에서 run_gui.bat 또는 run_블로그_전체.bat으로 발행하세요."
        )
        return payload_gen

    return {
        "action": "blog_pipeline",
        "triggered": bool(trigger_path),
        "trigger_path": trigger_path,
        "keyword": keyword,
        "message": (
            f"PC에 블로그 실행 요청을 넣었습니다 (키워드: {keyword}). "
            "run_gui.bat 또는 블로그 탭이 켜져 있으면 자동 시작됩니다."
        ),
    }


def _action_content_generate(entry: dict[str, Any], logger: Callable[[str], None]) -> dict[str, Any]:
    from seo_content_builder import generate_content, list_workflows, save_content

    workflows = list_workflows()
    workflow = "blog_review"
    if entry.get("category") == "blog":
        workflow = "blog_review"
    elif entry.get("category") == "video":
        workflow = "shorts_script"
    elif "detail" in (entry.get("launcher") or "").lower():
        workflow = "product_detail"

    keywords, priority = _load_config_keywords()
    keyword = _first_blog_keyword()
    logger(f"☁️ 콘텐츠 생성 ({workflow}): {keyword}")
    result = generate_content(workflow, keyword, product_name=keyword)
    if result.get("success"):
        try:
            result["saved_path"] = save_content(result)
        except OSError as exc:
            result["save_warning"] = str(exc)
    return {"action": "content_generate", "workflow": workflow, "result": result}


def _action_keyword_analyze(entry: dict[str, Any], logger: Callable[[str], None]) -> dict[str, Any]:
    from keyword_analyzer import analyze_all_products

    logger("☁️ 키워드·상품 분석")
    analysis = analyze_all_products()
    return {"action": "keyword_analyze", "analysis": analysis}


def _action_cloud_connect(entry: dict[str, Any], logger: Callable[[str], None]) -> dict[str, Any]:
    from rank_persistence import persistence_backend

    logger("☁️ JARVIS·Vercel 연동 점검")
    checks = []
    for name, ok, detail in (
        ("HUB_CLOUD", True, cloud_platform()),
        ("GEMINI_API_KEY", bool(os.environ.get("GEMINI_API_KEY", "").strip()), "set" if os.environ.get("GEMINI_API_KEY") else "missing"),
        ("SUPABASE_URL", bool(os.environ.get("SUPABASE_URL", "").strip()), "set" if os.environ.get("SUPABASE_URL") else "optional"),
        ("persistence", True, persistence_backend()),
    ):
        checks.append({"name": name, "ok": ok, "detail": str(detail)})

    catalog = _ROOT / "data" / "programs_catalog.json"
    checks.append({
        "name": "programs_catalog",
        "ok": catalog.is_file(),
        "detail": str(catalog) if catalog.is_file() else "missing",
    })
    return {"action": "cloud_connect", "checks": checks, "all_ok": all(c["ok"] for c in checks if c["name"] != "SUPABASE_URL")}


def _action_programs_check(entry: dict[str, Any], logger: Callable[[str], None]) -> dict[str, Any]:
    logger("☁️ 클라우드 프로그램 점검")
    steps: list[dict[str, Any]] = []

    def step(name: str, ok: bool, detail: str = "") -> None:
        steps.append({"name": name, "ok": ok, "detail": detail})

    step("Python", True, f"{sys.version_info.major}.{sys.version_info.minor}")
    try:
        from app import app  # noqa: F401

        step("Flask app", True)
    except Exception as exc:
        step("Flask app", False, str(exc)[:80])

    try:
        from rank_tracker import load_config

        cfg = load_config()
        kw = len(cfg.get("keywords") or [])
        step("config", kw > 0, f"keywords={kw}")
    except Exception as exc:
        step("config", False, str(exc)[:80])

    try:
        from rank_persistence import persistence_backend

        step("persistence", True, persistence_backend())
    except Exception as exc:
        step("persistence", False, str(exc)[:80])

    catalog = _ROOT / "data" / "programs_catalog.json"
    if catalog.is_file():
        try:
            data = json.loads(catalog.read_text(encoding="utf-8"))
            n = len(data.get("programs") or [])
            step("javis_catalog", n > 0, f"programs={n}")
        except Exception as exc:
            step("javis_catalog", False, str(exc)[:80])
    else:
        step("javis_catalog", False, "missing")

    required_ok = all(s["ok"] for s in steps if s["name"] in ("Flask app", "config", "javis_catalog"))
    return {"action": "programs_check", "steps": steps, "required_ok": required_ok}


def _action_local_hint(entry: dict[str, Any], logger: Callable[[str], None]) -> dict[str, Any]:
    logger(f"ℹ️ PC 전용: {entry.get('name')}")
    return {
        "action": "local_hint",
        "message": (
            f"「{entry.get('name')}」은 Windows·GUI·Playwright가 필요합니다. "
            "PC에서 run_gui.bat 또는 해당 run_*.bat을 실행하세요."
        ),
    }


def _action_javis_proxy(entry: dict[str, Any], logger: Callable[[str], None]) -> dict[str, Any]:
    """JARVIS bat — 카테고리별 클라우드 대체 실행."""
    cat = entry.get("category", "")
    if cat == "seo":
        action = "track_now"
    elif cat == "blog":
        action = "content_generate"
    elif cat == "video":
        action = "content_generate"
    elif cat == "ops":
        action = "programs_check"
    else:
        action = "hub_status"

    handler = _HANDLERS.get(action)
    if not handler:
        return {"action": "javis_proxy", "error": "no handler"}
    payload = handler(entry, logger)
    payload["proxied_from"] = entry.get("id")
    return payload


_HANDLERS: dict[str, Callable[..., dict[str, Any]]] = {
    "hub_status": _action_hub_status,
    "track_now": _action_track_now,
    "seo_pipeline": _action_seo_pipeline,
    "content_generate": _action_content_generate,
    "blog_pipeline": _action_blog_pipeline,
    "blog_studio": _action_blog_studio,
    "keyword_analyze": _action_keyword_analyze,
    "cloud_connect": _action_cloud_connect,
    "programs_check": _action_programs_check,
    "local_hint": _action_local_hint,
    "javis_proxy": _action_javis_proxy,
}


def run_serverless_program(
    program_id: str,
    entry: dict[str, Any],
    logger: Callable[[str], None],
) -> dict[str, Any]:
    action = resolve_cloud_action(entry)
    if not action:
        return {
            "success": False,
            "error": "클라우드에서 실행할 수 없는 프로그램입니다. PC에서 run_*.bat을 사용하세요.",
            "program_id": program_id,
        }
    if action == "local_hint":
        payload = _action_local_hint(entry, logger)
        return {
            "success": True,
            "message": payload.get("message"),
            "cloud": True,
            "program_id": program_id,
            "result": payload,
        }
    if action == "blog_studio":
        payload = _action_blog_studio(entry, logger)
        return {
            "success": True,
            "message": payload.get("message"),
            "cloud": True,
            "program_id": program_id,
            "action": action,
            "studio_url": payload.get("url"),
            "result": payload,
        }
    if action == "javis_proxy":
        payload = _action_javis_proxy(entry, logger)
        return {
            "success": True,
            "message": f"☁️ {entry.get('name', program_id)} — 클라우드 프록시 실행 완료",
            "cloud": True,
            "program_id": program_id,
            "action": action,
            "result": payload,
        }

    handler = _HANDLERS.get(action)
    if not handler:
        return {"success": False, "error": f"알 수 없는 클라우드 액션: {action}"}

    try:
        payload = handler(entry, logger)
        return {
            "success": True,
            "message": f"☁️ {entry.get('name', program_id)} — 클라우드 실행 완료 ({action})",
            "cloud": True,
            "program_id": program_id,
            "action": action,
            "result": payload,
        }
    except Exception as exc:
        return {
            "success": False,
            "error": str(exc),
            "cloud": True,
            "program_id": program_id,
            "action": action,
        }
