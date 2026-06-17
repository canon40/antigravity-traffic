# -*- coding: utf-8 -*-
"""
JARVIS 멀티 에이전트 — 작업 유형별 모델 우선순위 (LLM 호출 전 규칙만 결정).

Hermes(오케스트레이터) → Codex(코딩) / Gemma2(글쓰기) / DeepSeek(알고·이미지) 분업.
설정: drawer/agents.json → jarvis_model_routing
"""

from __future__ import annotations

import os
from functools import lru_cache
from typing import Any

_CODING_HINTS = (
    "codex",
    "코덱스",
    "코딩",
    "코드",
    "개발",
    "스크립트",
    "리팩터",
    "refactor",
    "debug",
    "디버그",
    "파일",
    "cursor",
    "implement",
    "구현",
)
_ALGO_HINTS = (
    "알고리즘",
    "수학",
    "algorithm",
    "math",
    "증명",
    "복잡도",
    "optimize",
    "최적화",
)
_IMAGE_GEN_HINTS = (
    "이미지 생성",
    "그림",
    "text-to-image",
    "t2i",
    "janus",
    "야누스",
    "멀티모달",
    "multimodal",
    "draw",
    "render",
)
_IMAGE_PROMPT_HINTS = (
    "이미지 프롬프트",
    "image prompt",
    "image_desc",
    "썸네일",
    "배너",
    "flux",
    "midjourney",
)
_CONTENT_HINTS = (
    "블로그",
    "글쓰기",
    "원고",
    "본문",
    "마케팅",
    "콘텐츠",
    "요약",
    "에세이",
    "포스팅",
    "blog",
    "outline",
    "body",
)
_ORCHESTRATION_HINTS = (
    "오케스트",
    "orchestrat",
    "분배",
    "라우팅",
    "route",
    "에이전트",
    "agent",
    "팀장",
    "hermes",
    "헤르메스",
    "openclaw",
    "오픈클로",
)
_ARCHITECTURE_HINTS = (
    "설계",
    "아키텍",
    "architecture",
    "loop",
    "감독",
    "수용 기준",
    "acceptance",
    "fable",
    "페이블",
    "비목표",
)
_DOCS_UI_HINTS = (
    "readme",
    "문서",
    "주석",
    "ui 문구",
    "마이크로카피",
    "버튼",
    "에러 메시지",
    "tooltip",
    "라벨",
)


def _routing_config() -> dict[str, Any]:
    try:
        from drawer.registry import agents_config

        return agents_config().get("jarvis_model_routing") or {}
    except Exception:
        return {}


@lru_cache(maxsize=1)
def _categories() -> dict[str, dict]:
    cfg = _routing_config()
    cats = cfg.get("task_categories") or {}
    if cats:
        return cats
    return _default_categories()


def _default_categories() -> dict[str, dict]:
    return {
        "orchestration": {
            "label": "종합 컨트롤러",
            "priority": ["openclaw", "hermes", "fable"],
            "role": "발화 분석·에이전트 업무 배분",
        },
        "architecture": {
            "label": "설계·LOOP 감독",
            "priority": ["fable", "hermes", "codex"],
            "role": "수용 기준·아키텍처 검토",
        },
        "coding": {
            "label": "개발·자동화",
            "priority": ["codex", "deepseek", "llama", "hermes"],
            "role": "프로젝트 코드·파일 자율 제어",
        },
        "algorithm": {
            "label": "알고리즘·수학",
            "priority": ["deepseek", "codex", "hermes"],
            "role": "복잡한 로직·디버깅",
        },
        "content": {
            "label": "블로그·글쓰기",
            "priority": ["gemma4", "gemma2", "hermes", "deepseek"],
            "role": "자연스러운 한글 본문·요약",
        },
        "docs_ui": {
            "label": "문서·UI 문구",
            "priority": ["gemma4", "hermes", "gemma2"],
            "role": "README·UI 마이크로카피",
        },
        "image_generate": {
            "label": "이미지 생성",
            "priority": ["deepseek_janus", "genai", "pollinations"],
            "role": "텍스트→이미지 파일",
        },
        "image_prompt": {
            "label": "이미지 프롬프트",
            "priority": ["hermes", "gemma2", "deepseek"],
            "role": "이미지 AI용 정교한 프롬프트",
        },
    }


