# -*- coding: utf-8
"""
블로그 자동 파이프라인.

키워드 → 고유 글 + 이미지 + 영상 → 티스토리 / 네이버 / Blogger 업로드
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Callable

_ROOT = Path(__file__).resolve().parent.parent
_CFG = _ROOT / "config" / "blog_automation.json"
_REPORT = Path.home() / ".jarvis" / "learning" / "last_blog_auto.json"


def load_config() -> dict[str, Any]:
    if _CFG.is_file():
        return json.loads(_CFG.read_text(encoding="utf-8"))
    return {"enabled": True}


def default_publish_platforms() -> list[str]:
    return ["tistory", "naver", "blogger"]


def expand_publish_jobs(platforms: list[str] | None, cfg: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """티스토리 · 네이버(1,2,…) · Blogger 순 작업 목록."""
    cfg = cfg or load_config()
    order = platforms or cfg.get("publish_order") or default_publish_platforms()
    jobs: list[dict[str, Any]] = []
    for name in order:
        if name == "naver":
            from integrations.blog_credentials import list_naver_blog_targets

            targets = list_naver_blog_targets()
            if not targets:
                jobs.append({"key": "naver", "platform": "naver", "naver_target": None})
            for t in targets:
                jobs.append(
                    {
                        "key": f"naver:{t['blog_id']}",
                        "platform": "naver",
                        "naver_target": t,
                    }
                )
            continue
        plat = (cfg.get("platforms") or {}).get(name) or {}
        if plat.get("enabled", True):
            jobs.append({"key": name, "platform": name, "naver_target": None})
    return jobs


def ensure_playwright() -> dict[str, Any]:
    """playwright + chromium 자동 설치."""
    import subprocess
    import sys

    # 1차: 이미 설치된 경우 chromium 설치만 시도
    try:
        import playwright  # noqa: F401

        r = subprocess.run(
            [sys.executable, "-m", "playwright", "install", "chromium"],
            capture_output=True,
            text=True,
            timeout=300,
        )
        return {"ok": r.returncode == 0, "step": "chromium"}
    except Exception:
        # 2차: 설치를 한 번만 재시도하고, 실패해도 재귀하지 않는다.
        try:
            subprocess.run(
                [sys.executable, "-m", "pip", "install", "playwright", "pyperclip", "-q"],
                check=False,
            )
            import playwright  # noqa: F401

            r = subprocess.run(
                [sys.executable, "-m", "playwright", "install", "chromium"],
                capture_output=True,
                text=True,
                timeout=300,
            )
            return {"ok": r.returncode == 0, "step": "pip+chromium"}
        except Exception as e:
            return {"ok": False, "error": f"playwright 설치 실패: {e}"}


def login_platforms(
    platforms: list[str] | None = None,
    *,
    on_status: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    """수동 로그인 1회 — 이후 세션 유지."""
    emit = on_status or print
    cfg = load_config()
    if cfg.get("auto_login", True):
        ensure_playwright()
    results: dict[str, Any] = {}
    for job in expand_publish_jobs(platforms, cfg):
        key = job["key"]
        plat = job["platform"]
        emit(f"\n=== {key} 로그인 ===")
        if plat == "tistory":
            from integrations.blog_publisher_tistory import login_tistory

            results[key] = login_tistory(on_status=emit)
        elif plat == "naver":
            from integrations.blog_publisher_naver import login_naver_blog

            results[key] = login_naver_blog(naver_target=job.get("naver_target"), on_status=emit)
        elif plat == "blogger":
            from integrations.blog_publisher_blogger import login_blogger

            results[key] = login_blogger(on_status=emit)
        else:
            results[key] = {"ok": False, "error": f"알 수 없는 플랫폼: {plat}"}

    return {"ok": all(r.get("ok") for r in results.values()), "platforms": results}


def load_last_report() -> dict[str, Any] | None:
    if not _REPORT.is_file():
        return None
    try:
        return json.loads(_REPORT.read_text(encoding="utf-8"))
    except Exception:
        return None


def _filter_jobs_by_keys(jobs: list[dict[str, Any]], keys: list[str]) -> list[dict[str, Any]]:
    if not keys:
        return jobs
    want = {k.strip() for k in keys if k.strip()}
    out = [j for j in jobs if j.get("key") in want]
    if out:
        return out
    for j in jobs:
        plat = j.get("platform") or ""
        if plat in want:
            out.append(j)
    return out or jobs


def run_blog_retry_publish(
    *,
    report: dict[str, Any] | None = None,
    platform_keys: list[str] | None = None,
    on_status: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    """직전 글·이미지 재사용, 실패 플랫폼만 재발행."""
    _emit = on_status or print

    def emit(msg: str) -> None:
        try:
            _emit(msg)
        except UnicodeEncodeError:
            try:
                _emit(str(msg).encode("utf-8", errors="replace").decode("utf-8", errors="replace"))
            except Exception:
                pass
    base = report or load_last_report()
    if not base:
        return {"ok": False, "error": "last_blog_auto 없음"}

    art_r = (base.get("steps") or {}).get("article") or {}
    if not art_r.get("ok"):
        return {"ok": False, "error": "직전 글 생성 실패 — 전체 blog_auto 필요"}

    article = art_r.get("article") or {}
    media = (base.get("steps") or {}).get("media") or {}
    kw = str(base.get("keyword") or "").strip()
    title = article.get("title") or kw
    body = article.get("body_html") or article.get("body_plain") or ""
    tags = article.get("tags") or []

    from integrations.blog_tag_factory import expand_naver_tags

    naver_tags = expand_naver_tags(kw, tags, title=title)
    cfg = load_config()
    if cfg.get("auto_login", True):
        ensure_playwright()

    keys = platform_keys
    if not keys:
        from integrations.blog_evolution import failed_publish_keys

        keys = failed_publish_keys(base)
    if not keys:
        return {"ok": True, "skipped": "no_failed_platforms", "keyword": kw}

    emit(f"[블로그 재시도] {kw} — {', '.join(keys)}")
    jobs = _filter_jobs_by_keys(expand_publish_jobs(None, cfg), keys)
    pub_results: dict[str, Any] = dict((base.get("steps") or {}).get("publish") or {})

    from integrations.blog_credentials import naver_write_url as build_naver_write_url

    for job in jobs:
        key = job["key"]
        plat = job["platform"]
        emit(f"\n[재발행] {key}...")
        plat_tags = naver_tags if plat == "naver" else tags
        kwargs = {
            "title": title,
            "body_html": body,
            "tags": plat_tags,
            "image_paths": media.get("images") or [],
            "video_path": media.get("video") or "",
            "on_status": emit,
        }
        if plat == "tistory":
            from integrations.blog_publisher_tistory import publish_tistory

            pub_results[key] = publish_tistory(**kwargs)
        elif plat == "naver":
            from integrations.blog_publisher_naver import publish_naver_blog

            target = job.get("naver_target") or {}
            bid = (target.get("blog_id") or "").strip()
            pub_results[key] = publish_naver_blog(
                **kwargs,
                blog_write_url=build_naver_write_url(bid),
                naver_target=target,
            )
        elif plat == "blogger":
            from integrations.blog_publisher_blogger import publish_blogger

            pub_results[key] = publish_blogger(**kwargs)
        else:
            pub_results[key] = {"ok": False, "error": f"unknown: {plat}"}

    merged = dict(base)
    merged["steps"] = dict(base.get("steps") or {})
    merged["steps"]["publish"] = pub_results
    merged["retry"] = True
    merged["retry_keys"] = keys
    merged["finished"] = time.time()
    merged["ok"] = all(
        isinstance(v, dict) and v.get("ok") for v in pub_results.values()
    ) if pub_results else False
    attach_failure_summary(merged)
    _save_report(merged)
    try:
        from integrations.blog_evolution import record_blog_run

        record_blog_run(merged)
    except Exception:
        pass
    fs = merged.get("failure_summary") or {}
    if fs.get("has_issues") or not merged.get("ok"):
        emit("\n[실패 원인 요약]")
        emit(fs.get("headline_ko") or "—")
        for line in fs.get("lines_ko") or []:
            emit(f"  · {line}")
    emit(f"\n[재시도 완료] ok={merged['ok']}")
    return merged


def run_blog_auto(
    keyword: str,
    *,
    platforms: list[str] | None = None,
    publish: bool = True,
    skip_media: bool = False,
    with_video: bool = False,
    naver_write_url_override: str = "",
    guideline: str = "",
    on_status: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    """키워드 1개 → 글·미디어·업로드."""
    _emit = on_status or print

    def emit(msg: str) -> None:
        try:
            _emit(msg)
        except UnicodeEncodeError:
            try:
                _emit(str(msg).encode("utf-8", errors="replace").decode("utf-8", errors="replace"))
            except Exception:
                pass
    kw = (keyword or "").strip()
    if not kw:
        return {"ok": False, "error": "keyword 필요"}

    cfg = load_config()
    if not cfg.get("enabled", True):
        return {"ok": False, "error": "blog_automation disabled"}

    if publish and cfg.get("auto_login", True):
        ensure_playwright()

    from integrations.blog_content_factory import load_writing_guideline

    g_full = load_writing_guideline(guideline)
    report: dict[str, Any] = {
        "keyword": kw,
        "guideline_applied": bool(g_full),
        "started": time.time(),
        "steps": {},
    }
    emit(f"[블로그] 키워드: {kw}")
    if g_full:
        emit(f"[블로그] 사용자 지침 반영 ({len(g_full)}자)")

    try:
        from integrations.blog_content_factory import create_preview_article, create_unique_article
    except ImportError:
        # 오래 실행된 Streamlit 프로세스의 모듈 캐시가 구버전일 때 안전 폴백.
        from integrations.blog_content_factory import create_unique_article

        create_preview_article = None  # type: ignore[assignment]

    if not publish and create_preview_article is not None:
        art_r = create_preview_article(kw, guideline=guideline)
    else:
        art_r = create_unique_article(kw, guideline=guideline)
    report["steps"]["article"] = art_r
    if not art_r.get("ok"):
        dup = art_r.get("duplicate_check") or {}
        reason_code = str(dup.get("reason") or "").strip()
        reason_map = {
            "keyword_cooldown": "동일 키워드 재발행 쿨다운",
            "identical_body_hash": "본문 중복(해시)",
            "identical_title_hash": "제목 중복(해시)",
            "high_similarity": "기존 글과 유사도 높음",
        }
        reason = art_r.get("error") or reason_map.get(reason_code) or reason_code or "알 수 없는 오류"
        report["ok"] = False
        report["error"] = f"글 생성 실패: {reason}"
        _save_report(report)
        return report

    article = art_r.get("article") or {}
    title = article.get("title") or kw
    body = article.get("body_html") or article.get("body_plain") or ""
    emit(f"[블로그] 글 생성 완료 — 제목: {title[:50]}")
    tags = article.get("tags") or []
    from integrations.blog_tag_factory import expand_naver_tags

    naver_tags = expand_naver_tags(kw, tags, title=title)

    if skip_media:
        media = {"ok": True, "images": [], "video": "", "skipped": True}
    else:
        emit("[블로그] Gemini 이미지 생성 (영상은 기본 생략)...")
        from integrations.blog_media_factory import generate_blog_media

        media = generate_blog_media(article, keyword=kw, with_video=with_video)
    report["steps"]["media"] = media
    if media.get("ok"):
        emit(f"[블로그] 미디어 완료 — 이미지 {len(media.get('images') or [])}장")
    else:
        emit("[블로그] 미디어 생성 실패")

    pub_results: dict[str, Any] = {}
    if publish:
        from integrations.blog_credentials import naver_write_url as build_naver_write_url

        for job in expand_publish_jobs(platforms, cfg):
            key = job["key"]
            plat = job["platform"]
            emit(f"\n[업로드] {key}...")
            plat_tags = naver_tags if plat == "naver" else tags
            kwargs = {
                "title": title,
                "body_html": body,
                "tags": plat_tags,
                "image_paths": media.get("images") or [],
                "video_path": (media.get("video") or "") if with_video else "",
                "on_status": emit,
            }
            if plat == "tistory":
                from integrations.blog_publisher_tistory import publish_tistory

                pub_results[key] = publish_tistory(**kwargs)
            elif plat == "naver":
                from integrations.blog_publisher_naver import publish_naver_blog

                target = job.get("naver_target") or {}
                bid = (target.get("blog_id") or "").strip()
                write_url = (naver_write_url_override or build_naver_write_url(bid)).strip()
                pub_results[key] = publish_naver_blog(
                    **kwargs,
                    blog_write_url=write_url,
                    naver_target=target,
                )
            elif plat == "blogger":
                from integrations.blog_publisher_blogger import publish_blogger

                pub_results[key] = publish_blogger(**kwargs)
            else:
                pub_results[key] = {"ok": False, "error": f"unknown: {plat}"}

    report["steps"]["publish"] = pub_results

    if publish and pub_results:
        from integrations.blog_duplicate_guard import record_published

        ok_platforms = [k for k, v in pub_results.items() if v.get("ok")]
        if ok_platforms:
            record_published(
                keyword=kw,
                title=title,
                body=body,
                platforms=ok_platforms,
                media_dir=media.get("output_dir") or "",
            )

    report["finished"] = time.time()
    article_ok = bool(article) and len((body or "").strip()) >= 120
    media_ok = bool(media.get("ok", True))
    publish_ok = (not publish) or all(r.get("ok") for r in pub_results.values())
    report["ok"] = bool(article_ok and media_ok and publish_ok)
    if not report["ok"]:
        fails = [k for k, v in (pub_results or {}).items() if not v.get("ok")]
        if fails:
            report["error"] = "발행 실패: " + ", ".join(fails)
        elif not article_ok:
            report["error"] = "본문 생성 부족 또는 실패"
    attach_failure_summary(report)
    _save_report(report)
    try:
        from integrations.blog_evolution import record_blog_run

        record_blog_run(report)
    except Exception:
        pass
    if pub_results:
        emit("\n[발행 요약]")
        for k, v in pub_results.items():
            mark = "OK" if v.get("ok") else "FAIL"
            emit(f"  {mark} {k}")
    fs = report.get("failure_summary") or {}
    if fs.get("has_issues") or not report.get("ok"):
        emit("\n[실패 원인 요약]")
        emit(fs.get("headline_ko") or report.get("error") or "—")
        for line in fs.get("lines_ko") or []:
            emit(f"  · {line}")
    emit(f"\n[완료] ok={report['ok']}")
    return report


def _save_report(report: dict[str, Any]) -> None:
    _REPORT.parent.mkdir(parents=True, exist_ok=True)
    _REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")


_FAILURE_LABELS_KO: dict[str, str] = {
    "entry_failed": "진입 실패 (로그인·글쓰기 화면 미도달)",
    "body_insufficient": "본문 부족 (에디터 입력 실패)",
    "tags_failed": "태그 입력 실패",
    "publish_not_clicked": "발행 버튼 미클릭",
    "article_failed": "글·본문 생성 실패",
    "media_failed": "이미지·영상 생성 실패",
    "login_required": "로그인 필요",
}


def _classify_publish_result(result: dict[str, Any]) -> list[str]:
    """단일 플랫폼 발행 결과 → 실패 유형 코드 목록."""
    if not isinstance(result, dict):
        return ["entry_failed"]

    err = (result.get("error") or "").strip().lower()
    cats: list[str] = []

    if not result.get("ok"):
        if "login" in err or "로그인" in err:
            cats.append("login_required")
        if any(
            x in err
            for x in (
                "write",
                "글쓰기",
                "postwrite",
                "mainframe",
                "진입",
                "editor",
                "url",
                "이동",
            )
        ):
            cats.append("entry_failed")
        if any(x in err for x in ("body", "본문", "content", "에디터")):
            cats.append("body_insufficient")
        if "tag" in err or "태그" in err:
            cats.append("tags_failed")
        if "publish" in err or "발행" in err:
            cats.append("publish_not_clicked")
        if not cats:
            if result.get("title_filled") and not result.get("body_filled"):
                cats.append("body_insufficient")
            elif not result.get("body_ok", True):
                cats.append("body_insufficient")
            elif not result.get("published_clicked"):
                cats.append("publish_not_clicked")
            else:
                cats.append("entry_failed")
        return list(dict.fromkeys(cats))

    body_chars = int(result.get("body_chars") or 0)
    if result.get("body_ok") is False or body_chars < 80:
        cats.append("body_insufficient")
    tags = result.get("tags") or []
    tags_filled = int(result.get("tags_filled") or 0)
    if tags and tags_filled < 1:
        cats.append("tags_failed")
    if not result.get("published_clicked"):
        cats.append("publish_not_clicked")
    return list(dict.fromkeys(cats))


def _iter_publish_results(publish: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    out: list[tuple[str, dict[str, Any]]] = []
    for key, val in (publish or {}).items():
        if isinstance(val, list):
            for i, one in enumerate(val):
                if isinstance(one, dict):
                    out.append((f"{key}[{i}]", one))
        elif isinstance(val, dict):
            out.append((key, val))
    return out


def summarize_blog_failures(report: dict[str, Any]) -> dict[str, Any]:
    """실행 리포트에서 실패 유형·플랫폼별 메시지·한 줄 요약 생성."""
    steps = report.get("steps") or {}
    article = steps.get("article") or {}
    media = steps.get("media") or {}
    publish = steps.get("publish") or {}

    by_category: dict[str, list[str]] = {k: [] for k in _FAILURE_LABELS_KO}
    platform_issues: list[dict[str, Any]] = []

    if not article.get("ok"):
        by_category["article_failed"].append("(글 생성)")
        platform_issues.append(
            {
                "platform": "article",
                "categories": ["article_failed"],
                "message_ko": article.get("error") or "Gemini 글 생성 실패",
            }
        )
    else:
        body_plain = (article.get("body_plain") or "").strip()
        if len(body_plain) < 120:
            by_category["body_insufficient"].append("(생성 본문 짧음)")
            platform_issues.append(
                {
                    "platform": "article",
                    "categories": ["body_insufficient"],
                    "message_ko": f"생성 본문 {len(body_plain)}자 — 120자 미만",
                }
            )

    if media and not media.get("ok") and not media.get("skipped"):
        by_category["media_failed"].append("(미디어)")
        platform_issues.append(
            {
                "platform": "media",
                "categories": ["media_failed"],
                "message_ko": media.get("error") or "이미지·영상 생성 실패",
            }
        )

    for plat_key, one in _iter_publish_results(publish):
        cats = _classify_publish_result(one)
        if not cats:
            continue
        label = _FAILURE_LABELS_KO.get(cats[0], cats[0])
        detail = (one.get("error") or "").strip()
        if not detail:
            parts = []
            if "body_insufficient" in cats:
                parts.append(f"본문 {int(one.get('body_chars') or 0)}자")
            if "tags_failed" in cats:
                parts.append(f"태그 {int(one.get('tags_filled') or 0)}개 입력")
            if "publish_not_clicked" in cats:
                parts.append("발행 클릭 없음")
            if "entry_failed" in cats:
                parts.append("글쓰기 화면 미진입")
            detail = ", ".join(parts) if parts else label
        for c in cats:
            if plat_key not in by_category[c]:
                by_category[c].append(plat_key)
        platform_issues.append(
            {
                "platform": plat_key,
                "categories": cats,
                "message_ko": detail,
                "ok": bool(one.get("ok")),
                "published_clicked": bool(one.get("published_clicked")),
                "body_chars": int(one.get("body_chars") or 0),
            }
        )

    active_cats = [c for c, plats in by_category.items() if plats]
    lines: list[str] = []
    for cat in active_cats:
        plats = by_category[cat]
        lines.append(f"{_FAILURE_LABELS_KO[cat]}: {', '.join(plats)}")

    if report.get("ok") and not lines:
        headline = "실패 없음 — 단계가 정상 완료되었습니다."
    elif not lines:
        headline = report.get("error") or "실패 원인을 분류하지 못했습니다. last_blog_auto.json을 확인하세요."
    else:
        headline = lines[0]
        if len(lines) > 1:
            headline += f" 외 {len(lines) - 1}건"

    return {
        "headline_ko": headline,
        "lines_ko": lines,
        "by_category": {k: v for k, v in by_category.items() if v},
        "platform_issues": platform_issues,
        "has_issues": bool(lines) or not report.get("ok"),
    }


def attach_failure_summary(report: dict[str, Any]) -> dict[str, Any]:
    """report에 failure_summary를 붙여 반환 (저장·UI 공용)."""
    report["failure_summary"] = summarize_blog_failures(report)
    return report


def format_failure_summary_ko(report: dict[str, Any] | None = None) -> str:
    """UI·CLI용 실패 요약 텍스트."""
    r = report
    if r is None and _REPORT.is_file():
        try:
            r = json.loads(_REPORT.read_text(encoding="utf-8"))
        except Exception:
            r = {}
    if not r:
        return "저장된 블로그 실행 기록이 없습니다."
    fs = r.get("failure_summary") or summarize_blog_failures(r)
    lines = ["【실패 원인 요약】", fs.get("headline_ko") or "—"]
    for line in fs.get("lines_ko") or []:
        lines.append(f"  · {line}")
    if not (fs.get("lines_ko")) and r.get("error"):
        lines.append(f"  · {r.get('error')}")
    lines.append("")
    lines.append(f"전체 ok={r.get('ok')} | 키워드={r.get('keyword', '—')}")
    return "\n".join(lines)


def load_last_blog_report() -> dict[str, Any]:
    if not _REPORT.is_file():
        return {}
    try:
        return json.loads(_REPORT.read_text(encoding="utf-8"))
    except Exception:
        return {}


def format_status_ko() -> str:
    cfg = load_config()
    lines = [
        "=== 블로그 자동 글쓰기·이미지·영상·업로드 ===",
        "",
        "지원: 티스토리 · 네이버(복수) · Google Blogger — 한 번에 전체 발행",
        "★ 저장된 계정으로 자동 로그인 (실패·봇 → Windows 팝업 + 알림 파일) ★",
        "★ 카톡: config notify.webhook_url 또는 JARVIS_NOTIFY_WEBHOOK (n8n 연동) ★",
        "★ 네이버 — 서식 없이 붙여넣기로 밑줄 자동 제거 ★",
        "★ 이미지 — Gemini/Imagen 생성 (Pexels·폴더 선택 없음) ★",
        "★ 같은 글·같은 내용 — 해시·유사도로 차단 ★",
        "",
        "[1] 로그인 (최초 1회 — 캡차·2FA는 브라우저에서 직접)",
        "  run_블로그_자동.bat login",
        "  run_블로그_자동.bat naver   (네이버만)",
        "  python run_blog_auto.py --login",
        "",
        "[2] 전체 발행 (티스토리 + 네이버1·2 + 구글)",
        "  run_블로그_전체.bat \"키워드\"",
        "  python run_blog_auto.py \"키워드\" --all --force",
        "  지침: config/blog_writing_guideline.txt (또는 --guideline \"추가 지침\")",
        "[3] 키워드 → 글+Gemini이미지+발행",
        "  run_블로그_자동.bat \"키워드\"",
        "  (영상 필요 시) --with-video",
        "",
        "[플랫폼]",
    ]
    for name, plat in (cfg.get("platforms") or {}).items():
        en = "[ON]" if plat.get("enabled", True) else "[OFF]"
        lines.append(f"  {en} {name} — {plat.get('browser_dir', '')}")
    try:
        from integrations.blog_credentials import list_naver_blog_targets

        for t in list_naver_blog_targets():
            lines.append(f"  · 네이버 {t.get('label')} → blog.naver.com/{t.get('blog_id')}")
    except Exception:
        pass
    lines.extend(
        [
            "",
            "【실패 원인 분류 (UI·콘솔·last_blog_auto.json)】",
            "  · 진입 실패 — 로그인·글쓰기 화면 미도달",
            "  · 본문 부족 — 에디터 입력 실패·생성 본문 짧음",
            "  · 태그 입력 실패",
            "  · 발행 버튼 미클릭",
            "  · run_blog_auto.py / blog_auto action=last 로 마지막 요약 조회",
            "",
            f"중복 레지스트리: {cfg.get('registry_path', '.jarvis/blog_published/registry.jsonl')}",
            f"계정 파일: .jarvis/blog_credentials.local.json (git 제외)",
            f"알림 파일: {Path.home() / '.jarvis' / 'ALERT_LOGIN_REQUIRED.json'}",
        ]
    )
    if _REPORT.is_file():
        try:
            r = load_last_blog_report()
            lines.append(f"  마지막 키워드: {r.get('keyword', '—')}")
            fs = r.get("failure_summary") or {}
            if fs.get("headline_ko"):
                lines.append(f"  마지막 결과: {fs.get('headline_ko')}")
        except Exception:
            pass
    return "\n".join(lines)
