"""
티스토리 메인 페이지(인기글 베스트, 오늘의 티스토리)에서 구독(이웃) 추가 + 댓글 자동화.
- www.tistory.com 에서 블로그/글 링크 수집 → 각 블로그 구독하기 → 각 글에 댓글 등록.
- 오늘 이미 방문·댓글한 블로그/글은 건너뛰고, 내일 실행 시 전날 방문한 글에 좋아요+댓글.
"""
import asyncio
import json
import random
import os
import re
import sys
from datetime import datetime, timedelta
from playwright.async_api import async_playwright

TISTORY_MAIN = "https://www.tistory.com/"
TISTORY_LOGIN = "https://www.tistory.com/auth/login"
MIN_DELAY = 4.0
MAX_DELAY = 9.0
STATE_FILENAME = "tistory_visit_state.json"


async def _delay(a, b):
    await asyncio.sleep(random.uniform(a, b))


def _extract_blog_id(url: str) -> str | None:
    """https://8282ok.tistory.com → 8282ok"""
    if not url:
        return None
    m = re.search(r"https?://([^.]+)\.tistory\.com", url)
    return m.group(1) if m else None


def _normalize_url(url: str) -> str:
    """비교용 URL 정규화 (쿼리/해시 제거)."""
    if not url:
        return ""
    return (url.split("#")[0].split("?")[0] or url).rstrip("/")


def _state_path() -> str:
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), STATE_FILENAME)