@lru_cache(maxsize=1)
def _model_profiles() -> dict[str, dict]:
    cfg = _routing_config()
    profiles = cfg.get("model_profiles") or {}
    if profiles:
        return profiles
    return _default_model_profiles()


def _default_model_profiles() -> dict[str, dict]:
    return {
        "fable": {
            "label": "Claude Fable 5",
            "backend": "anthropic",
            "model_id": "claude-fable-5",
            "env": "BLOG_CLAUDE_MODEL",
            "heavy_tasks_only": True,
        },
        "openclaw": {
            "label": "OpenClaw",
            "backend": "openclaw",
            "external": True,
        },
        "hermes": {
            "label": "Hermes (Nous)",
            "backend": "ollama",
            "ollama_models": ["hermes3:latest", "hermes3:8b", "nous-hermes2:latest"],
            "env": "BLOG_ORCHESTRATOR_MODEL",
            "external": False,
        },
        "codex": {
            "label": "Codex / Cursor",
            "backend": "cursor",
            "external": True,
            "role": "Agentic coding in IDE",
        },
        "deepseek": {
            "label": "DeepSeek",
            "backend": "ollama",
            "ollama_models": ["deepseek-r1:8b", "deepseek-r1:1.5b", "deepseek-v3:latest"],
            "env": "BLOG_DEEPSEEK_MODEL",
        },
        "gemma4": {
            "label": "Gemma 4",
            "backend": "ollama",
            "ollama_models": ["gemma4:latest", "gemma4:e2b", "gemma4:31b"],
            "env": "BLOG_GEMMA4_MODEL",
        },
        "gemma2": {
            "label": "Gemma 2",
            "backend": "ollama",
            "ollama_models": ["gemma2:9b", "gemma2:9b-it", "gemma2:2b", "gemma2:latest"],
            "env": "BLOG_GEMMA_MODEL",
        },
        "llama": {
            "label": "Llama 3",
            "backend": "ollama",
            "ollama_models": ["llama3:latest", "llama3.1:latest", "llama3.2:latest"],
            "env": "BLOG_LLAMA_MODEL",
        },
        "deepseek_janus": {
            "label": "DeepSeek Janus",
            "backend": "ollama",
            "ollama_models": ["janus-pro", "janus", "deepseek-janus"],
            "note": "설치 시 멀티모달 T2I. 없으면 genai 폴백",
        },
        "genai": {
            "label": "Gemini Image",
            "backend": "gemini",
            "env_flag": "BLOG_IMAGE_PROVIDER=genai",
        },
        "pollinations": {
            "label": "Pollinations",
            "backend": "free",
            "env_flag": "BLOG_IMAGE_PROVIDER=free",
        },
    }


def jarvis_routing_enabled() -> bool:
    return os.environ.get("BLOG_JARVIS_MODEL_ROUTING", "0").strip().lower() not in (
        "0",
        "false",
        "no",
        "off",
    )


