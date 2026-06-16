# -*- coding: utf-8 -*-
"""웹·네이버 검색 컨텍스트 수집 (Super Agent 리서치 단계)."""

from __future__ import annotations

import re
from urllib.parse import quote_plus

import httpx

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
}


async def fetch_duckduckgo_snippets(query: str, *, limit: int = 6) -> str:
    """DuckDuckGo HTML 검색 (API 키 불필요)."""
    q = quote_plus(query)
    url = f"https://html.duckduckgo.com/html/?q={q}"
    try:
        async with httpx.AsyncClient(timeout=25.0, follow_redirects=True) as client:
            res = await client.get(url, headers=_HEADERS)
            res.raise_for_status()
            html = res.text
    except Exception as e:
        return f"(웹 검색 실패: {e})"

    titles = re.findall(r'class="result__a"[^>]*>([^<]+)<', html)
    snippets = re.findall(r'class="result__snippet"[^>]*>([^<]+)<', html)
    lines: list[str] = []
    for i in range(min(limit, len(titles))):
        t = re.sub(r"\s+", " ", titles[i]).strip()
        s = re.sub(r"\s+", " ", snippets[i]).strip() if i < len(snippets) else ""
        lines.append(f"- {t}" + (f" | {s}" if s else ""))
    if not lines:
        return "(웹 검색 결과 없음)"
    return "【웹 검색 참고】\n" + "\n".join(lines)


async def gather_research_context(
    topics: list[str],
    *,
    use_naver: bool = True,
    use_web: bool = True,
) -> str:
    from content_factory.naver_context import fetch_blog_snippets

    parts: list[str] = []
    for topic in topics:
        topic = (topic or "").strip()
        if not topic:
            continue
        parts.append(f"\n### 주제: {topic}")
        if use_web:
            parts.append(await fetch_duckduckgo_snippets(topic))
        if use_naver:
            parts.append(await fetch_blog_snippets(topic))
    return "\n".join(parts).strip()
