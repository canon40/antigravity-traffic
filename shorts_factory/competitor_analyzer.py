# -*- coding: utf-8 -*-
"""타사·자사 상세페이지 URL 수집·구조 분석 (로컬, API 없음)."""

from __future__ import annotations

import json
import re
import ssl
import time
from html import unescape
from html.parser import HTMLParser
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse, urlunparse
from urllib.request import Request, urlopen

_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36 LoopReel/1.1"
)
_FETCH_TIMEOUT = 22
_MAX_BYTES = 1_500_000
_FETCH_HINT = (
    "네이버가 자동 수집을 차단(429)했습니다. 브라우저에서 해당 URL을 연 뒤 "
    "상세 영역 텍스트를 복사해 「수동 붙여넣기」에 넣으면 분석됩니다."
)

SECTION_DEFS: list[dict[str, Any]] = [
    {"id": "hero", "label": "히어로·한줄 정의", "keywords": ("대표", "히어로", "한줄", "메인", "headline", "og:title")},
    {"id": "pain", "label": "문제·Pain", "keywords": ("고민", "불편", "문제", "번거", "왜", "아직도", "stress", "pain")},
    {"id": "before_after", "label": "전후·B&A", "keywords": ("전후", "비포", "애프터", "before", "after", "b&a", "변화", "비교")},
    {"id": "usp", "label": "USP·스펙", "keywords": ("특장", "usp", "스펙", "함량", "성능", "차별", "원액", "%", "기능")},
    {"id": "howto", "label": "시공·사용법", "keywords": ("시공", "사용법", "도포", "단계", "방법", "how to", "가이드", "꿀팁")},
    {"id": "components", "label": "구성·라인업", "keywords": ("구성", "구성품", "라인업", "세트", "옵션", "variant")},
    {"id": "reviews", "label": "후기·리뷰", "keywords": ("후기", "리뷰", "review", "평점", "별점", "구매자")},
    {"id": "faq", "label": "FAQ·Q&A", "keywords": ("faq", "q&a", "질문", "답변", "문의", "as", "교환", "환불")},
    {"id": "trust", "label": "신뢰·인증", "keywords": ("인증", "특허", "브랜드", "수출", "award", "kc", "안전")},
    {"id": "cta", "label": "CTA·구매", "keywords": ("구매", "장바구니", "바로구매", "지금", "cta", "smartstore", "쿠폰", "할인")},
]

_SSL_CTX = ssl.create_default_context()


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._skip = False
        self.chunks: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in ("script", "style", "noscript"):
            self._skip = True

    def handle_endtag(self, tag: str) -> None:
        if tag in ("script", "style", "noscript"):
            self._skip = False

    def handle_data(self, data: str) -> None:
        if not self._skip and data.strip():
            self.chunks.append(data.strip())


def _is_naver_store_url(url: str) -> bool:
    host = (urlparse(url).netloc or "").lower()
    return any(
        x in host
        for x in ("smartstore.naver.com", "brand.naver.com", "shopping.naver.com", "m.smartstore.naver.com")
    )


def normalize_url(url: str) -> str:
    url = (url or "").strip()
    if not url:
        return ""
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    parsed = urlparse(url)
    clean = parsed._replace(query="", fragment="")
    out = urlunparse(clean)
    if out.endswith("/") and parsed.path not in ("", "/"):
        out = out.rstrip("/")
    return out


def _fetch_html(url: str, *, retry: int = 2) -> tuple[str, str | None]:
    last_err: str | None = None
    for attempt in range(retry + 1):
        req = Request(
            url,
            headers={
                "User-Agent": _USER_AGENT,
                "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.8",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Referer": "https://www.naver.com/",
            },
        )
        try:
            with urlopen(req, timeout=_FETCH_TIMEOUT, context=_SSL_CTX) as resp:
                raw = resp.read(_MAX_BYTES + 1)
                if len(raw) > _MAX_BYTES:
                    raw = raw[:_MAX_BYTES]
                charset = resp.headers.get_content_charset() or "utf-8"
                html = raw.decode(charset, errors="replace")
                if "시스템오류" in html and len(html) < 20_000:
                    last_err = "네이버 차단(시스템오류 페이지)"
                elif len(html) > 500:
                    return html, None
                last_err = "응답 본문이 너무 짧음"
        except HTTPError as e:
            last_err = f"HTTP {e.code}"
            if e.code == 429 and attempt < retry:
                time.sleep(2.5 + attempt * 2)
                continue
        except URLError as e:
            last_err = str(e.reason or e)
        except Exception as e:
            last_err = str(e)
        if attempt < retry:
            time.sleep(1.5)
    return "", last_err


