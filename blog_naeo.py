# -*- coding: utf-8 -*-
"""NAEO·AI 트렌드 블로그 — 영상 챕터 기반 고정 개요."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

NAEO_POST_TYPE = "NAEO·AI 트렌드"

_ROOT = Path(__file__).resolve().parent
_OUTLINE_PATH = _ROOT / "data" / "blog" / "naeo_outline.json"


@lru_cache(maxsize=1)
def load_naeo_config() -> dict:
    if not _OUTLINE_PATH.is_file():
        return {}
    try:
        return json.loads(_OUTLINE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def is_naeo_post_type(post_type: str) -> bool:
    return (post_type or "").strip() == NAEO_POST_TYPE


def default_keyword() -> str:
    return (load_naeo_config().get("default_keyword") or "NAEO").strip()


def default_title() -> str:
    return (
        load_naeo_config().get("default_title")
        or "블로그 유입이 이상한 이유 — SEO·AEO·GEO와 NAEO"
    ).strip()


def outline_markdown() -> str:
    """## 소제목 → 한 줄 설명 형식 개요."""
    cfg = load_naeo_config()
    lines: list[str] = []
    for ch in cfg.get("chapters") or []:
        ts = ch.get("timestamp") or ""
        head = ch.get("heading") or ""
        brief = ch.get("brief") or ""
        prefix = f"[{ts}] " if ts else ""
        lines.append(f"## {prefix}{head} → {brief}")
    return "\n".join(lines)


def outline_for_prompt() -> str:
    """LLM 프롬프트용 — 챕터 고정, 본문만 확장."""
    cfg = load_naeo_config()
    parts = [
        "【NAEO 글 — 소제목 고정】 아래 H2 순서와 제목을 바꾸지 말 것. 각 섹션 본문만 작성.",
        "",
    ]
    for ch in cfg.get("chapters") or []:
        ts = ch.get("timestamp") or ""
        head = ch.get("heading") or ""
        brief = ch.get("brief") or ""
        parts.append(f"- [{ts}] ## {head}")
        parts.append(f"  (다룰 내용: {brief})")
    parts.append("")
    for rule in cfg.get("writing_rules") or []:
        parts.append(f"- {rule}")
    ref = cfg.get("video_ref")
    if ref:
        parts.append(f"- 참고 영상: {ref}")
    return "\n".join(parts)


def template_outline(keyword: str = "") -> tuple[str, str, str]:
    """(title, outline, image_desc) — API 없이 즉시 사용."""
    cfg = load_naeo_config()
    title = default_title()
    outline = outline_markdown()
    img = (
        "Modern blogger analyzing traffic dashboard on laptop, AI search icons, "
        "clean office, photorealistic, no text"
    )
    return title, outline, img


def template_tags() -> str:
    tags = load_naeo_config().get("tags_hint") or []
    return ",".join(str(t) for t in tags[:10]) if tags else "NAEO,블로그,SEO,AEO,GEO"
