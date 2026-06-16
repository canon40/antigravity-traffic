# -*- coding: utf-8 -*-
"""네이버 쇼핑 SEO 가이드(RAG) + 키워드 DB 기반 마케팅 자산 생성."""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import Any, Callable

import config as cfg
from store_supabase import fetch_keywords

_BASE_DIR = Path(__file__).resolve().parent
_GUIDELINE_PATH = _BASE_DIR / "docs" / "naver_shopping_seo.txt"
_STORE_MODEL = os.environ.get("STORE_GEMINI_MODEL", "gemini-2.5-flash")

try:
    from google.genai import Client as GenAIClient
    from google.genai import types as genai_types

    _GENAI_OK = True
except ImportError:
    _GENAI_OK = False


def load_naver_guidelines() -> str:
    if _GUIDELINE_PATH.exists():
        return _GUIDELINE_PATH.read_text(encoding="utf-8")
    return (
        "상품명은 50자 내외, 브랜드명 앞 배치, 키워드 중복·특수문자 남용 금지. "
        "태그는 카테고리 매칭 유효 태그 위주 10개."
    )


def _api_key(explicit: str | None = None) -> str:
    return (
        (explicit or "").strip()
        or os.environ.get("GEMINI_API_KEY", "").strip()
        or os.environ.get("GOOGLE_API_KEY", "").strip()
        or getattr(cfg, "GEMINI_API_KEY", "").strip()
        or getattr(cfg, "GOOGLE_API_KEY", "").strip()
    )


def _format_keywords(keywords_data: list[dict[str, Any]]) -> str:
    if not keywords_data:
        return "(수집된 키워드 없음 — 상품 컨셉과 카테고리만으로 생성)"
    lines = []
    for k in keywords_data:
        lines.append(
            f"- {k.get('keyword', '')} "
            f"(월간검색량: {k.get('monthly_search_volume', '?')}, "
            f"경쟁도: {k.get('competition_index', '?')})"
        )
    return "\n".join(lines)


def _extract_text(res) -> str:
    if res is None:
        return ""
    text = getattr(res, "text", None)
    if text:
        return str(text).strip()
    parts = []
    for cand in getattr(res, "candidates", None) or []:
        content = getattr(cand, "content", None)
        if not content:
            continue
        for part in getattr(content, "parts", None) or []:
            t = getattr(part, "text", None)
            if t:
                parts.append(t)
    return "\n".join(parts).strip()


async def generate_store_assets(
    product_concept: str,
    category: str,
    *,
    api_key: str | None = None,
    keywords_override: list[dict[str, Any]] | None = None,
    log_fn: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    """
    상품명 3안, 태그 10개, 오프닝 카피 생성.
    Returns: {ok, text, tags_for_blog?, error?}
    """
    concept = (product_concept or "").strip()
    cat = (category or "").strip()
    if not concept:
        return {"ok": False, "error": "상품 컨셉이 비어 있습니다."}
    if not cat:
        return {"ok": False, "error": "카테고리가 비어 있습니다."}

    key = _api_key(api_key)
    if not key:
        return {"ok": False, "error": "Gemini API 키가 없습니다. 설정 탭에서 키를 입력하세요."}
    if not _GENAI_OK:
        return {"ok": False, "error": "google-genai 패키지가 필요합니다. pip install google-genai"}

    if log_fn:
        log_fn("[에이전트] 키워드·가이드라인 로드 중...")

    keywords_data = keywords_override if keywords_override is not None else fetch_keywords(cat, limit=10)
    seo_guidelines = load_naver_guidelines()
    keywords_str = _format_keywords(keywords_data)

    system_instruction = (
        "당신은 네이버 스마트스토어 상위 노출 전문 마케팅 컨설턴트입니다. "
        "제공된 네이버 쇼핑 가이드라인을 절대적으로 준수합니다. "
        "가이드 위반 상품명·중복 키워드·금지 표현은 포함하지 않습니다."
    )

    user_prompt = f"""
[참조: 네이버 쇼핑 가이드라인]
{seo_guidelines}

[수집된 시장 키워드 데이터]
{keywords_str}

[내 상품 컨셉]
{concept}

[카테고리]
{cat}

위 자료를 바탕으로 다음을 한국어로 작성하세요:

1. 네이버 SEO 규정에 부합하는 **최적 상품명 3개** (각 50자 내외)와 기획 의도
2. 태그 사전 등록 가능성이 높은 **유효 태그 10개** (쉼표로 구분한 한 줄도 마지막에 [TAGS] 블록으로)
3. 상세페이지 **오프닝 카피라이팅** 2~4문장

마지막 줄에 반드시 다음 형식을 추가하세요:
[TAGS] 태그1, 태그2, 태그3, ...
"""

    if log_fn:
        log_fn(f"[에이전트] Gemini({_STORE_MODEL}) 생성 요청...")

    client = GenAIClient(api_key=key)

    def _call():
        return client.models.generate_content(
            model=_STORE_MODEL,
            contents=user_prompt,
            config=genai_types.GenerateContentConfig(
                system_instruction=system_instruction,
                temperature=0.3,
            ),
        )

    try:
        res = await asyncio.to_thread(_call)
        text = _extract_text(res)
    except Exception as e:
        return {"ok": False, "error": str(e)}

    tags_line = ""
    for line in text.splitlines():
        if line.strip().upper().startswith("[TAGS]"):
            tags_line = line.split("]", 1)[-1].strip()
            break

    tags_for_blog = ", ".join(t.strip() for t in tags_line.split(",") if t.strip()) if tags_line else ""

    return {
        "ok": True,
        "text": text,
        "tags_for_blog": tags_for_blog,
        "keywords_used": keywords_data,
    }


def parse_tags_from_report(text: str) -> str:
    """리포트 텍스트에서 [TAGS] 줄 추출."""
    for line in (text or "").splitlines():
        if line.strip().upper().startswith("[TAGS]"):
            return line.split("]", 1)[-1].strip()
    return ""