def _fetch_html_playwright(url: str) -> tuple[str, str | None]:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return "", "playwright 미설치"

    html = ""
    err: str | None = None
    try:
        with sync_playwright() as p:
            launch_kwargs: dict[str, Any] = {
                "headless": True,
                "args": ["--disable-blink-features=AutomationControlled"],
            }
            browser = None
            for channel in ("chrome", "msedge", None):
                try:
                    browser = p.chromium.launch(**({**launch_kwargs, "channel": channel} if channel else launch_kwargs))
                    break
                except Exception:
                    continue
            if browser is None:
                return "", "브라우저 실행 실패"

            ctx = browser.new_context(
                user_agent=_USER_AGENT,
                locale="ko-KR",
                viewport={"width": 1366, "height": 900},
            )
            ctx.add_init_script(
                "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"
            )
            page = ctx.new_page()
            try:
                page.goto("https://www.naver.com", wait_until="domcontentloaded", timeout=20000)
                time.sleep(0.8)
                page.goto(url, wait_until="domcontentloaded", timeout=35000)
                page.wait_for_timeout(2500)
                html = page.content()
                title = page.title() or ""
                if "로그인" in title and len(html) < 25_000:
                    err = "로그인 필요(네이버 차단)"
                elif "시스템오류" in title or "에러" in title:
                    err = "네이버 차단(시스템오류)"
                elif len(html) < 800:
                    err = "응답 본문이 너무 짧음"
            finally:
                browser.close()
    except Exception as e:
        return "", str(e)

    if err:
        return "", err
    return html, None


def _meta_content(html: str, prop: str) -> str:
    for pat in (
        rf'<meta[^>]+property=["\']{re.escape(prop)}["\'][^>]+content=["\']([^"\']+)',
        rf'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']{re.escape(prop)}["\']',
        rf'<meta[^>]+name=["\']{re.escape(prop)}["\'][^>]+content=["\']([^"\']+)',
    ):
        m = re.search(pat, html, re.I)
        if m:
            return unescape(m.group(1).strip())
    return ""


def _title_from_html(html: str) -> str:
    og = _meta_content(html, "og:title")
    if og:
        return og
    m = re.search(r"<title[^>]*>([^<]+)</title>", html, re.I)
    return unescape(m.group(1).strip()) if m else ""


def _visible_text(html: str) -> str:
    parser = _TextExtractor()
    try:
        parser.feed(html)
    except Exception:
        pass
    text = " ".join(parser.chunks)
    text = re.sub(r"\s+", " ", text)
    return text[:120_000]


def _detect_sections(text: str) -> dict[str, bool]:
    low = text.lower()
    norm = re.sub(r"\s+", "", text)
    out: dict[str, bool] = {}
    for sec in SECTION_DEFS:
        hit = any(kw.lower() in low or kw in norm for kw in sec["keywords"])
        out[sec["id"]] = hit
    return out


def _headlines(text: str, limit: int = 6) -> list[str]:
    lines = re.split(r"[.!?。\n|]", text)
    cands: list[str] = []
    for line in lines:
        s = line.strip()
        if 12 <= len(s) <= 90 and s not in cands:
            cands.append(s)
        if len(cands) >= limit:
            break
    return cands


def _domain_label(url: str) -> str:
    try:
        host = urlparse(url).netloc or url
        return host.replace("www.", "")[:40]
    except Exception:
        return url[:40]


def _guess_title_from_url(url: str) -> str:
    path = urlparse(url).path.strip("/")
    parts = path.split("/")
    if parts and parts[-1].isdigit() and len(parts) >= 2:
        return parts[-2].replace("-", " ")[:80]
    return _domain_label(url)


