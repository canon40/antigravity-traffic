# -*- coding: utf-8 -*-
"""경량 게이트웨이 — LLM 없이 키워드·필드로 모듈만 라우팅."""

from __future__ import annotations

import re
from typing import Any

from blog_constants import DRAWER_MODULES

_STORE_HINTS = ("store", "스마트스토어", "마케팅", "상품", "키워드크롤")
_NEIGHBOR_HINTS = ("neighbor", "서이추", "이웃", "서로이웃")
_VERIFY_HINTS = ("verify", "검증", "api", "연동확인")
_WIKI_HINTS = ("wiki", "지침", "guidelines", "마스터지침")
_BLOG_HINTS = ("blog", "블로그", "포스팅", "글쓰기", "naver", "티스토리", "tistory", "blogger")


def route_intent(payload: dict[str, Any] | None) -> str:
    """
    JARVIS/Codex HTTP·파일 트리거 → 서랍 모듈 ID.
    반환: blog | store | neighbor | verify | wiki | idle
    """
    if not payload:
        return "blog"

    explicit = (payload.get("module") or payload.get("drawer") or "").strip().lower()
    if explicit in DRAWER_MODULES:
        return explicit

    action = " ".join(
        str(payload.get(k) or "")
        for k in ("action", "intent", "command", "topic", "keyword", "text")
    ).lower()

    if any(h in action for h in _STORE_HINTS) or payload.get("store_category") or payload.get("concept"):
        return "store"
    if any(h in action for h in _NEIGHBOR_HINTS) or payload.get("neighbor"):
        return "neighbor"
    if any(h in action for h in _VERIFY_HINTS) or payload.get("verify_only"):
        return "verify"
    if any(h in action for h in _WIKI_HINTS) or payload.get("load_wiki"):
        return "wiki"
    if payload.get("keyword") or payload.get("keywords") or payload.get("post_type"):
        return "blog"
    if any(h in action for h in _BLOG_HINTS):
        return "blog"

    return "blog"


def route_text_provider(payload: dict[str, Any] | None, config: dict | None = None) -> str:
    """설정·환경에서 텍스트 엔진 하나만 선택 (동시 다중 엔진 방지)."""
    import os

    if payload and payload.get("text_provider"):
        raw = str(payload["text_provider"]).lower()
        if "ollama" in raw or "로컬" in raw:
            return "ollama"
        if "claude" in raw or "클로드" in raw:
            return "claude"
        if "gemini" in raw:
            return "gemini"

    if config and config.get("text_provider"):
        tp = str(config["text_provider"]).lower()
        if tp in ("ollama", "gemini", "claude", "auto"):
            return "ollama" if tp == "auto" else tp

    default = os.environ.get("BLOG_TEXT_PROVIDER", "ollama").strip().lower()
    if default == "auto":
        return "ollama"
    return default or "ollama"


def summarize_route(payload: dict[str, Any] | None, config: dict | None = None) -> dict[str, Any]:
    mod = route_intent(payload)
    provider = route_text_provider(payload, config)
    out: dict[str, Any] = {"module": mod, "text_provider": provider}
    try:
        from drawer.model_router import jarvis_routing_enabled, summarize_model_route

        if jarvis_routing_enabled():
            mr = summarize_model_route(payload)
            out["task_category"] = mr.get("task_category")
            out["model_priority"] = mr.get("priority_chain")
            out["primary_agent"] = (mr.get("primary_agent") or {}).get("agent_id")
    except Exception:
        pass
    return out
