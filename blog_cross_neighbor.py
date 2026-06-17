# -*- coding: utf-8 -*-
"""네이버 블로그 서로이웃 신청 + 지정 이웃 최신 글 답글."""

from __future__ import annotations

import asyncio
import random
import sys
from typing import Callable

from playwright.async_api import Page, async_playwright

LogFn = Callable[[str], None]


async def _human_delay(lo: float, hi: float) -> None:
    await asyncio.sleep(random.uniform(lo, hi))


async def _naver_login(page: Page, naver_id: str, naver_pw: str, log: LogFn) -> bool:
    log(f"   🔑 네이버 로그인: {naver_id}")
    await page.goto("https://nid.naver.com/nidlogin.login", wait_until="domcontentloaded")
    await asyncio.sleep(1.5)
    await page.fill("#id", naver_id)
    await page.fill("#pw", naver_pw)
    await page.click(".btn_login, #log\\.login")
    await asyncio.sleep(4)
    if "nid.naver.com" in page.url:
        log("   ⚠️ 로그인 페이지에 머물러 있습니다. 열린 브라우저에서 2단계 인증·캡차를 완료해 주세요 (최대 3분).")
        try:
            await page.wait_for_url(
                lambda u: "naver.com" in u and "nid.naver.com" not in u,
                timeout=180_000,
            )
            log("   ✓ 로그인 완료")
        except Exception:
            return False
    return True


async def request_mutual_neighbor(
    page: Page,
    target_blog_id: str,
    message: str,
    log: LogFn,
) -> bool:
    """대상 블로그에 서로이웃 신청 (이미 이웃이면 스킵)."""
    target = (target_blog_id or "").strip()
    if not target:
        return False

    urls = [
        f"https://blog.naver.com/BuddyAddForm.naver?blogId={target}",
        f"https://blog.naver.com/BlogNeighborAdd.naver?blogId={target}",
        f"https://blog.naver.com/{target}",
    ]
    for url in urls:
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=25_000)
            await asyncio.sleep(2)

            body = (await page.locator("body").inner_text(timeout=5000) or "").lower()
            if any(x in body for x in ("이미 이웃", "이웃입니다", "서로이웃 중", "신청 대기")):
                log(f"   ✓ [{target}] 이미 이웃이거나 신청 대기 중 — 스킵")
                return True

            buddy_btn = page.locator(
                "a:has-text('이웃추가'), button:has-text('이웃추가'), a.btn_buddyadd"
            ).first
            if await buddy_btn.count() > 0 and await buddy_btn.is_visible(timeout=3000):
                await buddy_btn.click()
                await asyncio.sleep(1.5)

            both_radio = page.locator(
                "input[type='radio'][value='both'], "
                "input[type='radio'][value='2'], "
                "label:has-text('서로이웃') input"
            ).first
            if await both_radio.count() > 0:
                await both_radio.click()
                await asyncio.sleep(0.5)

            msg_box = page.locator(
                "#message, textarea[name='message'], textarea.buddy_msg"
            ).first
            if await msg_box.count() > 0:
                await msg_box.fill(message[:300])

            submit = page.locator(
                "#buddyAddSubmit, button:has-text('확인'), button:has-text('신청'), "
                "input[type='submit'][value*='확인']"
            ).first
            if await submit.count() > 0 and await submit.is_visible(timeout=3000):
                await submit.click()
                await asyncio.sleep(2)
                log(f"   ✓ [{target}] 서로이웃 신청 완료")
                return True

            if "BuddyAddForm" in url or "BlogNeighborAdd" in url:
                if await page.locator("text=신청").count() > 0:
                    log(f"   ✓ [{target}] 이웃 신청 화면 처리됨")
                    return True
        except Exception as exc:
            log(f"   · 이웃 신청 URL 시도 실패 ({url[:50]}…): {exc}")
    log(f"   ⚠️ [{target}] 서로이웃 신청을 완료하지 못했습니다. 수동 확인이 필요할 수 있습니다.")
    return False


async def comment_on_latest_post(
    page: Page,
    target_blog_id: str,
    messages: list[str],
    log: LogFn,
    min_delay: float = 4.0,
    max_delay: float = 9.0,
) -> bool:
    """이웃 블로그 최신 글에 공감·답글."""
    target = (target_blog_id or "").strip()
    if not target or not messages:
        return False

    list_url = f"https://blog.naver.com/PostList.naver?blogId={target}&from=postList"
    await page.goto(list_url, wait_until="domcontentloaded", timeout=25_000)
    await _human_delay(min_delay, max_delay)

    post_link = page.locator(
        "a.link_title, a.title, .post_list a.pcol2, #postListBody a"
    ).first
    if await post_link.count() == 0:
        post_link = page.locator(f"a[href*='blog.naver.com/{target}/']").first
    if await post_link.count() == 0:
        log(f"   ⚠️ [{target}] 최신 글 링크를 찾지 못했습니다.")
        return False

    href = await post_link.get_attribute("href")
    if href:
        if href.startswith("//"):
            href = "https:" + href
        elif href.startswith("/"):
            href = "https://blog.naver.com" + href
        await page.goto(href, wait_until="domcontentloaded", timeout=20_000)
    else:
        await post_link.click()
    await _human_delay(min_delay, max_delay)

    has_frame = await page.locator("#mainFrame").count() > 0
    frame = page.frame_locator("#mainFrame") if has_frame else page

    like_btn = frame.locator(".u_likeit_button, .blog_like_area a.u_likeit_button").first
    if await like_btn.count() > 0 and await like_btn.is_visible(timeout=3000):
        try:
            await like_btn.click()
            await asyncio.sleep(0.8)
            layer = page.locator("a.u_likeit_list_button[data-type='like']").first
            if await layer.count() > 0 and await layer.is_visible(timeout=1500):
                await layer.click()
        except Exception:
            pass

    comment_box = frame.locator(".u_cbox_text").first
    if await comment_box.count() == 0:
        open_c = page.locator("a:has-text('댓글'), button:has-text('댓글')").first
        if await open_c.count() > 0:
            await open_c.click()
            await asyncio.sleep(1.5)
            comment_box = frame.locator(".u_cbox_text").first

    if await comment_box.count() == 0 or not await comment_box.is_visible(timeout=5000):
        log(f"   ⚠️ [{target}] 댓글 입력창이 없습니다.")
        return False

    text = random.choice(messages)
    await comment_box.fill(text)
    await asyncio.sleep(0.5)
    upload = frame.locator(".u_cbox_btn_upload").first
    if await upload.count() == 0:
        upload = page.locator(".u_cbox_btn_upload").first
    await upload.click()
    await _human_delay(min_delay, max_delay)
    log(f"   ✓ [{target}] 최신 글 답글 등록")
    return True