def _profile_from_text(
    url: str,
    text: str,
    *,
    html: str = "",
    source: str = "fetch",
) -> dict[str, Any]:
    title = _title_from_html(html) if html else ""
    if not title or title in ("에러페이지 - 시스템오류",):
        title = _guess_title_from_url(url)
        first_line = text.strip().split("\n", 1)[0].strip()
        if 8 <= len(first_line) <= 120:
            title = first_line[:120]

    sections = _detect_sections(text)
    img_count = len(re.findall(r"<img\b", html, re.I)) if html else 0
    has_video = bool(re.search(r"<video\b|youtube|youtu\.be|vimeo", html or text, re.I))

    strengths: list[str] = []
    for sec in SECTION_DEFS:
        if sections.get(sec["id"]):
            strengths.append(sec["label"])

    return {
        "url": url,
        "ok": True,
        "source": source,
        "domain": _domain_label(url),
        "title": title[:120],
        "sections": sections,
        "sectionLabels": strengths,
        "headlines": _headlines(text),
        "signals": {
            "imageCount": img_count,
            "hasVideo": has_video,
            "textLength": len(text),
        },
        "snippet": text[:400],
    }


def _normalize_manual_map(manual_by_url: dict[str, str] | None) -> dict[str, str]:
    out: dict[str, str] = {}
    for k, v in (manual_by_url or {}).items():
        nk = normalize_url(k)
        text = (v or "").strip()
        if nk and text:
            out[nk] = text
    return out


def _manual_for_url(
    url: str,
    *,
    manual_by_url: dict[str, str],
    manual_texts: list[str] | None,
    index: int,
) -> str | None:
    url = normalize_url(url)
    if manual_texts and index < len(manual_texts):
        t = (manual_texts[index] or "").strip()
        if t:
            return t
    direct = (manual_by_url.get(url) or "").strip()
    if direct:
        return direct
    for k, v in manual_by_url.items():
        if normalize_url(k) == url and (v or "").strip():
            return v.strip()
    return None


def analyze_competitor_url(
    url: str,
    *,
    manual_text: str | None = None,
) -> dict[str, Any]:
    url = normalize_url(url)
    if not url:
        return {"url": "", "ok": False, "error": "URL 없음"}

    pasted = (manual_text or "").strip()
    if pasted:
        if len(pasted) < 40:
            return {
                "url": url,
                "ok": False,
                "error": "붙여넣기 텍스트가 너무 짧습니다 (40자 이상)",
                "domain": _domain_label(url),
                "fetchHint": _FETCH_HINT,
            }
        return _profile_from_text(url, pasted, source="manual")

    if _is_naver_store_url(url):
        return {
            "url": url,
            "ok": False,
            "error": "본문 붙여넣기가 필요합니다 (네이버 자동 수집 불가)",
            "domain": _domain_label(url),
            "fetchHint": _FETCH_HINT,
            "title": _guess_title_from_url(url),
        }

    html, err = _fetch_html(url)
    if err and "429" not in str(err):
        pw_html, pw_err = _fetch_html_playwright(url)
        if pw_html:
            html, err = pw_html, None
        elif pw_err and not err:
            err = pw_err

    if err:
        return {
            "url": url,
            "ok": False,
            "error": err,
            "domain": _domain_label(url),
            "fetchHint": _FETCH_HINT,
            "title": _guess_title_from_url(url),
        }

    text = _visible_text(html)
    if len(text) < 80:
        return {
            "url": url,
            "ok": False,
            "error": "본문 텍스트 추출 실패",
            "domain": _domain_label(url),
            "fetchHint": _FETCH_HINT,
        }

    return _profile_from_text(url, text, html=html, source="fetch")


