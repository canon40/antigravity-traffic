"""
블로그 방문·공감(좋아요)·댓글 자동화 (Playwright).
네이버: 이웃 새글(section.blog.naver.com)에서 각 글마다 공감 클릭 → 댓글 링크로 이동해 댓글 작성 → 목록 복귀, 페이지네이션(다음)으로 다음 페이지 반복.
- 오늘 이미 방문·댓글한 글은 건너뛰고, 내일 실행 시 전날 방문한 글에 좋아요+댓글. 댓글창 없음 글은 저장 후 다음부터 방문 안 함.
브라우저는 항상 화면에 보이도록 실행됩니다 (headless=False).
"""
import asyncio
import csv
import json
import random
import os
import sys
from datetime import datetime, timedelta
from playwright.async_api import async_playwright

# --- 리스크/휴먼라이크 컨트롤 상수 ---
MAX_ACTIONS_PER_DAY = 20
MIN_DELAY = 4.0
MAX_DELAY = 9.0
ERROR_THRESHOLD = 0.2

# --- 액션 로그 파일 ---
LOG_FILE = os.path.join(os.path.dirname(__file__), "neighbor_actions.csv")
NAVER_STATE_FILENAME = "naver_visit_state.json"


def _normalize_naver_url(url: str) -> str:
    """비교용 URL 정규화 (쿼리/해시 제거). blog.naver.com/xxx/222?copen=1 → blog.naver.com/xxx/222"""
    if not url:
        return ""
    u = (url.split("#")[0].split("?")[0] or url).rstrip("/")
    if u.startswith("//"):
        u = "https:" + u
    elif u.startswith("/"):
        u = "https://blog.naver.com" + u
    return u


def _naver_state_path() -> str:
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), NAVER_STATE_FILENAME)