async def subscribe_tistory_blog(
    page: Page,
    blog_url: str,
    log: LogFn,
    min_delay: float = 4.0,
    max_delay: float = 9.0,
) -> bool:
    """티스토리 블로그 URL에서 구독하기 (이미 구독 중이면 스킵)."""
    url = (blog_url or "").strip().rstrip("/")
    if not url or ".tistory.com" not in url:
        return False
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=25_000)
        await _human_delay(min_delay, max_delay)
        sub_btn = page.locator(
            "a:has-text('구독하기'), button:has-text('구독하기'), "
            ".btn_subscribe, a[href*='subscribe']"
        ).first
        if await sub_btn.count() > 0 and await sub_btn.is_visible(timeout=4000):
            btn_text = (await sub_btn.inner_text() or "").strip()
            if "구독하기" in btn_text and "구독중" not in btn_text:
                await sub_btn.click()
                await _human_delay(1.0, 2.0)
                log(f"   ✓ 티스토리 구독 완료: {url}")
                return True
        body = (await page.locator("body").inner_text(timeout=5000) or "").lower()
        if "구독중" in body or "구독 취소" in body:
            log(f"   ✓ 티스토리 이미 구독 중: {url}")
            return True
        log(f"   · 티스토리 구독 버튼 없음 (로그인 필요할 수 있음): {url}")
    except Exception as exc:
        log(f"   ⚠️ 티스토리 구독 실패 ({url}): {exc}")
    return False


async def run_account_cross_tasks(
    naver_id: str,
    naver_pw: str,
    actor_blog_id: str,
    neighbor_targets: list[str],
    comment_targets: list[str],
    neighbor_message: str,
    reply_messages: list[str],
    log: LogFn,
    min_delay: float = 4.0,
    max_delay: float = 9.0,
    tistory_subscribe_urls: list[str] | None = None,
) -> None:
    """한 네이버 계정으로 서로이웃 + 지정 블로그 답글."""
    from playwright_bootstrap import ensure_playwright_ready

    if not ensure_playwright_ready(log):
        raise RuntimeError(
            "Playwright 브라우저를 실행할 수 없습니다. run_fix_playwright.bat 실행 후 재시도하세요."
        )
    async with async_playwright() as p:
        browser = None
        try:
            browser = await p.chromium.launch(
                headless=False,
                slow_mo=120,
                args=["--start-maximized", "--disable-blink-features=AutomationControlled"],
                ignore_default_args=["--enable-automation"],
            )
        except Exception:
            browser = await p.chromium.launch(channel="chrome", headless=False, slow_mo=120)

        context = await browser.new_context(no_viewport=True)
        page = await context.new_page()
        try:
            if not await _naver_login(page, naver_id, naver_pw, log):
                log(f"   ❌ [{naver_id}] 로그인 실패 — 교차 이웃·답글 중단")
                return

            log(f"   🤝 [{actor_blog_id}] 서로이웃 신청 ({len(neighbor_targets)}곳)")
            for tgt in neighbor_targets:
                await request_mutual_neighbor(page, tgt, neighbor_message, log)
                await _human_delay(min_delay, max_delay)

            log(f"   💬 [{actor_blog_id}] 이웃 최신 글 답글 ({len(comment_targets)}곳)")
            for tgt in comment_targets:
                await comment_on_latest_post(
                    page, tgt, reply_messages, log, min_delay, max_delay
                )

            for t_url in tistory_subscribe_urls or []:
                await subscribe_tistory_blog(page, t_url, log, min_delay, max_delay)
        finally:
            try:
                await browser.close()
            except Exception:
                pass


def run_cross_neighbor_sync(
    naver_id: str,
    naver_pw: str,
    actor_blog_id: str,
    neighbor_targets: list[str],
    comment_targets: list[str],
    neighbor_message: str,
    reply_messages: list[str],
    log: LogFn | None = None,
    min_delay: float = 4.0,
    max_delay: float = 9.0,
    tistory_subscribe_urls: list[str] | None = None,
) -> None:
    """동기 래퍼 (GUI·배치 스크립트용)."""
    logger = log or print

    def _safe(msg: str) -> None:
        try:
            logger(msg)
        except Exception:
            try:
                logger(str(msg).encode("ascii", errors="replace").decode("ascii"))
            except Exception:
                pass

    if sys.platform == "win32":
        try:
            asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
        except Exception:
            pass
    asyncio.run(
        run_account_cross_tasks(
            naver_id,
            naver_pw,
            actor_blog_id,
            neighbor_targets,
            comment_targets,
            neighbor_message,
            reply_messages,
            _safe,
            min_delay,
            max_delay,
            tistory_subscribe_urls,
        )
    )