def analyze_competitor_urls(
    urls: list[str],
    *,
    manual_by_url: dict[str, str] | None = None,
    manual_texts: list[str] | None = None,
    own_product_url: str | None = None,
    own_manual_text: str | None = None,
) -> dict[str, Any]:
    manual_by_url = _normalize_manual_map(manual_by_url)
    clean: list[str] = []
    for u in urls:
        u = normalize_url(u)
        if u and u not in clean:
            clean.append(u)
    clean = clean[:5]

    profiles: list[dict[str, Any]] = []
    for i, u in enumerate(clean):
        if i > 0 and not _manual_for_url(u, manual_by_url=manual_by_url, manual_texts=manual_texts, index=i):
            time.sleep(0.8)
        profiles.append(
            analyze_competitor_url(
                u,
                manual_text=_manual_for_url(
                    u, manual_by_url=manual_by_url, manual_texts=manual_texts, index=i
                ),
            )
        )

    own_url = normalize_url(own_product_url or "")
    own_profile: dict[str, Any] | None = None
    own_manual_resolved = (own_manual_text or "").strip() or _lookup_manual(own_url, manual_by_url) or ""
    if own_url:
        own_profile = analyze_competitor_url(
            own_url,
            manual_text=own_manual_resolved or None,
        )
        own_profile["role"] = "own"
    elif own_manual_resolved and len(own_manual_resolved) >= 40:
        own_profile = _profile_from_text(
            "manual://own-product",
            own_manual_resolved,
            source="manual",
        )
        own_profile["role"] = "own"

    ok_profiles = [p for p in profiles if p.get("ok")]

    section_scores: dict[str, int] = {s["id"]: 0 for s in SECTION_DEFS}
    for p in ok_profiles:
        for sid, on in (p.get("sections") or {}).items():
            if on:
                section_scores[sid] = section_scores.get(sid, 0) + 1

    total = max(len(ok_profiles), 1)
    benchmark: list[dict[str, Any]] = []
    for sec in SECTION_DEFS:
        cnt = section_scores.get(sec["id"], 0)
        pct = round(100 * cnt / total)
        benchmark.append(
            {
                "id": sec["id"],
                "label": sec["label"],
                "competitorCoverage": pct,
                "recommended": pct >= 50 or sec["id"] in ("hero", "pain", "cta", "usp"),
            }
        )

    common_sections = [b["label"] for b in benchmark if b["competitorCoverage"] >= 50]
    gaps = [b["label"] for b in benchmark if b["recommended"] and b["competitorCoverage"] < 30]

    notes_lines = []
    for p in ok_profiles:
        notes_lines.append(f"[{p.get('domain')}] {p.get('title', '')}")
        if p.get("sectionLabels"):
            notes_lines.append("  섹션: " + ", ".join(p["sectionLabels"][:8]))
        if p.get("headlines"):
            notes_lines.append("  톤: " + " / ".join(p["headlines"][:2]))

    if own_profile and own_profile.get("ok"):
        notes_lines.append(f"[우리] {own_profile.get('title', '')}")
        if own_profile.get("sectionLabels"):
            notes_lines.append("  현재 섹션: " + ", ".join(own_profile["sectionLabels"][:8]))

    saved_manual: dict[str, str] = dict(manual_by_url)
    for i, u in enumerate(clean):
        t = _manual_for_url(u, manual_by_url=manual_by_url, manual_texts=manual_texts, index=i)
        if t:
            saved_manual[u] = t
    own_manual_saved = own_manual_resolved
    if own_url and own_manual_saved:
        saved_manual[own_url] = own_manual_saved
    elif own_manual_saved:
        saved_manual["manual://own-product"] = own_manual_saved

    return {
        "urls": clean,
        "ownProductUrl": own_url or None,
        "ownManualText": own_manual_saved or None,
        "manualByUrl": saved_manual,
        "ownProductProfile": own_profile,
        "profiles": profiles,
        "benchmark": benchmark,
        "summary": {
            "analyzed": len(ok_profiles),
            "failed": len(profiles) - len(ok_profiles),
            "commonSections": common_sections,
            "gapsToExploit": gaps,
            "recommendedFlow": (
                " → ".join(common_sections[:6])
                if common_sections
                else "히어로 → Pain → 전후 → USP → FAQ → CTA"
            ),
            "ownProductOk": bool(own_profile and own_profile.get("ok")),
        },
        "competitorNotesBlob": "\n".join(notes_lines),
        "fetchHint": _FETCH_HINT
        if (len(profiles) - len(ok_profiles)) > 0 or not ok_profiles
        else None,
    }


