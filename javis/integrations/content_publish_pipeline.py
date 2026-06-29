# -*- coding: utf-8
"""
숏폼 → YouTube → 블로그(영상 첨부) → 트래픽 연동 파이프라인.

1) AI Factory MP4 확보 (없으면 생성)
2) YouTube 업로드
3) JARVIS 블로그 자동 발행 (MP4 + YouTube 링크)
4) 스마트스토어 트래픽 1회 (선택)
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Callable

_ANTY = Path(__file__).resolve().parents[2]
if str(_ANTY) not in sys.path:
    sys.path.insert(0, str(_ANTY))

from blog_pipeline_runner import bootstrap_jarvis_imports

bootstrap_jarvis_imports()
_bundled = Path(__file__).resolve().parent.parent
if _bundled.is_dir() and str(_bundled) not in sys.path:
    sys.path.insert(0, str(_bundled))

_ROOT = _bundled

_CFG = _ROOT / "config" / "blog_automation.json"


def _load_cfg() -> dict[str, Any]:
    if _CFG.is_file():
        return json.loads(_CFG.read_text(encoding="utf-8"))
    return {}


def _emit(on_status: Callable[[str], None] | None, msg: str) -> None:
    fn = on_status or print
    try:
        fn(msg)
    except UnicodeEncodeError:
        fn(str(msg).encode("utf-8", errors="replace").decode("utf-8", errors="replace"))


def _resolve_store_url(keyword: str) -> str:
    try:
        anty = _ROOT.parent
        if str(anty) not in sys.path:
            sys.path.insert(0, str(anty))
        from store_link_builder import resolve_listing

        listing = resolve_listing(keyword)
        return str(listing.get("url") or "")
    except Exception:
        return ""


def _run_traffic_once(keyword: str, store_url: str, on_status: Callable[[str], None] | None) -> dict[str, Any]:
    if not store_url:
        return {"ok": False, "skipped": "no_store_url"}
    try:
        anty = _ROOT.parent
        vt = anty / "vercel_traffic"
        if str(vt) not in sys.path:
            sys.path.insert(0, str(vt))
        from traffic_session import run_traffic_session

        referer = f"https://m.search.naver.com/search.naver?query={keyword.replace(' ', '+')}"
        _emit(on_status, f"[트래픽] {keyword} → {store_url[:70]}...")
        outcome = run_traffic_session(store_url, referer_url=referer)
        return {"ok": bool(outcome.get("ok")), **outcome}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def run_content_publish_pipeline(
    keyword: str,
    *,
    create_video: bool | None = None,
    upload_youtube: bool | None = None,
    publish_blog: bool = True,
    trigger_traffic: bool | None = None,
    platforms: list[str] | None = None,
    video_path: str = "",
    youtube_url: str = "",
    duration: int = 30,
    test_mode: bool = False,
    on_status: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    """키워드 1개 — 숏폼·YouTube·블로그·트래픽 일괄."""
    kw = (keyword or "").strip()
    if not kw:
        return {"ok": False, "error": "keyword 필요"}

    cfg = _load_cfg()
    media_cfg = cfg.get("media") or {}
    yt_cfg = cfg.get("youtube") or {}

    if create_video is None:
        create_video = bool(media_cfg.get("auto_create_shorts", True))
    if upload_youtube is None:
        upload_youtube = bool(yt_cfg.get("enabled", True))
    if trigger_traffic is None:
        trigger_traffic = bool(cfg.get("traffic_after_publish", True))

    report: dict[str, Any] = {
        "ok": False,
        "keyword": kw,
        "started": time.time(),
        "steps": {},
    }

    from integrations.shorts_resolver import (
        ensure_shorts_mp4,
        find_shorts_mp4,
        manifest_youtube_url,
        save_manifest_entry,
    )

    # ── 1) 숏폼 MP4 ──
    mp4_path = (video_path or "").strip()
    if mp4_path:
        p = Path(mp4_path)
        if not p.is_file():
            return {"ok": False, "error": f"영상 없음: {mp4_path}"}
        mp4_path = str(p.resolve())
        _emit(on_status, f"[숏폼] 지정 영상: {mp4_path}")
    else:
        existing = find_shorts_mp4(kw)
        if existing:
            mp4_path = str(existing)
            _emit(on_status, f"[숏폼] 기존 영상 사용: {mp4_path}")
        elif create_video:
            created = ensure_shorts_mp4(
                kw,
                create_if_missing=True,
                duration=duration,
                test_mode=test_mode,
                on_status=on_status,
            )
            mp4_path = str(created) if created else ""
        else:
            mp4_path = ""

    report["steps"]["shorts"] = {"ok": bool(mp4_path), "path": mp4_path}
    if not mp4_path and publish_blog:
        _emit(on_status, "[경고] 영상 없음 — 블로그는 텍스트만 발행")

    # ── 2) YouTube ──
    yt_url = (youtube_url or manifest_youtube_url(kw)).strip()
    if upload_youtube and mp4_path and not yt_url:
        from integrations.youtube_uploader import upload_youtube_short, youtube_configured

        if not youtube_configured():
            _emit(on_status, "[YouTube] OAuth 미설정 — data/youtube_client_secrets.json 참고")
            report["steps"]["youtube"] = {"ok": False, "skipped": "not_configured"}
        else:
            store_url = _resolve_store_url(kw)
            yt_r = upload_youtube_short(
                mp4_path,
                title=f"{kw} 셀프 코팅 숏폼",
                description=f"{kw} 사용법·효과 요약\n\n스마트스토어: {store_url}",
                tags=list(yt_cfg.get("default_tags") or []) + [kw],
                privacy=str(yt_cfg.get("privacy") or "public"),
                category_id=str(yt_cfg.get("category_id") or "22"),
                on_status=on_status,
            )
            report["steps"]["youtube"] = yt_r
            if yt_r.get("ok"):
                yt_url = str(yt_r.get("url") or "")
    elif yt_url:
        report["steps"]["youtube"] = {"ok": True, "url": yt_url, "skipped": "existing"}
    else:
        report["steps"]["youtube"] = {"ok": False, "skipped": True}

    save_manifest_entry(kw, video_path=mp4_path, youtube_url=yt_url)

    # ── 3) 블로그 발행 ──
    blog_r: dict[str, Any] = {"ok": False, "skipped": not publish_blog}
    if publish_blog:
        from integrations.blog_auto_pipeline import run_blog_auto

        store_url = _resolve_store_url(kw)
        _emit(on_status, f"[블로그] 발행 시작 — 영상 첨부 + YouTube 링크")
        blog_r = run_blog_auto(
            kw,
            platforms=platforms,
            publish=True,
            skip_media=False,
            with_video=bool(mp4_path),
            video_path_override=mp4_path,
            youtube_url=yt_url,
            store_url=store_url,
            on_status=on_status,
        )
    report["steps"]["blog"] = blog_r

    # ── 4) 트래픽 ──
    traffic_r: dict[str, Any] = {"ok": False, "skipped": not trigger_traffic}
    if trigger_traffic:
        store_url = _resolve_store_url(kw)
        traffic_r = _run_traffic_once(kw, store_url, on_status)
    report["steps"]["traffic"] = traffic_r

    blog_ok = bool(blog_r.get("ok")) if publish_blog else True
    yt_ok = bool(report["steps"]["youtube"].get("ok")) if upload_youtube and mp4_path else True
    shorts_ok = bool(mp4_path) or not create_video
    report["ok"] = bool(shorts_ok and blog_ok and yt_ok)
    report["finished"] = time.time()
    report["youtube_url"] = yt_url
    report["video_path"] = mp4_path

    save_manifest_entry(kw, video_path=mp4_path, youtube_url=yt_url, blog_ok=blog_ok)
    _emit(on_status, f"\n[파이프라인 완료] ok={report['ok']}")
    if yt_url:
        _emit(on_status, f"  YouTube: {yt_url}")
    return report