def _load_naver_state(account_id: str) -> dict:
    """해당 계정의 저장된 방문 이력 로드."""
    path = _naver_state_path()
    if not os.path.isfile(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get("accounts", {}).get(account_id, {})
    except Exception:
        return {}


def _save_naver_state(
    account_id: str,
    date: str,
    posts_visited: list,
    posts_commented: list,
    no_comment_posts: list | None = None,
    comment_success_posts: list | None = None,
) -> None:
    """해당 계정의 오늘 날짜 기준 방문/댓글 이력 저장 (계정별로 병합)."""
    path = _naver_state_path()
    try:
        all_data = {}
        if os.path.isfile(path):
            with open(path, "r", encoding="utf-8") as f:
                all_data = json.load(f)
        accounts = all_data.get("accounts", {})
        accounts[account_id] = {
            "date": date,
            "posts_visited": list(posts_visited),
            "posts_commented": list(posts_commented),
            "no_comment_posts": list(no_comment_posts) if no_comment_posts is not None else [],
            "comment_success_posts": list(comment_success_posts) if comment_success_posts is not None else [],
        }
        all_data["accounts"] = accounts
        with open(path, "w", encoding="utf-8") as f:
            json.dump(all_data, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


class RiskControl:
    def __init__(self, max_actions: int, error_threshold: float = ERROR_THRESHOLD):
        self.max_actions = max_actions
        self.error_threshold = error_threshold
        self.actions = 0
        self.errors = 0

    def record_action(self) -> None:
        self.actions += 1

    def record_error(self) -> None:
        self.errors += 1

    def should_stop(self) -> bool:
        if self.actions >= self.max_actions:
            return True
        if self.actions > 0 and (self.errors / self.actions) > self.error_threshold:
            return True
        return False


async def human_delay(min_delay: float = MIN_DELAY, max_delay: float = MAX_DELAY) -> None:
    """사람처럼 랜덤 딜레이."""
    await asyncio.sleep(random.uniform(min_delay, max_delay))


async def smart_delay(min_s=3, max_s=7):
    """고정 범위 지연(짧은 대기용)."""
    await asyncio.sleep(random.uniform(min_s, max_s))


async def random_scroll(page) -> None:
    """사람처럼 중간중간 스크롤."""
    height = random.randint(200, 800)
    try:
        await page.mouse.wheel(0, height)
    except Exception:
        pass


async def run_blog_automation_for_account(
    naver_id: str,
    naver_pw: str,
    logger=None,
    max_actions: int | None = None,
    min_delay: float | None = None,
    max_delay: float | None = None,
    messages: list[str] | None = None,
    status_callback=None,
):
    """단일 네이버 계정에 대해 이웃 새글 공감/댓글 자동화를 수행한다.

    logger: callable(str)를 넘기면 print 대신 사용 (GUI 통합용).
    status_callback: callable(str) — GUI에 현재 작업 메시지를 넘길 때 사용 (메인 스레드 갱신은 호출 측에서 처리).
    """
    n_max_actions = max_actions or MAX_ACTIONS_PER_DAY
    n_min_delay = min_delay or MIN_DELAY
    n_max_delay = max_delay or MAX_DELAY

    def status(msg: str):
        if status_callback:
            try:
                status_callback(msg)
            except Exception:
                pass

    # 기본 댓글 문구
    if messages:
        comment_messages = messages
    else:
        comment_messages = [
            "좋은 글 잘 보고 갑니다! 소통해요.",
            "포스팅 잘 보고 갑니다. 오늘도 좋은 하루 보내세요!",
            "유익한 내용이네요. 자주 놀러 올게요!",
        ]
    log = logger or print

    from playwright_bootstrap import ensure_playwright_ready_async

    if not await ensure_playwright_ready_async(log):
        raise RuntimeError(
            "Playwright 브라우저를 실행할 수 없습니다. run_fix_playwright.bat 실행 후 재시도하세요."
        )

    # 주의: os.chdir()을 사용하지 않음.
    log("브라우저를 엽니다. 잠시만 기다려 주세요...")
    status("크롬 실행 중 · 브라우저 여는 중…")

    # --- 액션 로그 유틸리티 ---
    def log_action(
        action_type: str,
        post_url: str | None,
        page_index: int,
        item_index: int,
        ok: bool,
        error: str | None = None,
        author: str | None = None,
        title: str | None = None,
    ):
        try:
            exists = os.path.exists(LOG_FILE)
            with open(LOG_FILE, "a", encoding="utf-8", newline="") as f:
                writer = csv.writer(f)
                if not exists:
                    writer.writerow(
                        [
                            "timestamp",
                            "account",
                            "action_type",
                            "page",
                            "index",
                            "post_url",
                            "author",
                            "title",
                            "ok",
                            "error",
                        ]
                    )
                writer.writerow(
                    [
                        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        naver_id,
                        action_type,
                        page_index,
                        item_index,
                        post_url or "",
                        (author or ""),
                        (title or ""),
                        "1" if ok else "0",
                        (error or "")[:200],
                    ]
                )
        except Exception as e:
            # 파일 기록 실패는 치명적이지 않으므로 로그만 남김
            log(f"⚠️ 액션 로그 기록 실패: {e}")

    async with async_playwright() as p:
        # 브라우저를 화면에 보이게 실행. GUI에서 안정적으로 뜨도록 Playwright Chromium을 먼저 사용.
        browser = None
        # 1) Playwright Chromium 먼저 시도 (GUI에서 가장 안정적)
        try:
            log("Playwright Chromium으로 브라우저를 엽니다...")
            browser = await p.chromium.launch(
                headless=False,
                slow_mo=150,
                args=["--start-maximized", "--no-first-run", "--disable-blink-features=AutomationControlled"],
                ignore_default_args=["--enable-automation"],
            )
            log("Chromium 브라우저가 열렸습니다.")
        except Exception as e1:
            log(f"Chromium 실행 실패: {e1}. 설치된 Chrome으로 시도합니다...")
            status("크롬 실행 중 · Chrome 사용 시도…")
            # 2) 설치된 Google Chrome 시도
            try:
                browser = await p.chromium.launch(
                    channel="chrome",
                    headless=False,
                    slow_mo=150,
                    args=[
                        "--start-maximized",
                        "--disable-blink-features=AutomationControlled",
                        "--no-first-run",
                        "--no-default-browser-check",
                    ],
                    ignore_default_args=["--enable-automation"],
                )
                log("Chrome으로 브라우저를 실행했습니다.")
            except Exception as e2:
                log(f"브라우저 실행 실패: {e2}")
                log("해결: 터미널에서 실행 → .\\.venv\\Scripts\\playwright install chromium")
                raise RuntimeError(
                    f"브라우저를 실행할 수 없습니다. 터미널에서: .venv\\Scripts\\playwright install chromium"
                ) from e2
        if browser is None:
            raise RuntimeError("브라우저를 시작할 수 없습니다.")
        context = await browser.new_context(no_viewport=True)
        page = await context.new_page()
        await page.bring_to_front()
        log("Chrome 창이 열렸습니다. 화면에서 작업을 확인하세요.")
        status("크롬 실행 중 · 브라우저 창 표시됨")

        def _bring_browser_to_front():
            """Windows에서 브라우저 창을 맨 앞으로 가져오기 (작업이 보이도록)."""
            if sys.platform != "win32":
                return
            try:
                import ctypes
                user32 = ctypes.windll.user32
                hwnd = user32.GetForegroundWindow()
                # Chrome 창이 이미 포커스일 수 있음; 또는 창 제목으로 찾기
                def enum_cb(hw, _):
                    buf = ctypes.create_unicode_buffer(256)
                    if user32.GetWindowTextW(hw, buf, 256) and buf.value:
                        t = buf.value.lower()
                        if "chrome" in t or "naver" in t or "네이버" in t or "blog" in t:
                            user32.SetForegroundWindow(hw)
                            return False  # stop enum
                    return True
                WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
                user32.EnumWindows(WNDENUMPROC(enum_cb), 0)
            except Exception:
                pass

        # --- [네이버: 이웃 새글에서 공감+댓글 반복] ---
        async def naver_process(naver_id, naver_pw):
            log(f"네이버 계정 {naver_id} 작업 시작...")
            status("크롬 실행 중 · 네이버 로그인 중…")
            await page.goto("https://nid.naver.com/nidlogin.login")
            log("네이버 로그인 페이지를 불러왔습니다.")
            status("크롬 실행 중 · 네이버 로그인 중…")
            await page.bring_to_front()
            _bring_browser_to_front()
            log("ID 입력 중...")
            await page.fill("#id", naver_id)
            log("비밀번호 입력 중...")
            await page.fill("#pw", naver_pw)
            log("로그인 버튼 클릭. 잠시 대기...")
            await page.click(".btn_login")
            log("로그인 완료. 이웃 새글 목록으로 이동합니다...")
            await asyncio.sleep(4)

            status("크롬 실행 중 · 이웃 새글 목록 로드 중…")
            log("이웃 새글 목록을 불러오는 중...")
            await page.goto("https://section.blog.naver.com/")
            await smart_delay(2, 4)
            log("이웃 새글 목록 로드 완료.")

            blog_link = page.locator("a.MyView-module__link_service___Ok8hP", has_text="블로그").first
            if await blog_link.count() > 0 and await blog_link.is_visible(timeout=5000):
                await blog_link.click()
                await smart_delay(2, 4)
            else:
                pass

            # --- 방문/댓글 이력 (티스토리와 동일 로직) ---
            today = datetime.now().strftime("%Y-%m-%d")
            state = _load_naver_state(naver_id)
            state_date = state.get("date") or ""
            today_posts = set(_normalize_naver_url(u) for u in state.get("posts_visited", []) if state_date == today)
            no_comment_posts = set(_normalize_naver_url(u) for u in state.get("no_comment_posts", []))
            raw_success = state.get("comment_success_posts")
            if raw_success is None:
                comment_success_posts = set(_normalize_naver_url(u) for u in state.get("posts_commented", []))
            else:
                comment_success_posts = set(_normalize_naver_url(u) for u in raw_success)
            yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
            posts_to_revisit = []
            if state_date == yesterday:
                posts_to_revisit = [
                    u for u in (_normalize_naver_url(x) for x in state.get("posts_commented", []))
                    if u not in no_comment_posts
                ]
                if posts_to_revisit:
                    log(f"전날({state_date}) 방문한 글 {len(posts_to_revisit)}개 재방문 → 좋아요+댓글 예정")

            # --- 전날 방문한 글 재방문: 좋아요 + 댓글 ---
            revisit_done = 0
            if posts_to_revisit:
                status("크롬 실행 중 · 전날 방문 글 좋아요+댓글…")
                for post_url in posts_to_revisit[:n_max_actions]:
                    log(f"[재방문] 글: {post_url[:60]}...")
                    post_norm = _normalize_naver_url(post_url)
                    try:
                        await page.goto(post_url, wait_until="domcontentloaded", timeout=15000)
                        await human_delay(n_min_delay, n_max_delay)
                        has_frame = await page.locator("#mainFrame").count() > 0
                        frame = page.frame_locator("#mainFrame") if has_frame else page
                        # 공감(좋아요): 네이버 블로그 공감 버튼
                        like_btn = frame.locator(".u_likeit_button, .blog_like_area .my_reaction a.u_likeit_button").first
                        if await like_btn.count() > 0 and await like_btn.is_visible(timeout=3000):
                            await like_btn.click()
                            await asyncio.sleep(0.8)
                            layer_like = page.locator("ul.u_likeit_layer a.u_likeit_list_button[data-type='like']").first
                            if await layer_like.count() > 0 and await layer_like.is_visible(timeout=1500):
                                await layer_like.click()
                                await asyncio.sleep(0.5)
                            log("   ✓ 공감 클릭")
                        if post_norm in comment_success_posts:
                            log("   (이미 댓글을 남긴 글이라, 추가 댓글은 생략합니다)")
                        else:
                            comment_box = frame.locator(".u_cbox_text").first
                            if await comment_box.count() > 0 and await comment_box.is_visible(timeout=5000):
                                await comment_box.fill(random.choice(comment_messages))
                                await asyncio.sleep(0.5)
                                await frame.locator(".u_cbox_btn_upload").first.click()
                                await human_delay(n_min_delay, n_max_delay)
                                comment_success_posts.add(post_norm)
                                revisit_done += 1
                                log("   ✓ 좋아요+댓글 완료")
                        today_posts.add(post_norm)
                    except Exception as e:
                        log(f"   ✗ 재방문 오류: {e}")
                        today_posts.add(post_norm)
                    await human_delay(n_min_delay, n_max_delay)
                if revisit_done:
                    log(f"전날 방문 글 재방문 완료: {revisit_done}개 (좋아요+댓글)")

            risk = RiskControl(n_max_actions, ERROR_THRESHOLD)
            stop_all = False
            total_items = 0
            total_comments = 0

            page_idx = 0
            while True:
                if stop_all:
                    break
                page_idx += 1
                status(f"크롬 실행 중 · 이웃 새글 페이지 {page_idx} 처리 중…")
                log(f"▶ 이웃 새글 페이지 {page_idx} 처리 중...")
                await page.wait_for_load_state("domcontentloaded")
                await smart_delay(1, 2)

                # 현재 페이지의 글 목록 (div.item.multi_pic)
                items = page.locator("section.wrap_thumbnail_post_list div.list_post_article div.item.multi_pic, div.list_post_article_comments div.item.multi_pic")
                n = await items.count()
                if n == 0:
                    items = page.locator("div.item.multi_pic")
                    n = await items.count()
                if n == 0:
                    log("   이번 페이지에 글이 없습니다.")
                    break

                for i in range(n):
                    total_items += 1
                    post_url = None
                    last_error = None
                    author = None
                    title = None
                    if risk.should_stop():
                        log("   리스크 기준 도달 – 작업 중단.")
                        stop_all = True
                        break

                    status(f"크롬 실행 중 · 글 {i+1}/{n} 공감·댓글 작성 중…")
                    await human_delay(n_min_delay, n_max_delay)
                    item = items.nth(i)
                    try:
                        await item.scroll_into_view_if_needed(timeout=5000)
                    except Exception:
                        pass
                    await asyncio.sleep(0.5)
                    # 댓글 링크에서 URL 먼저 추출 → 이미 방문/댓글창 없음 글은 건너뜀
                    comment_link = item.locator("a[href*='copen=1']").first
                    if await comment_link.count() == 0:
                        comment_link = item.locator("a[href*='?copen=1']").first
                    if await comment_link.count() > 0:
                        href = await comment_link.get_attribute("href")
                        if href and "copen=1" in href:
                            post_url = href
                            if post_url.startswith("//"):
                                post_url = "https:" + post_url
                            elif post_url.startswith("/"):
                                post_url = "https://blog.naver.com" + post_url
                            post_norm = _normalize_naver_url(post_url)
                            if post_norm in no_comment_posts:
                                log(f"   글 (댓글창 없음으로 저장된 글, 건너뜀)")
                                continue
                            if post_norm in today_posts:
                                log(f"   글 (이미 오늘 방문함, 건너뜀)")
                                continue

                    # 랜덤 스크롤로 행동 자연스럽게
                    if random.random() < 0.4:
                        await random_scroll(page)

                    did_action = False
                    # 작성자/제목 정보 추출 (로그용)
                    try:
                        author_loc = item.locator(".info_author .name_author").first
                        if await author_loc.count() > 0:
                            author = (await author_loc.inner_text()).strip()
                    except Exception:
                        author = None
                    try:
                        title_loc = item.locator(".desc .title_post span").first
                        if await title_loc.count() > 0:
                            title = (await title_loc.inner_text()).strip()
                    except Exception:
                        title = None

                    # 1) 공감(하트): .my_reaction 안의 a.u_likeit_button 또는 span.u_likeit_icon.__reaction__zeroface 포함한 버튼 클릭
                    try:
                        like_btn = item.locator(".blog_like_area .my_reaction a.u_likeit_button").first
                        if await like_btn.count() > 0 and await like_btn.is_visible(timeout=2000):
                            await like_btn.click()
                            await asyncio.sleep(0.8)
                            # 레이어가 뜨면 '공감'(like) 선택
                            layer_like = page.locator("ul.u_likeit_layer a.u_likeit_list_button[data-type='like']").first
                            if await layer_like.count() > 0 and await layer_like.is_visible(timeout=1500):
                                await layer_like.click()
                                await asyncio.sleep(0.5)
                    except Exception as e:
                        last_error = str(e)

                    # 2) 댓글 링크 클릭 → 해당 글 페이지로 이동
                    try:
                        comment_link = item.locator("a[href*='copen=1']").first
                        if await comment_link.count() == 0:
                            comment_link = item.locator("a[href*='?copen=1']").first
                        if await comment_link.count() > 0:
                            href = await comment_link.get_attribute("href")
                            if href and "copen=1" in href:
                                if href.startswith("//"):
                                    href = "https:" + href
                                elif href.startswith("/"):
                                    href = "https://blog.naver.com" + href
                                post_url = href
                                post_norm = _normalize_naver_url(post_url)
                                await page.goto(href, wait_until="domcontentloaded", timeout=15000)
                                await human_delay(n_min_delay, n_max_delay)

                                # 본문이 iframe(mainFrame)인 경우
                                has_frame = await page.locator("#mainFrame").count() > 0
                                frame = page.frame_locator("#mainFrame") if has_frame else page
                                try:
                                    status(f"크롬 실행 중 · 댓글 작성 중 (성공 {total_comments}/{n_max_actions})…")
                                    comment_box = frame.locator(".u_cbox_text").first
                                    if await comment_box.count() > 0 and await comment_box.is_visible(timeout=5000):
                                        await comment_box.fill(random.choice(comment_messages))
                                        await asyncio.sleep(0.5)
                                        await frame.locator(".u_cbox_btn_upload").first.click()
                                        await human_delay(n_min_delay, n_max_delay)
                                        did_action = True
                                        comment_success_posts.add(post_norm)
                                        log(f"   ✓ 댓글 등록 완료")
                                    else:
                                        no_comment_posts.add(post_norm)
                                        log("   (댓글 입력창 없음 → 저장함, 다음부터 방문 안 함)")
                                except Exception as e:
                                    risk.record_error()
                                    last_error = str(e)
                                today_posts.add(post_norm)
                                # 목록으로 복귀(같은 페이지 유지)
                                await page.go_back()
                                await human_delay(n_min_delay, n_max_delay)
                    except Exception as e:
                        last_error = str(e)
                        try:
                            await page.go_back()
                        except Exception:
                            pass

                    # 액션 로그 기록
                    if post_url:
                        if did_action:
                            log_action(
                                "comment+like",
                                post_url,
                                page_idx,
                                i,
                                ok=True,
                                error=None,
                                author=author,
                                title=title,
                            )
                            risk.record_action()
                            total_comments += 1
                        else:
                            log_action(
                                "like_only_or_failed",
                                post_url,
                                page_idx,
                                i,
                                ok=False,
                                error=last_error,
                                author=author,
                                title=title,
                            )
                    if did_action:
                        await human_delay(n_min_delay, n_max_delay)

                # 3) 다음 페이지
                next_btn = page.locator("a.button_next").first
                if await next_btn.count() == 0:
                    next_btn = page.locator(".pagination a:has-text('다음')").first
                if await next_btn.count() > 0 and await next_btn.is_visible(timeout=2000):
                    try:
                        status(f"크롬 실행 중 · 다음 페이지로 이동 중…")
                        await next_btn.click()
                        await smart_delay(2, 4)
                    except Exception:
                        break
                else:
                    break

            _save_naver_state(
                naver_id,
                today,
                today_posts,
                today_posts,
                no_comment_posts,
                comment_success_posts,
            )
            log(f"   네이버 이웃 새글 공감/댓글 처리 완료. 총 시도 글 {total_items}개, 댓글 성공 {total_comments}개, 오류 {risk.errors}회. (오늘 방문 {len(today_posts)}글 기록)")

        # --- [티스토리] (기존 유지) ---
        async def tistory_process(t_id, t_pw):
            print(f"티스토리 계정 {t_id} 작업 시작...")
            await page.goto("https://www.tistory.com/auth/login")
            await asyncio.sleep(2)
            tab = page.locator("a.link_tab:has-text('내 블로그')").first
            if await tab.count() > 0 and await tab.is_visible(timeout=5000):
                await tab.click()
                await smart_delay()
            comment_links = page.locator("a[href*='#comment']")
            for i in range(await comment_links.count()):
                await comment_links.nth(i).click()
                await smart_delay()
                try:
                    ta = page.locator("textarea").first
                    if await ta.count() > 0 and await ta.is_visible(timeout=2000):
                        await ta.fill("방문 감사드려요! 좋은 하루 되세요.")
                        await page.locator("button:has-text('등록')").first.click()
                        await smart_delay()
                except Exception:
                    pass
                await page.go_back()
                await smart_delay()

        try:
            await naver_process(naver_id, naver_pw)
        finally:
            try:
                await browser.close()
            except Exception:
                pass


async def run_blog_automation():
    """config.py의 첫 번째 네이버 계정을 사용해 CLI에서 실행할 때 편의용 래퍼."""
    try:
        from config import NAVER_ACCOUNTS
        if NAVER_ACCOUNTS:
            acc = NAVER_ACCOUNTS[0]
            nid = acc.get("id", "")
            npw = acc.get("pw", "")
        else:
            nid = "hymini1"
            npw = "@@hwang4040"
    except Exception:
        nid = "hymini1"
        npw = "@@hwang4040"
    await run_blog_automation_for_account(nid, npw)


if __name__ == "__main__":
    print("서이추 댓글 자동화는 GUI(blog_main.py)의 '서이추 댓글' 탭에서만 실행할 수 있습니다.")
    print("실행: python blog_main.py → 서이추 댓글 탭에서 실행 버튼을 누르세요.")
