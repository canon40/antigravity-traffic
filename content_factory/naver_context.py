# -*- coding: utf-8 -*-
"""네이버 블로그 검색 스니펫 (n8n AI 도구 대체 — 경량)."""

from __future__ import annotations

import re
from urllib.parse import quote_plus

import httpx


async def fetch_blog_snippets(query: str, *, limit: int = 5) -> str:
    """네이버 블로그 검색 상위 제목·요약을 프롬프트 컨텍스트로 반환."""
    q = quote_plus(query)
    url = f"https://search.naver.com/search.naver?where=blog&query={q}"
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
    }
    try:
        async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
            res = await client.get(url, headers=headers)
            res.raise_for_status()
            html = res.text
    except Exception as e:
        return f"(네이버 검색 실패: {e})"

    titles = re.findall(
        r'class="title_link"[^>]*>([^<]+)<',
        html,
    ) or re.findall(r'<a[^>]*class="[^"]*api_txt_lines[^"]*"[^>]*>([^<]+)<', html)
    descs = re.findall(r'class="dsc_link"[^>]*>([^<]+)<', html) or re.findall(
        r'class="api_txt_lines dsc_txt[^"]*"[^>]*>([^<]+)<', html
    )

    lines = []
    for i in range(min(limit, len(titles))):
        t = re.sub(r"\s+", " ", titles[i]).strip()
        d = re.sub(r"\s+", " ", descs[i]).strip() if i < len(descs) else ""
        lines.append(f"- {t}" + (f" | {d}" if d else ""))
    if not lines:
        return "(네이버 블로그 검색 결과 없음 — 일반 지식으로 작성)"
    return "【네이버 블로그 검색 참고】\n" + "\n".join(lines)