def _load_state() -> dict:
    """저장된 방문 이력 로드. { date, blogs_visited, posts_commented }"""
    path = _state_path()
    if not os.path.isfile(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data
    except Exception:
        return {}


def _save_state(
    date: str,
    blogs_visited: list,
    posts_commented: list,
    no_comment_posts: list | None = None,
    comment_success_posts: list | None = None,
) -> None:
    """오늘 날짜 기준으로 방문/댓글 이력 저장.

    - no_comment_posts: 댓글창 없음으로 저장한 글(다음부터 방문 안 함)
    - comment_success_posts: 실제로 댓글 등록까지 완료된 글 (추가 댓글 방지용)
    """
    path = _state_path()
    try:
        payload = {
            "date": date,
            "blogs_visited": list(blogs_visited),
            "posts_commented": list(posts_commented),
            "no_comment_posts": list(no_comment_posts) if no_comment_posts is not None else [],
            "comment_success_posts": list(comment_success_posts) if comment_success_posts is not None else [],
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


async def run_tistory_neighbor_comment(
    t_id: str,
    t_pw: str,
    logger=None,
    status_callback=None,
    max_actions: int = 20,
    min_delay: float = MIN_DELAY,
    max_delay: float = MAX_DELAY,
    messages: list[str] | None = None,
):
    """티스토리 로그인 후 메인 페이지에서 블로그 구독 + 글 댓글 자동화."""
    log = logger or print

    def status(msg: str):
        if status_callback:
            try:
                status_callback(msg)
            except Exception:
                pass

    if not messages:
        messages = [
            "좋은 글 잘 보고 갑니다! 소통해요.",
            "포스팅 잘 보고 갑니다. 오늘도 좋은 하루 보내세요!",
            "유익한 정보네요. 자주 놀러 올게요!",
        ]

    _script_dir = os.path.dirname(os.path.abspath(__file__))
    try:
        os.chdir(_script_dir)
    except Exception:
        pass

    today = datetime.now().strftime("%Y-%m-%d")
    state = _load_state()
    state_date = state.get("date") or ""
    today_blogs = set(_normalize_url(u) for u in state.get("blogs_visited", []) if state_date == today)
    today_posts = set(_normalize_url(u) for u in state.get("posts_commented", []) if state_date == today)
    # 댓글 입력창이 없었던 글 → 다음부터 방문하지 않음 (영구 저장)
    no_comment_posts = set(_normalize_url(u) for u in state.get("no_comment_posts", []))
    # 한 번이라도 댓글을 남긴 글 (중복 댓글 방지용)
    raw_success = state.get("comment_success_posts")
    if raw_success is None:
        # 초기 버전 호환: 예전에는 posts_commented 에 모두 넣었으므로, 일단 중복 댓글 방지를 위해 그대로 사용
        comment_success_posts = set(_normalize_url(u) for u in state.get("posts_commented", []))
    else:
        comment_success_posts = set(_normalize_url(u) for u in raw_success)
    # 전날 방문한 글 목록 → 오늘 실행 시 해당 글에 좋아요+댓글 (댓글창 없음 목록은 제외)
    yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    posts_to_revisit = []
    if state_date == yesterday:
        posts_to_revisit = [u for u in (_normalize_url(x) for x in state.get("posts_commented", [])) if u not in no_comment_posts]
        if posts_to_revisit:
            log(f"전날({state_date}) 방문한 글 {len(posts_to_revisit)}개 재방문 → 좋아요+댓글 예정")

    log("티스토리 브라우저를 엽니다...")
    status("티스토리 실행 중 · 브라우저 여는 중…")

    from playwright_bootstrap import ensure_playwright_ready

    if not ensure_playwright_ready(log):
        raise RuntimeError(
            "Playwright 브라우저를 실행할 수 없습니다. run_fix_playwright.bat 실행 후 재시도하세요."
        )

    async with async_playwright() as p:
        try:
            browser = await p.chromium.launch(
                headless=False,
                slow_mo=150,
                args=["--start-maximized", "--no-first-run", "--disable-blink-features=AutomationControlled"],
                ignore_default_args=["--enable-automation"],
            )
        except Exception:
            browser = await p.chromium.launch(
                headless=False,
                slow_mo=150,
                args=["--start-maximized", "--no-first-run"],
            )
        context = await browser.new_context(no_viewport=True)
        page = await context.new_page()
        await page.bring_to_front()
        log("브라우저가 열렸습니다. 티스토리 로그인 중...")
        status("티스토리 실행 중 · 로그인…")

        # --- 로그인 ---
        await page.goto(TISTORY_LOGIN)
        await _delay(2, 4)
        kakao_btn = page.locator(".txt_login:has-text('카카오계정으로 시작하기'), .btn_login.link_kakao, a:has-text('카카오')").first
        if await kakao_btn.count() > 0 and await kakao_btn.is_visible(timeout=3000):
            await kakao_btn.click()
            await _delay(2, 4)
        log("카카오 로그인 창에서 직접 로그인해 주세요. (최대 5분 대기)")
        try:
            await page.wait_for_url(
                lambda url: "tistory.com" in url and all(x not in url for x in ["auth", "confirm", "security"]),
                timeout=300000,
            )
        except Exception:
            log("로그인 대기 시간이 초과되었습니다.")
            await browser.close()
            return
        log("티스토리 로그인 완료.")

        # --- 전날 방문한 글 재방문: 좋아요 + 댓글 ---
        revisit_done = 0
        if posts_to_revisit:
            status("티스토리 실행 중 · 전날 방문 글 좋아요+댓글…")
            for post_url in posts_to_revisit[:max_actions]:
                log(f"[재방문] 글: {post_url[:60]}...")
                try:
                    await page.goto(post_url, wait_until="domcontentloaded", timeout=15000)
                    await _delay(min_delay, max_delay)
                    post_norm = _normalize_url(post_url)
                    # 좋아요(공감) 버튼
                    like_btn = page.locator(
                        "a:has-text('공감'), button:has-text('공감'), "
                        ".like_btn, .sympathy, [class*='like'], [class*='sympathy'], "
                        "a[href*='like'], a[href*='sympathy']"
                    ).first
                    if await like_btn.count() > 0 and await like_btn.is_visible(timeout=3000):
                        await like_btn.click()
                        await _delay(0.5, 1)
                        log("   ✓ 공감 클릭")
                    # 이미 예전에 댓글을 남긴 글이면 추가 댓글은 남기지 않음
                    if post_norm in comment_success_posts:
                        log("   (이미 댓글을 남긴 글이라, 추가 댓글은 생략합니다)")
                        continue
                    # 댓글 입력
                    textarea = page.locator("textarea#comment, textarea.CommentWriter__textarea, textarea[placeholder*='댓글'], textarea.u_cbox_text").first
                    if await textarea.count() == 0:
                        textarea = page.locator("textarea").first
                    if await textarea.count() > 0 and await textarea.is_visible(timeout=5000):
                        msg = random.choice(messages)
                        await textarea.fill(msg)
                        await _delay(0.5, 1)
                        submit = page.locator(
                            ".u_cbox_btn_upload, button:has-text('댓글 등록'), button:has-text('등록'), "
                            "a.btn_register:has-text('등록'), a:has-text('댓글 등록')"
                        ).first
                        if await submit.count() > 0 and await submit.is_visible(timeout=5000):
                            await submit.click()
                            await _delay(min_delay, max_delay)
                            revisit_done += 1
                            comment_success_posts.add(post_norm)
                            log("   ✓ 좋아요+댓글 완료")
                except Exception as e:
                    log(f"   ✗ 재방문 오류: {e}")
                finally:
                    today_posts.add(_normalize_url(post_url))
                await _delay(min_delay, max_delay)
            if revisit_done:
                log(f"전날 방문 글 재방문 완료: {revisit_done}개 (좋아요+댓글)")

        log("메인 페이지로 이동...")
        status("티스토리 실행 중 · 메인 페이지 수집…")

        # --- 메인 페이지에서 링크 수집 ---
        await page.goto(TISTORY_MAIN, wait_until="domcontentloaded")
        await _delay(2, 4)

        blog_urls = set()
        post_urls = set()

        # 인기글 베스트: .best_popularity .cont_g
        for link in await page.locator("div.best_popularity a.txt_blogname").all():
            try:
                href = await link.get_attribute("href")
                if href and ".tistory.com" in href and _extract_blog_id(href):
                    blog_urls.add(href.split("?")[0].rstrip("/") or href)
            except Exception:
                pass
        for link in await page.locator("div.best_popularity a.link_cont.zoom_cont").all():
            try:
                href = await link.get_attribute("href")
                if href and ".tistory.com" in href:
                    post_urls.add(href.split("#")[0].split("?")[0])
            except Exception:
                pass

        # 오늘의 티스토리: .link_today, .link_profile
        for link in await page.locator("a.link_today").all():
            try:
                href = await link.get_attribute("href")
                if href and ".tistory.com" in href:
                    post_urls.add(href.split("#")[0].split("?")[0])
            except Exception:
                pass
        for link in await page.locator("a.link_profile").all():
            try:
                href = await link.get_attribute("href")
                if href and ".tistory.com" in href and _extract_blog_id(href):
                    blog_urls.add(href.split("?")[0].rstrip("/") or href)
            except Exception:
                pass

        # 카테고리 리스트: .list_tistory_top .link_blog, .link_cont.zoom_cont
        for link in await page.locator("div.list_tistory_top a.link_blog").all():
            try:
                href = await link.get_attribute("href")
                if href and ".tistory.com" in href and _extract_blog_id(href):
                    blog_urls.add(href.split("?")[0].rstrip("/") or href)
            except Exception:
                pass
        for link in await page.locator("div.list_tistory_top a.link_cont.zoom_cont").all():
            try:
                href = await link.get_attribute("href")
                if href and ".tistory.com" in href:
                    post_urls.add(href.split("#")[0].split("?")[0])
            except Exception:
                pass

        blog_list = list(blog_urls)[:max_actions]
        post_list = list(post_urls)[:max_actions]
        log(f"수집: 블로그 {len(blog_list)}개, 글 {len(post_list)}개 (최대 {max_actions}개씩 처리)")

        subs_done = 0
        comments_done = 0

        # 1) 블로그 구독하기 (오늘 이미 방문·구독한 블로그는 건너뜀)
        for i, blog_url in enumerate(blog_list):
            if subs_done >= max_actions:
                break
            blog_norm = _normalize_url(blog_url)
            if blog_norm in today_blogs:
                log(f"블로그 방문: {blog_url}")
                log("   (이미 오늘 방문함, 건너뜀)")
                continue
            status(f"티스토리 실행 중 · 구독하기 ({i+1}/{len(blog_list)})…")
            log(f"블로그 방문: {blog_url}")
            try:
                await page.goto(blog_url, wait_until="domcontentloaded", timeout=15000)
                await _delay(min_delay, max_delay)
                # 구독하기 버튼: 텍스트로 찾기 (구독하기 / 구독중)
                sub_btn = page.locator("a:has-text('구독하기'), button:has-text('구독하기'), .btn_subscribe, a[href*='subscribe']").first
                if await sub_btn.count() > 0 and await sub_btn.is_visible(timeout=3000):
                    btn_text = await sub_btn.inner_text()
                    if "구독하기" in btn_text and "구독중" not in btn_text:
                        await sub_btn.click()
                        await _delay(1, 2)
                        subs_done += 1
                        log(f"   ✓ 구독 완료 (누적 {subs_done}개)")
                    else:
                        log("   (이미 구독 중이거나 버튼 없음)")
                else:
                    log("   (이미 구독 중이거나 버튼 없음)")
                today_blogs.add(blog_norm)
            except Exception as e:
                log(f"   ✗ 오류: {e}")
                today_blogs.add(blog_norm)
            await _delay(min_delay, max_delay)

        # 2) 글 댓글 달기 (오늘 이미 댓글한 글·댓글창 없음 저장 글은 건너뜀)
        for i, post_url in enumerate(post_list):
            if comments_done >= max_actions:
                break
            post_norm = _normalize_url(post_url)
            if post_norm in no_comment_posts:
                log(f"글 방문: {post_url[:60]}...")
                log("   (댓글창 없음으로 저장된 글, 건너뜀)")
                continue
            if post_norm in today_posts:
                log(f"글 방문: {post_url[:60]}...")
                log("   (이미 오늘 댓글함, 건너뜀)")
                continue
            status(f"티스토리 실행 중 · 댓글 작성 ({i+1}/{len(post_list)})…")
            log(f"글 방문: {post_url[:60]}...")
            try:
                await page.goto(post_url, wait_until="domcontentloaded", timeout=15000)
                await _delay(min_delay, max_delay)
                # 댓글 입력창: textarea (댓글쓰기 영역)
                textarea = page.locator("textarea#comment, textarea.CommentWriter__textarea, textarea[placeholder*='댓글'], textarea.u_cbox_text").first
                if await textarea.count() == 0:
                    textarea = page.locator("textarea").first
                if await textarea.count() > 0 and await textarea.is_visible(timeout=5000):
                    msg = random.choice(messages)
                    await textarea.fill(msg)
                    await _delay(0.5, 1)
                    # 댓글 등록 버튼만 클릭 (button[type=submit] 사용 안 함 → 상단 '검색' 버튼과 겹침 방지)
                    submit = page.locator(
                        ".u_cbox_btn_upload, "
                        "button:has-text('댓글 등록'), "
                        "button:has-text('등록'), "
                        "a.btn_register:has-text('등록'), "
                        "a:has-text('댓글 등록')"
                    ).first
                    if await submit.count() > 0 and await submit.is_visible(timeout=5000):
                        await submit.click()
                        await _delay(min_delay, max_delay)
                        comments_done += 1
                        comment_success_posts.add(post_norm)
                        log(f"   ✓ 댓글 등록 완료 (누적 {comments_done}개)")
                    else:
                        log("   (등록 버튼을 찾지 못함)")
                else:
                    no_comment_posts.add(post_norm)
                    log("   (댓글 입력창 없음 → 저장함, 다음부터 방문 안 함)")
                today_posts.add(post_norm)
            except Exception as e:
                log(f"   ✗ 오류: {e}")
                today_posts.add(post_norm)
            await _delay(min_delay, max_delay)

        _save_state(today, today_blogs, today_posts, no_comment_posts, comment_success_posts)
        log(f"티스토리 작업 완료. 구독 {subs_done}개, 댓글 {comments_done}개. (오늘 방문 {len(today_blogs)}블로그, 댓글 {len(today_posts)}글 기록)")
        status("티스토리 실행 중 · 완료")
        await _delay(1, 2)
        await browser.close()