def _lookup_manual(url: str, manual_by_url: dict[str, str]) -> str | None:
    url = normalize_url(url)
    if not url:
        return None
    direct = (manual_by_url.get(url) or "").strip()
    if direct:
        return direct
    for k, v in manual_by_url.items():
        if normalize_url(k) == url and (v or "").strip():
            return v.strip()
    return None


def _finalize_benchmark_dict(data: dict[str, Any]) -> dict[str, Any]:
    profiles = data.get("profiles") or []
    own_profile = data.get("ownProductProfile")
    ok_profiles = [p for p in profiles if p.get("ok")]

    section_scores: dict[str, int] = {s["id"]: 0 for s in SECTION_DEFS}
    for p in ok_profiles:
        for sid, on in (p.get("sections") or {}).items():
            if on:
                section_scores[sid] = section_scores.get(sid, 0) + 1

    total = max(len(ok_profiles), 1)
    bench_rows: list[dict[str, Any]] = []
    for sec in SECTION_DEFS:
        cnt = section_scores.get(sec["id"], 0)
        pct = round(100 * cnt / total)
        bench_rows.append(
            {
                "id": sec["id"],
                "label": sec["label"],
                "competitorCoverage": pct,
                "recommended": pct >= 50 or sec["id"] in ("hero", "pain", "cta", "usp"),
            }
        )

    common_sections = [b["label"] for b in bench_rows if b["competitorCoverage"] >= 50]
    gaps = [b["label"] for b in bench_rows if b["recommended"] and b["competitorCoverage"] < 30]

    notes_lines = []
    for p in ok_profiles:
        notes_lines.append(f"[{p.get('domain')}] {p.get('title', '')}")
        if p.get("sectionLabels"):
            notes_lines.append("  섹션: " + ", ".join(p["sectionLabels"][:8]))
        if p.get("headlines"):
            notes_lines.append("  톤: " + " / ".join(p["headlines"][:2]))

    if own_profile and own_profile.get("ok"):
        notes_lines.append(f"[우리] {own_profile.get('title', '')}")
        if own_profile.get("sectionLabels"):
            notes_lines.append("  현재 섹션: " + ", ".join(own_profile["sectionLabels"][:8]))

    failed = len(profiles) - len(ok_profiles)
    data["benchmark"] = bench_rows
    data["summary"] = {
        "analyzed": len(ok_profiles),
        "failed": failed,
        "commonSections": common_sections,
        "gapsToExploit": gaps,
        "recommendedFlow": (
            " → ".join(common_sections[:6])
            if common_sections
            else "히어로 → Pain → 전후 → USP → FAQ → CTA"
        ),
        "ownProductOk": bool(own_profile and own_profile.get("ok")),
    }
    data["competitorNotesBlob"] = "\n".join(notes_lines)
    data["fetchHint"] = _FETCH_HINT if failed > 0 or not ok_profiles else None
    return data


def merge_competitor_benchmark(
    existing: dict[str, Any] | None,
    fresh: dict[str, Any],
    *,
    scope: str = "all",
) -> dict[str, Any]:
    scope = (scope or "all").lower()
    if not existing or scope == "all":
        return fresh
    merged = dict(fresh)
    merged["manualByUrl"] = {
        **(existing.get("manualByUrl") or {}),
        **(fresh.get("manualByUrl") or {}),
    }
    if scope == "own":
        merged["urls"] = existing.get("urls") or fresh.get("urls") or []
        merged["profiles"] = existing.get("profiles") or []
    elif scope == "competitors":
        merged["ownProductUrl"] = existing.get("ownProductUrl")
        merged["ownManualText"] = existing.get("ownManualText")
        merged["ownProductProfile"] = existing.get("ownProductProfile")
    return _finalize_benchmark_dict(merged)


def save_competitor_benchmark(slug_dir, data: dict) -> None:
    from pathlib import Path

    path = Path(slug_dir) / "competitor_benchmark.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def load_competitor_benchmark(slug_dir) -> dict | None:
    from pathlib import Path

    path = Path(slug_dir) / "competitor_benchmark.json"
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))
