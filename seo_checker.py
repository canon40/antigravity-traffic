import json
import os
import re
import time
from datetime import datetime
from urllib.parse import urlparse

import requests

CONFIG_PATH = "config.json"
AUDIT_PATH = "seo_audit_history.json"
PRODUCT_FETCH_DELAY_SEC = float(os.environ.get("SEO_PRODUCT_DELAY_SEC", "4"))
MOBILE_UA = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"
)
DESKTOP_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
)
_SESSION = requests.Session()


def load_config():
    if not os.path.exists(CONFIG_PATH):
        return {"product_urls": [], "blog_urls": [], "keywords": []}
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def _normalize_audit_url(url: str) -> str:
    """네이버 블로그·스마트스토어는 모바일 URL이 SEO 메타를 더 잘 반환합니다."""
    parsed = urlparse(url)
    host = (parsed.netloc or "").lower()
    path = parsed.path or "/"
    if host == "blog.naver.com":
        return f"https://m.blog.naver.com{path}"
    if host == "smartstore.naver.com":
        return f"https://m.smartstore.naver.com{path}"
    return url


def _is_shell_html(html: str) -> bool:
    """JS 껍데기만 받은 경우(제목·본문 없음)."""
    if len(html) < 800:
        return True
    return not _extract_title(html) and "<h1" not in html.lower()


