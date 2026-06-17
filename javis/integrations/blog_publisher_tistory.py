# -*- coding: utf-8 -*-
"""티스토리 — Playwright 세션 + manage API 발행 (Alpha Autoblog / viruagent 패턴)."""

from __future__ import annotations

import time
from typing import Any, Callable

from integrations.blog_auto_login import ensure_logged_in
from integrations.blog_browser_base import (
    launch_context,
    paste_plain_text,
    plain_body,
    strip_underline_html,
    upload_files_input,
)
from integrations.blog_credentials import get_platform_creds
from integrations.tistory_api_client import (
    TistoryApiClient,
    client_from_playwright_cookies,
    embed_images_in_html,
    map_visibility,
    normalize_tags,
)


def _cfg_tistory() -> dict[str, Any]:
    import json
    from pathlib import Path

    p = Path(__file__).resolve().parent.parent / "config" / "blog_automation.json"
    try:
        cfg = json.loads(p.read_text(encoding="utf-8"))
        return (cfg.get("platforms") or {}).get("tistory") or {}
    except Exception:
        return {}


def _is_login_url(url: str) -> bool:
    u = (url or "").lower()
    return ("tistory" in u) and ("login" in u or "auth" in u or "signin" in u)


def _resolve_category_id(api: TistoryApiClient, emit: Callable[[str], None]) -> int:
    tc = _cfg_tistory()
    creds = get_platform_creds("tistory")
    raw = creds.get("category_id") or creds.get("category") or tc.get("category_id")
    if raw is not None and str(raw).strip().isdigit():
        return int(raw)

    cats = api.get_categories()
    if not cats:
        emit("[티스토리] 카테고리 없음 — category_id=0")
        return 0
    if len(cats) == 1:
        cid = next(iter(cats.values()))
        emit(f"[티스토리] 카테고리 자동: {cid}")
        return int(cid)

    preferred = (creds.get("category_name") or tc.get("category_name") or "").strip()
    if preferred and preferred in cats:
        emit(f"[티스토리] 카테고리 '{preferred}' → {cats[preferred]}")
        return int(cats[preferred])

    first_name, first_id = next(iter(cats.items()))
    emit(f"[티스토리] 카테고리 기본값 '{first_name}' ({first_id}) — blog_credentials에 category_id 지정 권장")
    return int(first_id)


def _goto_tistory_write(page: Any, emit: Callable[[str], None]) -> None:
    candidates = (
        "https://www.tistory.com/guide/manage/newpost/",
        "https://www.tistory.com/manage/newpost/",
        "https://www.tistory.com/",
    )
    last_error: Exception | None = None
    for url in candidates:
        try:
            emit(f"[티스토리] 이동: {url}")
            page.goto(url, wait_until="domcontentloaded", timeout=90000)
            page.wait_for_timeout(1800)
            cur = (page.url or "").lower()
            if "newpost" in cur or "manage" in cur or "tistory.com" in cur:
                return
        except Exception as e:
            last_error = e
            continue
    if last_error:
        raise last_error


