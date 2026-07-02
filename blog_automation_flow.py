# -*- coding: utf-8 -*-
"""자동화 메인 루프: 브라우저 세션·포스팅 시퀀스. app 인스턴스와 config로 실행."""

import asyncio
import os
import random
import subprocess
import sys

from browser_stealth import (
    BROWSER_LAUNCH_ARGS,
    IGNORE_AUTOMATION_ARGS,
    apply_stealth_to_context,
)


def _content_gen_helpers():
    from blog_content_gen import (
        PRODUCT_LABELS,
        _normalize_text_provider,
        _template_outline,
        apply_product_choice,
        ollama_warmup,
    )

    return apply_product_choice, PRODUCT_LABELS, ollama_warmup, _normalize_text_provider, _template_outline


def _browser_stack():
    from playwright.async_api import async_playwright

    from blogger_browser import BloggerBrowserWriter, _body_to_html
    from google_blogger_auto import post_to_blogger
    from naver_module import NaverBlogPublisher, NaverBlogWriter
    from tistory_module import TistoryWriter

    return (
        async_playwright,
        NaverBlogWriter,
        NaverBlogPublisher,
        TistoryWriter,
        BloggerBrowserWriter,
        _body_to_html,
        post_to_blogger,
    )


_CHROME_LOCK_NAMES = ("lockfile", "SingletonLock", "SingletonCookie", "SingletonSocket")


def _profile_marker(user_data_dir: str) -> str:
    return os.path.basename(os.path.normpath(user_data_dir))


def _is_chrome_profile_in_use(user_data_dir: str) -> bool:
    """해당 user-data-dir을 사용 중인 chrome.exe 프로세스가 있는지 확인."""
    if sys.platform != "win32":
        return False
    try:
        marker = _profile_marker(user_data_dir)
        ps = (
            "Get-CimInstance Win32_Process -Filter \"Name='chrome.exe'\" "
            f"| Where-Object {{ $_.CommandLine -like '*{marker}*' }} "
            "| Select-Object -ExpandProperty ProcessId"
        )
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps],
            capture_output=True,
            text=True,
            timeout=12,
        )
        return any(line.strip().isdigit() for line in (result.stdout or "").splitlines())
    except Exception:
        return False


def _list_chrome_pids_for_profile(user_data_dir: str, automation_only: bool = True):
    if sys.platform != "win32":
        return []
    marker = _profile_marker(user_data_dir)
    ps = (
        "Get-CimInstance Win32_Process -Filter \"Name='chrome.exe'\" "
        f"| Where-Object {{ $_.CommandLine -like '*{marker}*' }} "
        "| Select-Object -ExpandProperty ProcessId"
    )
    if automation_only:
        ps = (
            "Get-CimInstance Win32_Process -Filter \"Name='chrome.exe'\" "
            f"| Where-Object {{ $_.CommandLine -like '*{marker}*' "
            "-and $_.CommandLine -like '*--enable-automation*' }} "
            "| Select-Object -ExpandProperty ProcessId"
        )
    result = subprocess.run(
        ["powershell", "-NoProfile", "-Command", ps],
        capture_output=True,
        text=True,
        timeout=20,
    )
    pids = []
    for line in (result.stdout or "").splitlines():
        line = line.strip()
        if line.isdigit():
            pids.append(int(line))
    return pids