def _fetch_html_once(url: str, *, user_agent: str) -> tuple[str, str, int]:
    headers = {
        "User-Agent": user_agent,
        "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }
    res = _SESSION.get(url, headers=headers, timeout=20, allow_redirects=True)
    res.encoding = res.apparent_encoding or "utf-8"
    return res.text, res.url, res.status_code


def _fetch_html(url: str) -> tuple[str, str]:
    audit_url = _normalize_audit_url(url)
    last_error = ""
    for attempt, ua in enumerate((MOBILE_UA, DESKTOP_UA)):
        for retry in range(3):
            html, final_url, status = _fetch_html_once(audit_url, user_agent=ua)
            if status == 429:
                last_error = "HTTP 429 (요청 과다) — 잠시 후 재시도"
                time.sleep(3 + retry * 4)
                continue
            if status >= 400:
                last_error = f"HTTP {status}"
                break
            if not _is_shell_html(html):
                return html, final_url
            last_error = "빈 껍데기 HTML (JS 렌더 필요)"
            break
        if attempt == 0 and audit_url != url:
            audit_url = url
    raise RuntimeError(last_error or "페이지를 가져오지 못했습니다")


def _extract_meta(html, name=None, prop=None):
    if name:
        m = re.search(
            rf'<meta[^>]+name=["\']{re.escape(name)}["\'][^>]+content=["\']([^"\']*)["\']',
            html,
            re.I,
        )
        if not m:
            m = re.search(
                rf'<meta[^>]+content=["\']([^"\']*)["\'][^>]+name=["\']{re.escape(name)}["\']',
                html,
                re.I,
            )
        return m.group(1).strip() if m else ""
    if prop:
        m = re.search(
            rf'<meta[^>]+property=["\']{re.escape(prop)}["\'][^>]+content=["\']([^"\']*)["\']',
            html,
            re.I,
        )
        if not m:
            m = re.search(
                rf'<meta[^>]+content=["\']([^"\']*)["\'][^>]+property=["\']{re.escape(prop)}["\']',
                html,
                re.I,
            )
        return m.group(1).strip() if m else ""
    return ""


def _extract_title(html):
    m = re.search(r"<title[^>]*>([^<]+)</title>", html, re.I)
    return m.group(1).strip() if m else ""


def _count_tags(html, tag):
    return len(re.findall(rf"<{tag}[^>]*>", html, re.I))


def _images_without_alt(html):
    imgs = re.findall(r"<img[^>]*>", html, re.I)
    missing = 0
    for img in imgs:
        if not re.search(r'alt=["\'][^"\']+["\']', img, re.I):
            missing += 1
    return missing, len(imgs)


def audit_page(url, page_type="page", target_keywords=None):
    target_keywords = target_keywords or []
    checks = []
    score = 0
    max_score = 0

    def add_check(name, passed, message, weight=1):
        nonlocal score, max_score
        max_score += weight
        if passed:
            score += weight
        checks.append({"name": name, "passed": passed, "message": message, "weight": weight})

    try:
        html, final_url = _fetch_html(url)
    except Exception as e:
        err = str(e)
        hint = ""
        if "429" in err:
            hint = " — 상품 URL을 한꺼번에 점검하면 네이버가 차단합니다. 5분 후 재시도하거나 상품을 2~3개씩 나눠 점검하세요."
        elif page_type == "blog" and "blog.naver.com" in url:
            hint = " — 블로그 홈 대신 최근 글 URL(m.blog.naver.com/아이디/글번호)로 점검하면 더 정확합니다."
        return {
            "url": url,
            "audit_url": _normalize_audit_url(url),
            "page_type": page_type,
            "success": False,
            "error": err + hint,
            "checks": [],
            "score": 0,
            "max_score": 0,
            "grade": "F",
        }

    title = _extract_title(html)
    description = _extract_meta(html, name="description")
    og_title = _extract_meta(html, prop="og:title")
    viewport = _extract_meta(html, name="viewport")
    h1_count = _count_tags(html, "h1")
    missing_alt, img_total = _images_without_alt(html)

    add_check(
        "페이지 제목(title)",
        bool(title) and 10 <= len(title) <= 70,
        f"{'✓' if title else '✗'} {title[:60] + '…' if len(title) > 60 else (title or '없음')} (권장 10~70자)",
        2,
    )
    add_check(
        "메타 설명(description)",
        bool(description) and 50 <= len(description) <= 160,
        f"{'✓' if description else '✗'} {len(description)}자 (권장 50~160자)",
        2,
    )
    add_check(
        "모바일 viewport",
        "width=device-width" in viewport,
        f"{'✓' if viewport else '✗'} {viewport or 'viewport 미설정'}",
        2,
    )
    add_check(
        "H1 태그",
        h1_count == 1,
        f"{'✓' if h1_count == 1 else '✗'} H1 {h1_count}개 (권장 1개)",
        1,
    )
    add_check(
        "이미지 alt 속성",
        img_total == 0 or missing_alt == 0,
        f"이미지 {img_total}개 중 alt 누락 {missing_alt}개",
        1,
    )
    add_check(
        "OG 태그(공유 미리보기)",
        bool(og_title),
        f"{'✓' if og_title else '✗'} og:title {'있음' if og_title else '없음'}",
        1,
    )

    if target_keywords:
        combined = (title + " " + description + " " + html[:5000]).lower()
        found = [kw for kw in target_keywords if kw.lower() in combined]
        add_check(
            "타겟 키워드 포함",
            len(found) > 0,
            f"발견: {', '.join(found) if found else '없음'} (대상: {', '.join(target_keywords[:3])})",
            2,
        )

    if page_type == "product":
        add_check(
            "HTTPS 보안",
            final_url.startswith("https://"),
            f"{'✓' if final_url.startswith('https') else '✗'} {urlparse(final_url).scheme}",
            1,
        )

    pct = int(score / max_score * 100) if max_score else 0
    if pct >= 80:
        grade = "A"
    elif pct >= 60:
        grade = "B"
    elif pct >= 40:
        grade = "C"
    else:
        grade = "D"

    return {
        "url": url,
        "audit_url": _normalize_audit_url(url),
        "final_url": final_url,
        "page_type": page_type,
        "success": True,
        "checks": checks,
        "score": score,
        "max_score": max_score,
        "percent": pct,
        "grade": grade,
        "audited_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
    }


def run_full_audit(logger=None):
    config = load_config()
    keywords = [k.get("keyword", "") for k in config.get("keywords", []) if k.get("keyword")]

    results = {"products": [], "blogs": [], "summary": {}}

    for i, url in enumerate(config.get("product_urls", [])):
        if i > 0 and PRODUCT_FETCH_DELAY_SEC > 0:
            time.sleep(PRODUCT_FETCH_DELAY_SEC)
        if logger:
            logger(f"🔎 상품 페이지 SEO 점검: {url}")
        results["products"].append(audit_page(url, "product", keywords))

    for url in config.get("blog_urls", []):
        if logger:
            logger(f"🔎 블로그 SEO 점검: {url}")
        results["blogs"].append(audit_page(url, "blog", keywords))

    all_pages = results["products"] + results["blogs"]
    ok_pages = [p for p in all_pages if p.get("success")]
    avg = int(sum(p.get("percent", 0) for p in ok_pages) / len(ok_pages)) if ok_pages else 0
    failed = [p for p in all_pages if not p.get("success")]

    results["summary"] = {
        "total_pages": len(all_pages),
        "audited_ok": len(ok_pages),
        "failed": len(failed),
        "average_score": avg,
        "completed_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "recommendations": _build_recommendations(all_pages),
    }

    _save_audit_history(results)
    return results


def _build_recommendations(pages):
    recs = []
    for page in pages:
        if not page.get("success"):
            detail = page.get("error") or "URL 확인 필요"
            recs.append(f"{page['url']}: {detail}")
            continue
        for check in page.get("checks", []):
            if not check["passed"]:
                recs.append(f"[{page['page_type']}] {check['name']}: {check['message']}")
    return recs[:15]


def _save_audit_history(results):
    history = []
    if os.path.exists(AUDIT_PATH):
        try:
            with open(AUDIT_PATH, "r", encoding="utf-8") as f:
                history = json.load(f)
        except Exception:
            history = []
    history.append(results)
    history = history[-30:]
    with open(AUDIT_PATH, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)


def get_latest_audit():
    if not os.path.exists(AUDIT_PATH):
        return None
    try:
        with open(AUDIT_PATH, "r", encoding="utf-8") as f:
            history = json.load(f)
        return history[-1] if history else None
    except Exception:
        return None