def route_task_category(payload: dict[str, Any] | None) -> str:
    """요청 → 작업 카테고리 (orchestration|coding|algorithm|content|image_generate|image_prompt)."""
    if not payload:
        return "content"

    explicit = (payload.get("task") or payload.get("task_category") or "").strip().lower()
    if explicit in _categories():
        return explicit

    action = " ".join(
        str(payload.get(k) or "")
        for k in ("action", "intent", "command", "topic", "keyword", "text", "module")
    ).lower()

    if any(h in action for h in _ORCHESTRATION_HINTS) or payload.get("orchestrate"):
        return "orchestration"
    if any(h in action for h in _ARCHITECTURE_HINTS) or payload.get("architecture"):
        return "architecture"
    if any(h in action for h in _CODING_HINTS) or payload.get("coding"):
        return "coding"
    if any(h in action for h in _DOCS_UI_HINTS) or payload.get("docs_ui"):
        return "docs_ui"
    if any(h in action for h in _ALGO_HINTS):
        return "algorithm"
    if any(h in action for h in _IMAGE_GEN_HINTS) or payload.get("image_generate"):
        return "image_generate"
    if any(h in action for h in _IMAGE_PROMPT_HINTS) or payload.get("image_prompt"):
        return "image_prompt"
    if payload.get("module") == "store":
        return "content"
    if any(h in action for h in _CONTENT_HINTS) or payload.get("keyword") or payload.get("post_type"):
        return "content"

    mod = (payload.get("module") or "").lower()
    if mod in ("blog", "wiki", "draft"):
        return "content"
    if mod == "store":
        return "content"

    return "content"


def model_priority_chain(task_category: str) -> list[str]:
    cat = _categories().get(task_category) or _categories().get("content", {})
    return list(cat.get("priority") or ["gemma2", "hermes", "deepseek"])


def _profile(model_id: str) -> dict:
    return _model_profiles().get(model_id) or {}


def ollama_candidates_for_task(task_category: str) -> list[str]:
    """설치된 Ollama 중 우선 시도할 모델 이름 후보 (순서 유지, 중복 제거)."""
    seen: set[str] = set()
    out: list[str] = []
    for mid in model_priority_chain(task_category):
        prof = _profile(mid)
        if prof.get("backend") != "ollama":
            continue
        for name in prof.get("ollama_models") or []:
            if name and name not in seen:
                seen.add(name)
                out.append(name)
    env_override = os.environ.get("BLOG_OLLAMA_MODEL", "").strip()
    if env_override and env_override not in seen:
        out.insert(0, env_override)
    return out


def resolve_primary_agent(task_category: str) -> dict[str, Any]:
    """1순위 에이전트 메타 (JARVIS/Codex용)."""
    chain = model_priority_chain(task_category)
    primary = chain[0] if chain else "gemma2"
    prof = _profile(primary)
    return {
        "agent_id": primary,
        "label": prof.get("label", primary),
        "backend": prof.get("backend", "unknown"),
        "external": bool(prof.get("external")),
        "role": (_categories().get(task_category) or {}).get("role", ""),
    }


def summarize_model_route(payload: dict[str, Any] | None) -> dict[str, Any]:
    """JARVIS HTTP / CLI용 전체 라우팅 요약."""
    task = route_task_category(payload)
    chain = model_priority_chain(task)
    primary = resolve_primary_agent(task)
    cat_meta = _categories().get(task) or {}

    return {
        "jarvis_model_routing": jarvis_routing_enabled(),
        "task_category": task,
        "task_label": cat_meta.get("label", task),
        "task_role": cat_meta.get("role", ""),
        "priority_chain": chain,
        "primary_agent": primary,
        "ollama_candidates": ollama_candidates_for_task(task),
        "architecture_table": architecture_summary(),
    }


def architecture_summary() -> list[dict[str, str]]:
    """사용자 문서용 요약 표."""
    rows = []
    for tid, cat in _categories().items():
        chain = cat.get("priority") or []
        agents = " > ".join(chain) if chain else "-"
        rows.append(
            {
                "category": cat.get("label", tid),
                "agents_priority": agents,
                "role": cat.get("role", ""),
            }
        )
    return rows


def match_installed_ollama(installed: set[str], candidates: list[str]) -> list[str]:
    """설치된 모델만 필터·별칭(:latest) 보정."""
    if not installed:
        return candidates[:]
    ordered: list[str] = []
    seen: set[str] = set()
    for name in candidates:
        if name in installed and name not in seen:
            ordered.append(name)
            seen.add(name)
            continue
        base = name.split(":")[0]
        for inst in installed:
            if inst.split(":")[0] == base and inst not in seen:
                ordered.append(inst)
                seen.add(inst)
                break
    return ordered