def publish_tistory_via_api(
    *,
    title: str,
    body_html: str,
    tags: list[str] | None = None,
    image_paths: list[str] | None = None,
    on_status: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    """manage API로 발행 — UI 클릭 없이 제목·HTML·태그·이미지·썸네일 처리."""
    emit = on_status or print
    tags = tags or []
    images = [str(p) for p in (image_paths or []) if p]
    tc = _cfg_tistory()
    creds = get_platform_creds("tistory")
    use_api = tc.get("use_api_publish", True)
    if use_api is False:
        return {"ok": False, "skipped": True, "reason": "use_api_publish=false"}

    p, ctx, page = launch_context("tistory")
    try:
        page.goto("https://www.tistory.com/", wait_until="domcontentloaded", timeout=60000)
        if _is_login_url(page.url):
            lr = ensure_logged_in("tistory", page, is_login_url=_is_login_url, on_status=emit)
            if not lr.get("ok"):
                return {"ok": False, "platform": "tistory", "error": "로그인 필요", "login": lr}

        cookies = ctx.cookies()
        blog_name = (creds.get("blog_name") or tc.get("blog_name") or "").strip()
        api = client_from_playwright_cookies(cookies, blog_name=blog_name)
        name = api.init_blog(preferred_name=blog_name)
        emit(f"[티스토리] API 발행 — 블로그 {name}.tistory.com")

        uploads: list[dict[str, Any]] = []
        for i, img in enumerate(images[:5]):
            try:
                up = api.upload_image(img)
                uploads.append(up)
                emit(f"[티스토리] 이미지 업로드 {i + 1}/{min(len(images), 5)}")
            except Exception as e:
                emit(f"[티스토리] 이미지 업로드 실패 ({img}): {e}")

        content = embed_images_in_html(strip_underline_html(body_html), uploads)
        category_id = _resolve_category_id(api, emit)
        visibility = map_visibility(creds.get("visibility") or tc.get("visibility") or "public")
        tag_str = normalize_tags(tags)
        thumbnail = None
        if uploads:
            thumbnail = uploads[0].get("url")

        result = api.publish_post(
            title=title,
            content=content,
            visibility=visibility,
            category=category_id,
            tag=tag_str,
            thumbnail=thumbnail,
        )

        entry_url = (
            result.get("entryUrl")
            or result.get("url")
            or (f"https://{name}.tistory.com" if name else "")
        )
        fallback_private = bool(result.get("_fallback_private"))
        if fallback_private:
            emit("[티스토리] 공개 한도(403) — 비공개로 발행됨")

        emit(f"[티스토리] API 발행 완료 — {entry_url}")
        return {
            "ok": True,
            "platform": "tistory",
            "method": "api",
            "blog_name": name,
            "published_clicked": True,
            "url": entry_url,
            "visibility": visibility,
            "category_id": category_id,
            "image_count": len(uploads),
            "fallback_private": fallback_private,
            "raw": result,
        }
    except Exception as e:
        emit(f"[티스토리] API 발행 실패: {e}")
        return {"ok": False, "platform": "tistory", "method": "api", "error": str(e)}
    finally:
        ctx.close()
        p.stop()


def publish_tistory_via_dom(
    *,
    title: str,
    body_html: str,
    tags: list[str] | None = None,
    image_paths: list[str] | None = None,
    video_path: str = "",
    on_status: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    """DOM 자동화 폴백 — API 실패 시."""
    emit = on_status or print
    tags = tags or []
    images = list(image_paths or [])

    p, ctx, page = launch_context("tistory")
    try:
        emit("[티스토리] DOM 폴백 — 글쓰기 페이지 이동...")
        _goto_tistory_write(page, emit)

        if _is_login_url(page.url):
            lr = ensure_logged_in("tistory", page, is_login_url=_is_login_url, on_status=emit)
            if not lr.get("ok"):
                return {"ok": False, "platform": "tistory", "error": "로그인 필요", "login": lr}
            _goto_tistory_write(page, emit)

        for sel in ("#post-title-inp", "input[placeholder*='제목']", "textarea[placeholder*='제목']"):
            try:
                loc = page.locator(sel).first
                if loc.count() > 0:
                    loc.click(timeout=3000)
                    loc.fill(title[:200])
                    break
            except Exception:
                continue

        body_plain = plain_body(body_html)
        clicked = False
        for sel in (
            ".mce-content-body",
            "[contenteditable='true']",
            "iframe[id*='editor']",
            "#editor-tistory",
        ):
            try:
                if "iframe" in sel:
                    frame = page.frame_locator(sel).first
                    frame.locator("body").click(timeout=3000)
                    paste_plain_text(page, body_plain, strip_underline=True)
                    clicked = True
                    break
                loc = page.locator(sel).first
                if loc.count() > 0:
                    loc.click(timeout=3000)
                    paste_plain_text(page, body_plain, strip_underline=True)
                    clicked = True
                    break
            except Exception:
                continue

        if not clicked:
            emit("[티스토리] 에디터 자동 클릭 실패 — 클립보드에 본문 복사")
            try:
                import pyperclip

                pyperclip.copy(body_plain)
            except Exception:
                pass

        if images:
            emit(f"[티스토리] 이미지 {len(images)}장 업로드 시도...")
            upload_files_input(page, images)

        if video_path:
            emit("[티스토리] 동영상 업로드 시도...")
            upload_files_input(page, [video_path])

        if tags:
            tag_str = ",".join(tags[:10])
            for sel in ("#tagText", "input[name='tag']", "input[placeholder*='태그']"):
                try:
                    loc = page.locator(sel).first
                    if loc.count() > 0:
                        loc.fill(tag_str)
                        break
                except Exception:
                    continue

        published = False
        for sel in (
            "button:has-text('완료')",
            "button:has-text('발행')",
            "button:has-text('공개')",
            "#publish-layer-btn",
            "a:has-text('발행')",
        ):
            try:
                btn = page.locator(sel).first
                if btn.count() > 0 and btn.is_visible():
                    btn.click(timeout=5000)
                    page.wait_for_timeout(1500)
                    for confirm in (
                        "button:has-text('공개 발행')",
                        "button:has-text('발행')",
                        "button:has-text('확인')",
                    ):
                        try:
                            c = page.locator(confirm).first
                            if c.count() > 0 and c.is_visible():
                                c.click(timeout=4000)
                                page.wait_for_timeout(1500)
                                break
                        except Exception:
                            continue
                    published = True
                    break
            except Exception:
                continue

        emit(f"[티스토리] DOM {'발행 클릭' if published else '작성만 — 발행 수동 확인'}")
        time.sleep(2)
        return {
            "ok": bool(published),
            "platform": "tistory",
            "method": "dom",
            "published_clicked": published,
            "url": page.url,
            "note": "티스토리 UI 변경 시 발행 버튼을 수동 확인하세요.",
        }
    except Exception as e:
        return {"ok": False, "platform": "tistory", "method": "dom", "error": str(e)}
    finally:
        ctx.close()
        p.stop()


def login_tistory(*, on_status: Callable[[str], None] | None = None) -> dict[str, Any]:
    emit = on_status or print
    p, ctx, page = launch_context("tistory")
    try:
        page.goto("https://www.tistory.com/auth/login", wait_until="domcontentloaded", timeout=60000)
        r = ensure_logged_in("tistory", page, is_login_url=_is_login_url, on_status=emit)
        if r.get("ok"):
            try:
                api = client_from_playwright_cookies(ctx.cookies())
                name = api.init_blog()
                emit(f"[티스토리] API 세션 확인 — {name}.tistory.com")
                r["blog_name"] = name
            except Exception as e:
                emit(f"[티스토리] API 세션 확인 실패 (DOM만 가능): {e}")
        return {**r, "platform": "tistory", "url": page.url}
    finally:
        ctx.close()
        p.stop()


def _publish_tistory_impl(
    *,
    title: str,
    body_html: str,
    tags: list[str] | None = None,
    image_paths: list[str] | None = None,
    video_path: str = "",
    on_status: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    emit = on_status or print
    api_result = publish_tistory_via_api(
        title=title,
        body_html=body_html,
        tags=tags,
        image_paths=image_paths,
        on_status=emit,
    )
    if api_result.get("ok"):
        return api_result

    if api_result.get("skipped"):
        emit("[티스토리] API 비활성 — DOM 발행")
    else:
        emit("[티스토리] API 실패 — DOM 폴백 시도")

    dom_result = publish_tistory_via_dom(
        title=title,
        body_html=body_html,
        tags=tags,
        image_paths=image_paths,
        video_path=video_path,
        on_status=emit,
    )
    dom_result["api_attempt"] = api_result
    return dom_result


def publish_tistory(
    *,
    title: str,
    body_html: str,
    tags: list[str] | None = None,
    image_paths: list[str] | None = None,
    video_path: str = "",
    on_status: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    """Alpha Autoblog 방식: API 우선 → 실패 시 DOM 폴백 (asyncio 환경에서도 동작)."""
    from integrations.blog_browser_base import run_sync_playwright_job

    return run_sync_playwright_job(
        lambda: _publish_tistory_impl(
            title=title,
            body_html=body_html,
            tags=tags,
            image_paths=image_paths,
            video_path=video_path,
            on_status=on_status,
        )
    )
