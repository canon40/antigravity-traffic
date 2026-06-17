"""Vercel 서버리스용 초단기 트래픽 세션 (HTTP 방문, 10초 이내)."""

from __future__ import annotations

import re
import time
from typing import Any

import httpx

MOBILE_USER_AGENT = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 "
    "Mobile/15E148 Safari/604.1"
)

DEFAULT_TIMEOUT_SEC = 8.0


def _extract_title(html: str) -> str:
    match = re.search(r"<title[^>]*>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
    if not match:
        return ""
    return re.sub(r"\s+", " ", match.group(1)).strip()[:200]


def run_traffic_session(target_url: str, timeout_sec: float = DEFAULT_TIMEOUT_SEC) -> dict[str, Any]:
    """
    대상 URL에 모바일 브라우저처럼 짧게 1회 방문합니다.
    Vercel 무료 플랜(최대 10초) 안에 끝나도록 HTTP 기반으로만 동작합니다.
    """
    if not target_url or not target_url.startswith(("http://", "https://")):
        raise ValueError("target_url은 http:// 또는 https:// 로 시작해야 합니다.")

    started = time.perf_counter()
    headers = {
        "User-Agent": MOBILE_USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
        "Referer": "https://m.naver.com/",
        "Cache-Control": "no-cache",
    }

    with httpx.Client(follow_redirects=True, timeout=timeout_sec) as client:
        response = client.get(target_url, headers=headers)

    elapsed = round(time.perf_counter() - started, 2)
    body_preview = response.text[:500] if response.text else ""
    retry_after_sec = None
    ra = response.headers.get("Retry-After")
    if ra and str(ra).strip().isdigit():
        retry_after_sec = int(str(ra).strip())

    return {
        "status_code": response.status_code,
        "final_url": str(response.url),
        "elapsed_sec": elapsed,
        "title": _extract_title(response.text or ""),
        "content_length": len(response.content),
        "ok": 200 <= response.status_code < 400,
        "preview": body_preview,
        "retry_after_sec": retry_after_sec,
    }
