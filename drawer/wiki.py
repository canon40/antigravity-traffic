# -*- coding: utf-8 -*-
"""
LLM Wiki 스타일 지침 로더 — 전체 마스터 지침을 메모리에 상주시키지 않고
작업 유형에 맞는 슬라이스만 디스크에서 읽어 합칩니다.
"""

from __future__ import annotations

import os
import re
from functools import lru_cache

_WIKI_ROOT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "wiki")

_POST_TYPE_SLICES = {
    "자동차 정보": "types/auto.md",
    "바이크 정보": "types/bike.md",
    "코팅제 정보": "types/coating.md",
    "제품 홍보": "types/living.md",
    "맛집/일상": "types/hobby_food.md",
    "취미글": "types/hobby_food.md",
    "정보성 팁": "types/tips.md",
    "NAEO·AI 트렌드": "types/naeo.md",
    "알림글": "types/notice.md",
    "자동(매번 랜덤)": "",
}


def wiki_enabled() -> bool:
    return os.environ.get("BLOG_USE_WIKI", "1").strip().lower() not in ("0", "false", "no", "off")


@lru_cache(maxsize=32)
def _read_slice(rel_path: str) -> str:
    if not rel_path:
        return ""
    path = os.path.join(_WIKI_ROOT, rel_path.replace("/", os.sep))
    if not os.path.isfile(path):
        return ""
    try:
        with open(path, encoding="utf-8") as f:
            return f.read().strip()
    except OSError:
        return ""


def list_slices() -> list[str]:
    out = []
    for root, _dirs, files in os.walk(_WIKI_ROOT):
        for name in files:
            if name.endswith(".md"):
                rel = os.path.relpath(os.path.join(root, name), _WIKI_ROOT)
                out.append(rel.replace("\\", "/"))
    return sorted(out)


def load_guidelines_for_task(
    post_type: str = "",
    *,
    user_master: str = "",
    extra: str = "",
    include_products: bool = True,
    max_chars: int = 12000,
) -> str:
    """
    작업에 필요한 지침만 조합.
    user_master가 있으면 Wiki 슬라이스는 보조(분량·Truth Table)로만 붙입니다.
    """
    if user_master and user_master.strip():
        base = user_master.strip()
        if not wiki_enabled():
            if extra:
                base += "\n\n[이번 작업 추가 지침]\n" + extra.strip()
            return base[:max_chars]

        parts = [base]
        core = _read_slice("00_core.md")
        if core and core not in base:
            parts.append("\n\n[Wiki 핵심]\n" + core)
        if include_products:
            prod = _read_slice("01_products_truth.md")
            if prod and "Truth Table" not in base:
                parts.append("\n\n[Wiki 제품 데이터]\n" + prod)
        mate = _read_slice("03_naver_mate.md")
        if mate and "메이트 5원칙" not in base:
            parts.append("\n\n[Wiki — 네이버 메이트]\n" + mate)
        pt = (post_type or "").strip()
        rel = _POST_TYPE_SLICES.get(pt, "")
        if rel:
            slice_text = _read_slice(rel)
            if slice_text:
                parts.append(f"\n\n[Wiki — {pt}]\n" + slice_text)
        if extra:
            parts.append("\n\n[이번 작업 추가 지침]\n" + extra.strip())
        return "\n".join(parts)[:max_chars]

    if not wiki_enabled():
        return _fallback_master_guidelines()

    chunks = []
    for rel in ("00_core.md", "01_products_truth.md", "02_post_types.md", "03_naver_mate.md"):
        t = _read_slice(rel)
        if t:
            chunks.append(t)
    pt = (post_type or "").strip()
    rel = _POST_TYPE_SLICES.get(pt, "")
    if rel:
        t = _read_slice(rel)
        if t:
            chunks.append(t)
    if extra:
        chunks.append("[이번 작업 추가 지침]\n" + extra.strip())

    combined = "\n\n".join(chunks).strip()
    if not combined:
        return _fallback_master_guidelines()
    return combined[:max_chars]


def _fallback_master_guidelines() -> str:
    """wiki/ 파일 없을 때만 content_gen 로드 (무거운 import 방지)."""
    core = _read_slice("00_core.md")
    if core:
        return core
    try:
        from drawer.registry import get_content_gen

        return get_content_gen().DEFAULT_MASTER_GUIDELINES
    except Exception:
        return "본문은 최소 1,500자 이상 작성합니다."


def load_default_master_guidelines() -> str:
    """GUI 지침 탭 기본값 — wiki 전체 또는 폴백."""
    if wiki_enabled():
        full = _read_slice("master_full.md")
        if full:
            return full
        parts = []
        for rel in ("00_core.md", "01_products_truth.md", "02_post_types.md", "03_naver_mate.md"):
            t = _read_slice(rel)
            if t:
                parts.append(t)
        if parts:
            return "\n\n".join(parts)
    return _fallback_master_guidelines()


def parse_min_chars_from_wiki() -> int | None:
    """wiki 슬라이스에서 최소 글자 수 추출."""
    text = "\n".join(_read_slice(p) for p in ("00_core.md", "master_full.md") if p)
    if not text:
        return None
    found = []
    for m in re.finditer(r"([\d]{1,2},?[\d]{3}|[\d]{3,5})\s*자\s*(?:이상|이상의)", text):
        try:
            n = int(m.group(1).replace(",", ""))
            if 200 <= n <= 20000:
                found.append(n)
        except ValueError:
            pass
    return max(found) if found else None
