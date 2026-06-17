# -*- coding: utf-8
"""Google Blogger — 수동 Google 로그인 후 자동 글쓰기."""

from __future__ import annotations

import time
from typing import Any, Callable

from integrations.blog_auto_login import ensure_logged_in
from integrations.blog_browser_base import (
    launch_context,
    plain_body,
    upload_files_input,
)


def _is_google_login(url: str) -> bool:
    u = (url or "").lower()
    return "accounts.google.com" in u and ("signin" in u or "login" in u or "oauth" in u)


def login_blogger(*, on_status: Callable[[str], None] | None = None) -> dict[str, Any]:
    emit = on_status or print
    p, ctx, page = launch_context("blogger")
    try:
        page.goto("https://www.blogger.com/", wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(2000)
        if _is_google_login(page.url):
            r = ensure_logged_in("blogger", page, is_login_url=_is_google_login, on_status=emit)
        else:
            r = {"ok": True, "already_logged_in": True}
        return {**r, "platform": "blogger", "url": page.url}
    finally:
        emit("[Blogger] 세션 저장을 위해 10초 후 브라우저 종료...")
        page.wait_for_timeout(10000)
        ctx.close()
        p.stop()


def publish_blogger(
    *,
    title: str,
    body_html: str,
    tags: list[str] | None = None,
    image_paths: list[str] | None = None,
    video_path: str = "",
    on_status: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    emit = on_status or print
    tags = tags or []
    images = list(image_paths or [])
    body_plain = plain_body(body_html)

    p, ctx, page = launch_context("blogger")
    try:
        emit("[Blogger] 대시보드 이동...")
        page.goto("https://www.blogger.com/", wait_until="domcontentloaded", timeout=90000)
        page.wait_for_timeout(2500)

        if _is_google_login(page.url):
            lr = ensure_logged_in("blogger", page, is_login_url=_is_google_login, on_status=emit)
            if not lr.get("ok"):
                return {"ok": False, "platform": "blogger", "error": "로그인 필요", "login": lr}

        # 새 글
        for sel in (
            "a:has-text('New post')",
            "a:has-text('새 게시물')",
            "a:has-text('글 작성')",
            "[aria-label*='New post']",
        ):
            try:
                loc = page.locator(sel).first
                if loc.count() > 0:
                    loc.click(timeout=8000)
                    page.wait_for_timeout(3000)
                    break
            except Exception:
                continue

        # 제목
        for sel in ("input[aria-label*='Title']", "input[placeholder*='Title']", "textarea[aria-label*='Title']"):
            try:
                loc = page.locator(sel).first
                if loc.count() > 0:
                    loc.fill(title[:200])
                    break
            except Exception:
                continue

        # 본문
        for sel in (
            "[aria-label*='Compose']",
            ".CodeMirror",
            "[contenteditable='true']",
            "iframe[title*='Editor']",
        ):
            try:
                if "iframe" in sel:
                    fl = page.frame_locator(sel).first
                    fl.locator("body").click(timeout=4000)
                else:
                    page.locator(sel).first.click(timeout=4000)
                try:
                    import pyperclip

                    pyperclip.copy(body_plain)
                except Exception:
                    page.evaluate("(t)=>navigator.clipboard.writeText(t)", body_plain)
                page.keyboard.press("Control+V")
                break
            except Exception:
                continue

        # 이미지·영상
        all_media = images + ([video_path] if video_path else [])
        if all_media:
            emit(f"[Blogger] 미디어 {len(all_media)}개 업로드 시도...")
            for sel in ("button[aria-label*='Insert image']", "button:has-text('Image')", "input[type='file']"):
                try:
                    if "file" in sel:
                        upload_files_input(page, all_media, input_selector=sel)
                        break
                    page.locator(sel).first.click(timeout=3000)
                    upload_files_input(page, all_media)
                    break
                except Exception:
                    continue

        if tags:
            for sel in ("input[aria-label*='Labels']", "input[placeholder*='Labels']"):
                try:
                    page.locator(sel).first.fill(",".join(tags[:20]))
                    break
                except Exception:
                    continue

        published = False
        for sel in ("button:has-text('Publish')", "button:has-text('게시')", "[aria-label*='Publish']"):
            try:
                btn = page.locator(sel).first
                if btn.count() > 0 and btn.is_visible():
                    btn.click(timeout=5000)
                    page.wait_for_timeout(1500)
                    confirm = page.locator("button:has-text('Publish'), button:has-text('게시')").last
                    if confirm.count() > 0:
                        confirm.click(timeout=3000)
                    published = True
                    break
            except Exception:
                continue

        emit(f"[Blogger] {'게시 클릭' if published else '작성 완료 — 게시 확인'}")
        return {
            "ok": bool(published),
            "platform": "blogger",
            "published_clicked": published,
            "url": page.url,
        }
    except Exception as e:
        return {"ok": False, "platform": "blogger", "error": str(e)}
    finally:
        ctx.close()
        p.stop()