def _kill_automation_chrome_for_profile(user_data_dir: str, logger) -> int:
    """자동화(Playwright)용 Chrome 프로세스만 종료한다."""
    if sys.platform != "win32":
        return 0
    try:
        marker = _profile_marker(user_data_dir)
        pids = _list_chrome_pids_for_profile(user_data_dir, automation_only=False)
        killed = 0
        for pid in pids:
            proc = subprocess.run(
                ["taskkill", "/F", "/PID", str(pid)],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if proc.returncode == 0:
                killed += 1
        if killed:
            logger(f"      [정리] 이전 자동화 Chrome {killed}개 종료 ({marker})")
        return killed
    except Exception as e:
        logger(f"      [경고] 자동화 Chrome 정리 실패: {e}")
        return 0


def _clear_stale_chrome_locks(user_data_dir: str, logger) -> int:
    """크래시 등으로 남은 Chrome 프로필 lock 파일을 제거한다."""
    removed = 0
    lock_paths = [os.path.join(user_data_dir, name) for name in _CHROME_LOCK_NAMES]
    lock_paths.append(os.path.join(user_data_dir, "Default", "LOCK"))
    for path in lock_paths:
        if not os.path.exists(path):
            continue
        try:
            os.remove(path)
            removed += 1
            logger(f"      [정리] 프로필 lock 제거: {os.path.basename(path)}")
        except OSError as e:
            logger(f"      [경고] 프로필 lock 제거 실패 ({os.path.basename(path)}): {e}")
    return removed


def _is_profile_lock_error(err_msg: str) -> bool:
    msg = (err_msg or "").lower()
    return (
        "targetclosederror" in msg
        or "exit code 21" in msg
        or "failed to launch" in msg
        or "user data directory is already in use" in msg
        or "singletonlock" in msg
        or "lockfile" in msg
        or "process_singleton" in msg
    )


async def _try_launch_persistent(playwright_obj, user_data_dir: str, logger, use_chrome_channel: bool):
    common_args = {
        "headless": False,
        "no_viewport": True,
        "locale": "ko-KR",
        "timezone_id": "Asia/Seoul",
        "ignore_default_args": IGNORE_AUTOMATION_ARGS,
        "args": BROWSER_LAUNCH_ARGS,
    }
    if use_chrome_channel:
        ctx = await playwright_obj.chromium.launch_persistent_context(
            user_data_dir,
            channel="chrome",
            **common_args,
        )
    else:
        ctx = await playwright_obj.chromium.launch_persistent_context(
            user_data_dir,
            **common_args,
        )
    await apply_stealth_to_context(ctx)
    return ctx


async def _launch_context_with_fallback(playwright_obj, user_data_dir: str, logger):
    """Chrome 채널 우선 실행 후 실패 시 Playwright Chromium으로 폴백. stale lock 자동 정리."""
    os.makedirs(user_data_dir, exist_ok=True)

    if _is_chrome_profile_in_use(user_data_dir):
        _kill_automation_chrome_for_profile(user_data_dir, logger)
        await asyncio.sleep(2)
    else:
        # Chrome 프로세스는 없는데 lockfile만 남은 경우(비정상 종료) 선제 정리
        removed_preclean = _clear_stale_chrome_locks(user_data_dir, logger)
        if removed_preclean:
            logger(f"      [정보] 사용 중인 Chrome 없음 — stale lock {removed_preclean}개 선제 정리")

    removed = _clear_stale_chrome_locks(user_data_dir, logger)
    if removed:
        logger(f"      [정보] 남아 있던 프로필 lock {removed}개를 정리했습니다.")

    last_err = None
    for attempt in range(2):
        # 1) 로컬 설치 Chrome 우선
        try:
            return await _try_launch_persistent(playwright_obj, user_data_dir, logger, True)
        except Exception as e:
            last_err = e
            logger(f"      [경고] Chrome 채널 실행 실패, Playwright Chromium으로 재시도: {e}")

        # 2) Playwright Chromium 폴백
        try:
            return await _try_launch_persistent(playwright_obj, user_data_dir, logger, False)
        except Exception as e:
            last_err = e
            if attempt == 0 and _is_profile_lock_error(str(e)) and not _is_chrome_profile_in_use(user_data_dir):
                logger("      [재시도] 프로필 lock 재정리 후 브라우저를 다시 실행합니다...")
                _clear_stale_chrome_locks(user_data_dir, logger)
                await asyncio.sleep(1)
                continue
            raise

    if last_err:
        raise last_err
    raise RuntimeError("브라우저 실행에 실패했습니다.")


def _is_playwright_browser_missing_error(err_msg: str) -> bool:
    msg = (err_msg or "").lower()
    return (
        "winerror 2" in msg
        or "지정된 파일을 찾을 수 없습니다" in msg
        or "playwright team" in msg
        or "please run the following command" in msg
        or "playwright install" in msg
        or "executable doesn't exist" in msg
        or "failed to launch" in msg and "chromium" in msg
    )


def _append_product_url(body: str, config: dict, required_keyword: str = "") -> str:
    """스마트스토어 URL — 마지막 1문단 부드러운 참고 링크로만."""
    try:
        # 1. 키워드 기반으로 상품 URL 및 카테고리(auto/bike/living) 자동 감지
        kw = str(required_keyword or "").lower()
        
        PRODUCT_URL_MAP = {
            "auto": "https://smartstore.naver.com/nanumlab/products/12639296730",  # 퍼마코트 자동차 코팅제
            "bike": "https://smartstore.naver.com/nanumlab/products/12808836901",  # 나눔랩 바이크 코팅제
            "living": "https://smartstore.naver.com/nanumlab/products/10713170202", # 듀라코트 리빙코트
        }
        from blog_constants import PRODUCT_LABELS
        
        # 기본값 설정
        url = (config.get("product_url") or "").strip()
        choice = (config.get("product_choice") or "none").strip().lower()
        
        # 만약 product_choice가 none이거나, url이 없으면 키워드 기반 자동 연동
        if choice == "none" or not url:
            if any(x in kw for x in ("바이크", "오토바이", "이륜차", "bike")):
                choice = "bike"
            elif any(x in kw for x in ("가구", "원목", "싱크대", "욕실", "타일", "리빙", "식탁", "living", "곰팡이")):
                choice = "living"
            else:
                choice = "auto"
            url = PRODUCT_URL_MAP[choice]
            # 실시간 config에 동기화
            config["product_choice"] = choice
            config["product_url"] = url
    except Exception:
        url = ""
        choice = "none"
        
    if not url or url in body:
        return body
        
    label = PRODUCT_LABELS.get(choice, "관련 제품")
    particle = "를" if label and (ord(label[-1]) - 0xAC00) % 28 == 0 else "을"
    footer = (
        f"\n\n직접 시공이 부담되시면, 위에서 정리한 기준(성분·함량·시공 난이도)에 맞는 "
        f"{label}{particle} 먼저 비교해 보시는 것을 권합니다. "
        f"참고 링크(나눔랩 스마트스토어): {url}"
    )
    return body.rstrip() + footer


def _build_keyword_plan(keywords_list, total_rounds):
    """라운드 수만큼 키워드 쌍(필수, 추가)을 중복 최소화해 생성."""
    kws = [k for k in (keywords_list or []) if k]
    if not kws:
        return [("", "")] * total_rounds
    if len(kws) == 1:
        return [(kws[0], kws[0])] * total_rounds

    pairs = []
    # 가능한 모든 순서쌍 생성 (A+B, B+A를 다른 조합으로 취급)
    for a in kws:
        for b in kws:
            if a != b:
                pairs.append((a, b))
    random.shuffle(pairs)

    plan = []
    last = None
    idx = 0
    while len(plan) < total_rounds:
        if idx >= len(pairs):
            random.shuffle(pairs)
            idx = 0
        cand = pairs[idx]
        idx += 1
        # 바로 이전 라운드와 동일 조합은 회피
        if cand == last and len(pairs) > 1:
            continue
        plan.append(cand)
        last = cand
    return plan


async def _generate_one_round(app, config, posting_targets, r, total_rounds, post_type, keyword_plan, ignore_keywords_types):
    """원고·이미지만 생성 (Chrome/Playwright 없음)."""
    _, _, _, _normalize_text_provider, _template_outline = _content_gen_helpers()

    if post_type in ignore_keywords_types:
        required_keyword = "맛집·일상 에세이" if post_type == "맛집/일상" else "취미 에세이"
        extra_keyword = required_keyword
        keyword_display = post_type + " (키워드 무시)"
        app.log(f"\n🚀 [라운드 {r+1}/{total_rounds}] {keyword_display} → 원고 생성")
    else:
        required_keyword, extra_keyword = keyword_plan[r]
        keyword_display = f"{required_keyword}" + (
            f" + {extra_keyword}" if extra_keyword != required_keyword else ""
        )
        app.log(f"\n🚀 [라운드 {r+1}/{total_rounds}] 필수 '{required_keyword}', 추가 '{extra_keyword}' → 원고 생성")

    await app.check_pause()
    tp = _normalize_text_provider(config)
    if tp in ("ollama", "auto"):
        app.log("   📋 1단계: 제목·개요 확정 중... (Ollama 사용 시 1~5분 소요될 수 있습니다)")
    elif tp == "claude":
        app.log("   📋 1단계: 제목·개요 확정 중... (Claude Code)")
    else:
        app.log("   📋 1단계: 제목·개요 확정 중...")
    outline_title, outline_str, image_desc = await app.generate_outline(
        config, required_keyword, extra_keyword
    )
    if not (outline_title or "").strip() or len((outline_title or "").strip()) < 4:
        tpl_title, tpl_outline, tpl_img = _template_outline(required_keyword)
        app.log(f"      ⚠️ 제목이 비정상이라 템플릿으로 대체합니다: {tpl_title}")
        outline_title, outline_str, image_desc = tpl_title, tpl_outline, tpl_img

    contents_by_key = {}
    naver_targets = [t for t in posting_targets if t["type"] == "naver"]
    app.log("   📝 본문 1회 생성 (모든 계정 공통 · 속도 우선)")
    body, tags = await app.generate_body_from_outline(
        config, outline_title, outline_str, required_keyword, extra_keyword
    )
    body = _append_product_url(body, config, required_keyword)
    for t in naver_targets:
        contents_by_key[f"naver:{t['id']}"] = (outline_title, body, tags)
    if any(t["type"] != "naver" for t in posting_targets):
        contents_by_key["default"] = (outline_title, body, tags)
    elif not contents_by_key.get("default") and contents_by_key:
        contents_by_key["default"] = next(iter(contents_by_key.values()))

    await app.check_pause()
    if app.img_mode_var.get() == "custom" and app.custom_img_paths:
        app.log("   📸 사용자 선택 이미지를 사용합니다.")
        img_paths = app.custom_img_paths.copy()
    else:
        app.log("   🎨 AI 이미지 2장 생성 (본문 중간·끝, 키워드 맞춤)")
        varied_desc = f"{image_desc} | variation:{r+1}-{random.randint(1000, 9999)}"
        img_paths = await app.generate_images(
            config,
            required_keyword,
            extra_keyword,
            title=outline_title,
            image_desc=varied_desc,
        )

    product_img = os.path.join(app.base_dir, "product_info.png")
    if os.path.exists(product_img):
        img_paths = list(img_paths or [])
        img_paths.append(product_img)

    return {
        "keyword_display": keyword_display,
        "contents_by_key": contents_by_key,
        "img_paths": img_paths or [],
    }


async def _init_browser_sessions(p, app, config, posting_targets):
    """Playwright 컨텍스트·라이터 준비 (발행 단계에서만 호출)."""
    (
        _async_playwright,
        NaverBlogWriter,
        NaverBlogPublisher,
        TistoryWriter,
        BloggerBrowserWriter,
        _body_to_html,
        post_to_blogger,
    ) = _browser_stack()

    naver_contexts = {}
    naver_writers = {}
    naver_pubs = {}
    tistory_page = None
    t_writer = None
    google_page = None
    g_writer = None

    app.log("   🌐 [발행] 브라우저 세션 준비 중... (원고 완료 후에만 실행)")

    for nid, npw in zip(config["naver_ids"], config["naver_pws"]):
        app.log(f"      🔹 [{nid}] 세션 연결 중...")
        acc_dir = os.path.join(app.base_dir, f"browser_data_{nid}")
        ctx = await _launch_context_with_fallback(p, acc_dir, app.log)
        page = ctx.pages[0] if ctx.pages else await ctx.new_page()
        naver_contexts[nid] = ctx
        naver_writers[nid] = NaverBlogWriter(page, app.log)
        naver_pubs[nid] = NaverBlogPublisher(page, app.log)

    if config["use_tistory"]:
        app.log("      🔹 [티스토리] 세션 준비 중...")
        if naver_contexts:
            first_ctx = list(naver_contexts.values())[0]
            tistory_page = await first_ctx.new_page()
        else:
            t_acc_dir = os.path.join(app.base_dir, "browser_data_tistory")
            t_ctx = await _launch_context_with_fallback(p, t_acc_dir, app.log)
            tistory_page = t_ctx.pages[0] if t_ctx.pages else await t_ctx.new_page()
            naver_contexts["tistory_internal"] = t_ctx
        t_writer = TistoryWriter(tistory_page, app.log)
        t_writer.wait_func = app.wait_with_pause
        if await t_writer.is_logged_in():
            app.log("      ✅ [티스토리] 기존 로그인 세션 유지됨")
        else:
            app.log("      ℹ️ [티스토리] 포스팅 직전에 로그인합니다.")

    if config.get("use_google"):
        app.log("      🔹 [구글 Blogger] 브라우저 세션 준비 중...")
        if naver_contexts:
            first_ctx = list(naver_contexts.values())[0]
            google_page = await first_ctx.new_page()
        else:
            g_acc_dir = os.environ.get("GOOGLE_CHROME_USER_DATA") or os.path.join(
                app.base_dir, "browser_data_google"
            )
            g_ctx = await _launch_context_with_fallback(p, g_acc_dir, app.log)
            google_page = g_ctx.pages[0] if g_ctx.pages else await g_ctx.new_page()
            naver_contexts["google_internal"] = g_ctx
        g_writer = BloggerBrowserWriter(google_page, app.log)
        g_writer.wait_func = app.wait_with_pause

    for nid in naver_writers:
        naver_writers[nid].wait_func = app.wait_with_pause
        naver_pubs[nid].wait_func = app.wait_with_pause

    if naver_writers:
        app.log("   🔐 [발행] 네이버 로그인 세션 확인 중...")
        for nid, npw in zip(config["naver_ids"], config["naver_pws"]):
            await app.check_pause()
            n_wr = naver_writers.get(nid)
            if n_wr:
                await n_wr.warmup_session({"naver_id": nid, "naver_pw": npw})

    return naver_contexts, naver_writers, naver_pubs, t_writer, g_writer, _body_to_html, post_to_blogger


async def _post_round_targets(
    app,
    config,
    posting_targets,
    round_data,
    naver_contexts,
    naver_writers,
    naver_pubs,
    t_writer,
    g_writer,
    _body_to_html,
    post_to_blogger,
):
    """준비된 브라우저로 한 라운드 발행."""
    from naver_module import NaverBlogPublisher, NaverBlogWriter

    keyword_display = round_data["keyword_display"]
    contents_by_key = round_data["contents_by_key"]
    img_paths = round_data["img_paths"]

    for target in posting_targets:
        await app.check_pause()
        if target["type"] == "naver":
            key = f"naver:{target['id']}"
        else:
            key = "default"
        title, body, tags = contents_by_key.get(key, (None, None, None))
        if not title:
            continue

        if target["type"] == "naver":
            n_id = target["id"]
            app.log(f"\n   🟢 [네이버 포스팅 시작] 계정: {n_id}")
            ctx = naver_contexts[n_id]
            page = ctx.pages[0] if ctx.pages else await ctx.new_page()
            n_wr = NaverBlogWriter(page, app.log)
            n_pb = NaverBlogPublisher(page, app.log)
            n_wr.wait_func = app.wait_with_pause
            n_pb.wait_func = app.wait_with_pause

            posted = False
            for post_try in range(2):
                if post_try > 0:
                    app.log(f"      🔄 [{n_id}] 글쓰기 재시도 ({post_try + 1}/2)...")
                frame = await n_wr.navigate_to_editor({"naver_id": n_id, "naver_pw": target["pw"]})
                n_pb.page = n_wr.page
                if not frame:
                    app.log(f"      ❌ [{n_id}] 에디터 진입 실패")
                    continue
                if config.get("manual_confirm"):
                    if not app._ask_yesno_on_main(
                        "확인", f"[{n_id}] 계정에 글 작성을 시작할까요?\n\n키워드: {keyword_display}"
                    ):
                        app.log(f"   ⏭ [{n_id}] 작성을 취소했습니다.")
                        break
                if not await n_wr.write_content(frame, title, body, img_paths):
                    app.log(f"      ❌ [{n_id}] 본문 작성 실패")
                    continue
                await app.check_pause()
                if not await n_pb.open_publish_layer(frame):
                    app.log(f"      ❌ [{n_id}] 발행 레이어 실패")
                    continue
                await app.check_pause()
                await n_pb.set_tags(frame, tags)
                await app.check_pause()
                await n_pb.finalize_publish(frame)
                app.log(f"      ✅ [{n_id}] 포스팅 완료")
                posted = True
                break
            if not posted:
                app.log(f"      ❌ [{n_id}] 포스팅을 완료하지 못했습니다.")

        elif target["type"] == "tistory":
            app.log("\n   🔵 [티스토리 포스팅 시작]")
            if not await t_writer.ensure_logged_in(config["tistory_id"], config["tistory_pw"]):
                app.log("      ❌ [티스토리] 로그인 실패")
                continue
            if await t_writer.navigate_to_editor():
                if config.get("manual_confirm"):
                    if not app._ask_yesno_on_main("확인", "티스토리에 글 작성을 시작할까요?"):
                        app.log("   ⏭ 티스토리 작성을 취소했습니다.")
                        continue
                if await t_writer.fill_and_publish(title, body, tags, img_paths):
                    app.log("      ✅ [티스토리] 포스팅 완료")
                else:
                    app.log("      ❌ [티스토리] 작성/발행 실패")
            else:
                app.log("      ❌ [티스토리] 에디터 진입 실패")

        elif target["type"] == "google":
            app.log("\n   🟣 [구글 Blogger 포스팅 시작]")
            if config.get("manual_confirm"):
                if not app._ask_yesno_on_main("확인", "구글 Blogger로 글 작성을 시작할까요?"):
                    app.log("   ⏭ 구글 Blogger 작성을 취소했습니다.")
                    continue
            if g_writer and await g_writer.write_draft(title, body, img_paths):
                app.log("      ✅ [구글 Blogger] 포스팅 완료")
            else:
                try:
                    html_body = _body_to_html(body, img_paths)
                    await asyncio.to_thread(post_to_blogger, title, html_body, True)
                    app.log("      ✅ [구글 Blogger] API 초안 저장 완료")
                except Exception as ge:
                    app.log(f"      ❌ [구글 Blogger] API 발행 실패: {ge}")


async def _close_browser_contexts(naver_contexts):
    for ctx in (naver_contexts or {}).values():
        try:
            await ctx.close()
        except Exception:
            pass


async def run_main_loop(app, config):
    """자동화: 원고·이미지 먼저 → 필요 시에만 Chrome(발행)."""
    apply_product_choice, PRODUCT_LABELS, ollama_warmup, _normalize_text_provider, _template_outline = (
        _content_gen_helpers()
    )
    try:
        from drawer.light import browser_per_round, defer_browser, unload_after_job
    except ImportError:
        defer_browser = lambda: True  # noqa: E731
        browser_per_round = lambda: True  # noqa: E731
        unload_after_job = lambda: True  # noqa: E731

    try:
        app.log("=== canon4040 오토 글로그 통합 자동화 시작 ===")
        if defer_browser():
            app.log("   📦 [서랍] 원고·이미지를 먼저 만든 뒤, 발행할 때만 Chrome을 켭니다.")

        posting_targets = []
        if config["use_naver1"] and len(config["naver_ids"]) > 0:
            posting_targets.append(
                {"type": "naver", "id": config["naver_ids"][0], "pw": config["naver_pws"][0]}
            )
        if config["use_naver2"]:
            n2_id_setup = config.get("n2_id", "")
            n2_pw_setup = config.get("n2_pw", "")
            if n2_id_setup and n2_id_setup in config["naver_ids"]:
                posting_targets.append({"type": "naver", "id": n2_id_setup, "pw": n2_pw_setup})
        if config["use_tistory"]:
            posting_targets.append({"type": "tistory"})
        if config.get("use_google"):
            posting_targets.append({"type": "google"})

        # 로컬에서 “발행까지”가 아니라 “초안 생성/이미지 생성”까지만 빠르게 검증할 때 사용
        draft_only_flag = os.environ.get("BLOG_DRAFT_ONLY", "").strip().lower()
        if draft_only_flag in ("1", "true", "yes", "on"):
            app.log("   📝 BLOG_DRAFT_ONLY=1 감지 — 발행(브라우저) 생략하고 초안만 생성합니다.")
            posting_targets = []

        if not posting_targets:
            app.log("⚠️ 발행할 계정 정보가 없습니다. 초안(원고·이미지)만 생성합니다.")
            posting_targets = []

        from blog_constants import validate_automation_subject

        ok_subject, subject_err = validate_automation_subject(config)
        if not ok_subject:
            app.log(f"⚠️ {subject_err}")
            return

        apply_product_choice(config)
        product_choice = (config.get("product_choice") or "none").strip().lower()
        if product_choice in PRODUCT_LABELS:
            kw_preview = ", ".join((config.get("keywords") or [])[:3])
            app.log(
                f"   🎯 홍보 상품: {PRODUCT_LABELS[product_choice]} "
                f"→ 글 유형 [{config.get('post_type')}] / 키워드: {kw_preview}"
            )

        total_rounds = config["count"]
        keywords_list = config["keywords"]
        post_type = (config.get("post_type") or "").strip() or "제품 홍보"
        ignore_keywords_types = ("맛집/일상", "취미글")
        if not keywords_list and post_type not in ignore_keywords_types:
            app.log("⚠️ 키워드가 없습니다. 설정에서 키워드를 입력해 주세요.")
            return
        keyword_plan = (
            []
            if post_type in ignore_keywords_types
            else _build_keyword_plan(keywords_list, total_rounds)
        )

        tp_engine = _normalize_text_provider(config)
        if tp_engine in ("ollama", "auto"):
            app.log(
                "   ⏳ Ollama: 원고 생성 중 (Chrome은 아직 켜지 않습니다). "
                "느리면 템플릿 원고로 진행됩니다."
            )
            await ollama_warmup(app.log)
        elif tp_engine == "claude":
            app.log("   ⏳ Claude Code 모드: CLI 로그인 필요")

        needs_browser = bool(posting_targets)
        if needs_browser:
            from playwright_bootstrap import ensure_playwright_ready_async

            if not await ensure_playwright_ready_async(app.log):
                return
        async_playwright_fn, *_rest = _browser_stack()

        async def _wait_gap_after_round(r_idx: int) -> None:
            if r_idx >= total_rounds - 1:
                return
            wait_min = config["gap"]
            app.log(f"\n💤 다음 라운드까지 대기 중... ({wait_min}분)")
            for m_idx in range(int(wait_min)):
                if m_idx > 0:
                    app.log(f"      ⏳ 남은 대기 시간: {int(wait_min - m_idx)}분...")
                await app.wait_with_pause(60)

        if needs_browser and not defer_browser():
            app.log("   🌐 [전체 모드] Chrome을 먼저 켠 뒤 원고·발행을 진행합니다.")
            async with async_playwright_fn() as p:
                sessions = await _init_browser_sessions(p, app, config, posting_targets)
                for r in range(total_rounds):
                    round_data = await _generate_one_round(
                        app,
                        config,
                        posting_targets,
                        r,
                        total_rounds,
                        post_type,
                        keyword_plan,
                        ignore_keywords_types,
                    )
                    await _post_round_targets(
                        app, config, posting_targets, round_data, *sessions
                    )
                    await _wait_gap_after_round(r)
                await _close_browser_contexts(sessions[0])
        elif needs_browser and defer_browser() and browser_per_round():
            for r in range(total_rounds):
                round_data = await _generate_one_round(
                    app,
                    config,
                    posting_targets,
                    r,
                    total_rounds,
                    post_type,
                    keyword_plan,
                    ignore_keywords_types,
                )
                app.log("   🌐 [발행] 이 라운드만 Chrome 실행 후 종료합니다.")
                async with async_playwright_fn() as p:
                    sessions = await _init_browser_sessions(p, app, config, posting_targets)
                    await _post_round_targets(
                        app, config, posting_targets, round_data, *sessions
                    )
                    await _close_browser_contexts(sessions[0])
                await _wait_gap_after_round(r)
        else:
            pending_rounds = []
            for r in range(total_rounds):
                round_data = await _generate_one_round(
                    app,
                    config,
                    posting_targets,
                    r,
                    total_rounds,
                    post_type,
                    keyword_plan,
                    ignore_keywords_types,
                )
                if needs_browser and defer_browser():
                    pending_rounds.append(round_data)
                await _wait_gap_after_round(r)
            if defer_browser() and pending_rounds and needs_browser:
                app.log("   🌐 [발행] 원고가 모두 준비됨 — Chrome을 한 번만 실행합니다.")
                async with async_playwright_fn() as p:
                    sessions = await _init_browser_sessions(p, app, config, posting_targets)
                    for round_data in pending_rounds:
                        await _post_round_targets(
                            app, config, posting_targets, round_data, *sessions
                        )
                    await _close_browser_contexts(sessions[0])

        app.log("✨ 모든 작업이 성공적으로 완료되었습니다.")
        on_done = getattr(app, "on_automation_complete", None)
        if callable(on_done):
            try:
                on_done(config, success=True)
            except Exception as exc:
                app.log(f"   ⚠️ 발행 후 처리 생략: {exc}")
    except Exception as e:
        err_text = str(e)
        app.log(f"❌ 오류 발생: {err_text}")
        import traceback

        app.log(traceback.format_exc())
        if _is_playwright_browser_missing_error(err_text):
            app.log("⛔ Playwright 브라우저 런타임 문제로 자동화가 중단되었습니다.")
            app.log("   해결: 프로젝트 폴더에서 run_fix_playwright.bat 실행 후 재시도")
            return
        if _is_profile_lock_error(err_text):
            app.log("⛔ Chrome 프로필 충돌로 자동화가 중단되었습니다.")
            return
        app.log("⛔ [자동화 시작]을 다시 눌러 주세요.")
    finally:
        if unload_after_job():
            try:
                from drawer.registry import unload_all

                unload_all()
                app.log("   🧹 [서랍] 메모리에서 워커 모듈을 내렸습니다.")
            except Exception:
                pass

        def _reset_run_button():
            app.is_processing = False
            app.btn_run.config(state="normal", text="🚀 자동화 시작")
            if getattr(app, "btn_draft", None):
                app.btn_draft.config(state="normal", text="✍ 원고+이미지 생성")
            if getattr(app, "btn_pause", None):
                try:
                    app.btn_pause.config(state="disabled")
                except Exception:
                    pass

        app.root.after(0, _reset_run_button)


# 레거시 run_main_loop(브라우저 선기동) 제거됨 — defer_browser / browser_per_round 환경변수 참고
