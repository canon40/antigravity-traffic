# -*- coding: utf-8 -*-
"""JARVIS 음성/HTTP → 상세페이지 스튜디오 (타사 벤치마크 · 분석 · HTML)."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any
from urllib.parse import quote

_ROOT = Path(__file__).resolve().parents[1]
SHORTS_DIR = _ROOT / "docs" / "shorts"
DEFAULT_PORT = 8766

_URL_RE = re.compile(r"https?://[^\s\)\]\"']+", re.I)

_BENCH_KW = ("타사", "벤치마크", "경쟁", "비교", "레퍼런스", "competitor", "benchmark")
_ANALYZE_KW = ("니즈", "후킹", "분석", "analyze", "전략")
_BUILD_KW = ("html", "HTML", "스마트스토어", "미리보기", "생성", "만들", "빌드", "build")
_OPEN_KW = ("열", "open", "스튜디오", "실행", "시작")
_FULL_KW = ("전체", "한번에", "파이프라인", "끝까지", "풀", "full", "pipeline")
_LIST_KW = ("목록", "프로젝트", "작업", "list")


def _extract_urls(text: str) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for m in _URL_RE.findall(text or ""):
        u = m.rstrip(".,;")
        if u not in seen:
            seen.add(u)
            out.append(u)
    return out[:5]


def _list_projects() -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    if not SHORTS_DIR.is_dir():
        return items
    for d in sorted(SHORTS_DIR.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
        if not d.is_dir():
            continue
        plan_path = d / "plan.json"
        if not plan_path.is_file():
            continue
        try:
            plan = json.loads(plan_path.read_text(encoding="utf-8"))
        except Exception:
            plan = {}
        items.append(
            {
                "slug": d.name,
                "topic": plan.get("topic") or plan.get("video_title") or d.name,
                "product_id": plan.get("product_id"),
                "detail_analyzed": bool((d / "detail_analysis.json").is_file()),
                "detail_ready": bool((d / "detail_preview.html").is_file()),
                "mtime": d.stat().st_mtime,
            }
        )
    return items


def _resolve_slug(payload: dict[str, Any]) -> str | None:
    slug = (payload.get("slug") or "").strip()
    if slug:
        return slug
    projects = _list_projects()
    if not projects:
        return None

    hints = " ".join(
        str(payload.get(k) or "")
        for k in ("keyword", "topic", "query", "text", "message", "command")
    ).lower()

    for p in projects:
        s = p["slug"].lower()
        t = str(p.get("topic") or "").lower()
        if hints and (s in hints or t and t in hints):
            return p["slug"]
        for token in re.split(r"[\s,]+", hints):
            if len(token) >= 3 and (token in s or token in t):
                return p["slug"]

    return projects[0]["slug"]


def detect_action(text: str, payload: dict[str, Any] | None = None) -> str:
    p = payload or {}
    explicit = (p.get("action") or p.get("intent") or "").strip().lower()
    if explicit in (
        "open",
        "benchmark",
        "analyze",
        "build",
        "pipeline",
        "full",
        "list",
        "help",
    ):
        return "pipeline" if explicit == "full" else explicit

    t = (text or "").strip()
    low = t.lower()
    if not t:
        return "open"
    if any(k in t for k in _LIST_KW):
        return "list"
    if any(k in low for k in _FULL_KW) or (
        any(k in t for k in _BENCH_KW)
        and any(k in low for k in _BUILD_KW)
    ):
        return "pipeline"
    if any(k in t for k in _BENCH_KW) or _extract_urls(t):
        return "benchmark"
    if any(k in t for k in _ANALYZE_KW):
        return "analyze"
    if any(k in low for k in _BUILD_KW):
        return "build"
    if any(k in t for k in _OPEN_KW):
        return "open"
    if "상세" in t and any(v in t for v in ("만들", "생성", "해")):
        return "pipeline"
    return "pipeline"


def voice_help() -> dict[str, Any]:
    return {
        "ok": True,
        "service": "loopreel_detail_studio",
        "port": DEFAULT_PORT,
        "examples": [
            "상세페이지 스튜디오 열어",
            "바이크 프로젝트 타사 분석 https://smartstore.naver.com/…",
            "니즈 후킹 분석해",
            "상세 HTML 만들어",
            "타사 분석부터 HTML까지 한번에",
        ],
        "actions": {
            "open": "브라우저에서 /detail/ 열기",
            "benchmark": "타사 URL 구조 분석",
            "analyze": "니즈·후킹 분석 저장",
            "build": "HTML 미리보기·스마트스토어 생성",
            "pipeline": "벤치마크→분석→HTML 순서 실행",
        },
    }


def _detail_url(slug: str | None = None) -> str:
    base = f"http://127.0.0.1:{DEFAULT_PORT}/detail/"
    if slug:
        return f"{base}?slug={quote(slug, safe='')}"
    return base


def _speech(action: str, result: dict[str, Any]) -> str:
    if not result.get("ok"):
        return result.get("speech") or result.get("error") or "상세페이지 작업에 실패했습니다."
    if action == "open":
        return result.get("speech") or "상세페이지 스튜디오를 열었습니다. 타사 URL을 넣고 분석을 시작하세요."
    if action == "list":
        n = len(result.get("projects") or [])
        return f"콘티가 있는 프로젝트 {n}개를 찾았습니다."
    if action == "benchmark":
        n = (result.get("benchmark") or {}).get("summary", {}).get("analyzed", 0)
        return f"타사 {n}건 벤치마크를 완료했습니다. 이제 니즈 분석을 실행하세요."
    if action == "analyze":
        return "니즈와 후킹 분석을 저장했습니다. HTML 생성 단계로 넘어가세요."
    if action == "build":
        return "상세페이지 HTML과 미리보기를 만들었습니다."
    if action == "pipeline":
        return result.get("speech") or "타사 분석부터 HTML 생성까지 완료했습니다."
    return result.get("message") or "완료했습니다."


def execute_action(action: str, payload: dict[str, Any]) -> dict[str, Any]:
    from shorts_factory.competitor_analyzer import (
        analyze_competitor_urls,
        load_competitor_benchmark,
        save_competitor_benchmark,
    )
    from shorts_factory.detail import write_detail_outputs
    from shorts_factory.detail_analyzer import analyze_detail_plan, save_analysis

    p = dict(payload or {})
    text = " ".join(str(p.get(k) or "") for k in ("text", "message", "command", "keyword", "topic")).strip()

    if action == "help":
        h = voice_help()
        h["speech"] = "상세페이지 스튜디오입니다. 타사 URL 분석, 니즈 분석, HTML 생성을 음성으로 요청할 수 있습니다."
        return h

    if action == "list":
        projects = _list_projects()
        return {
            "ok": True,
            "action": action,
            "projects": projects,
            "url": _detail_url(),
            "speech": _speech(action, {"ok": True, "projects": projects}),
        }

    if action == "open":
        slug = _resolve_slug(p)
        return {
            "ok": True,
            "action": action,
            "slug": slug,
            "url": _detail_url(slug),
            "open_browser": True,
            "speech": "상세페이지 스튜디오를 엽니다. 먼저 프로젝트를 고르고 타사 URL을 분석하세요.",
        }

    slug = _resolve_slug(p)
    if not slug:
        return {
            "ok": False,
            "action": action,
            "error": "콘티 프로젝트가 없습니다. 쇼츠 스튜디오에서 ① 콘티를 먼저 만드세요.",
            "speech": "콘티 작업이 없어서 상세페이지를 만들 수 없습니다. 쇼츠 스튜디오에서 콘티를 먼저 생성해 주세요.",
            "url": _detail_url(),
        }

    out_dir = SHORTS_DIR / slug
    plan_path = out_dir / "plan.json"
    if not plan_path.is_file():
        return {
            "ok": False,
            "action": action,
            "error": f"plan.json 없음: {slug}",
            "speech": "선택한 프로젝트에 콘티 파일이 없습니다.",
        }

    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    urls = p.get("competitor_urls") or p.get("competitorLinks") or p.get("urls")
    if isinstance(urls, str):
        urls = [u.strip() for u in urls.replace("\n", ",").split(",") if u.strip()]
    if not urls:
        urls = _extract_urls(text)
    notes = str(p.get("competitor_notes") or p.get("notes") or "")
    strategy = (p.get("strategy") or "").strip() or None
    selected_hook = (p.get("selected_hook") or "").strip() or None
    use_llm = bool(p.get("use_llm", False))

    result: dict[str, Any] = {
        "ok": True,
        "action": action,
        "slug": slug,
        "url": _detail_url(slug),
    }

    steps: list[str] = []

    if action in ("benchmark", "pipeline") and urls:
        benchmark = analyze_competitor_urls(list(urls))
        save_competitor_benchmark(out_dir, benchmark)
        result["benchmark"] = benchmark
        steps.append("benchmark")
        n = benchmark.get("summary", {}).get("analyzed", 0)
        if action == "benchmark":
            result["speech"] = f"{slug} 프로젝트, 타사 {n}건 분석을 마쳤습니다."
            return result

    if action in ("analyze", "pipeline"):
        benchmark = load_competitor_benchmark(out_dir)
        analysis = analyze_detail_plan(
            plan,
            strategy_override=strategy,
            competitor_notes=notes,
            competitor_benchmark=benchmark,
            selected_hook=selected_hook,
        )
        save_analysis(out_dir, analysis)
        plan = dict(plan)
        plan["detail_analyzed"] = True
        plan["detail_analysis_file"] = "detail_analysis.json"
        plan_path.write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
        result["analysis"] = analysis
        steps.append("analyze")
        if action == "analyze":
            result["speech"] = f"{slug} 니즈·후킹 분석을 저장했습니다."
            return result

    if action in ("build", "pipeline"):
        build = write_detail_outputs(
            plan,
            slug,
            out_dir,
            use_llm=use_llm,
            strategy=strategy,
            competitor_notes=notes,
            selected_hook=selected_hook,
        )
        if not build.get("ok"):
            return {
                "ok": False,
                "action": action,
                "slug": slug,
                "error": build.get("error") or "HTML 생성 실패",
                "speech": "HTML 생성에 실패했습니다.",
                "steps": steps,
            }
        result["detail"] = build.get("detail")
        result["preview_url"] = f"http://127.0.0.1:{DEFAULT_PORT}/{quote(slug, safe='')}/detail_preview.html"
        steps.append("build")
        result["steps"] = steps
        if action == "pipeline":
            parts = []
            if "benchmark" in steps:
                parts.append("타사 벤치마크")
            parts.extend(["니즈 분석", "HTML 생성"])
            result["speech"] = f"{slug} 상세페이지, {'와 '.join(parts)}까지 완료했습니다. 미리보기를 확인하세요."
        else:
            result["speech"] = f"{slug} 상세 HTML과 미리보기를 만들었습니다."
        result["open_browser"] = True
        return result

    if action == "benchmark" and not urls:
        return {
            "ok": False,
            "action": action,
            "slug": slug,
            "error": "타사 URL이 필요합니다.",
            "speech": "타사 분석을 하려면 스마트스토어 URL을 말씀하거나 입력해 주세요.",
            "url": _detail_url(slug),
        }

    result["speech"] = "요청을 처리했습니다."
    result["steps"] = steps
    return result


def handle_javis_start(payload: dict[str, Any] | None) -> dict[str, Any]:
    p = dict(payload or {})
    text = " ".join(
        str(p.get(k) or "")
        for k in ("text", "message", "command", "keyword", "topic", "query")
    ).strip()
    action = detect_action(text, p)
    result = execute_action(action, p)
    if "speech" not in result:
        result["speech"] = _speech(action, result)
    result["detected_action"] = action
    result["service"] = "loopreel_detail_studio"
    return result
