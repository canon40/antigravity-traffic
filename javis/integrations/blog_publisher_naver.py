# -*- coding: utf-8 -*-
"""네이버 블로그 — 제목/본문 분리 · 본문에 이미지+텍스트 삽입."""

from __future__ import annotations

import re
from typing import Any, Callable

from integrations.blog_auto_login import ensure_logged_in
from integrations.blog_browser_base import (
    fill_title_editable,
    launch_context,
    paste_in_locator,
    plain_body,
    strip_underline_html,
)
from integrations.naver_se_editor import (
    append_body_paragraph,
    body_text_length,
    click_new_text_block,
    dismiss_editor_overlay,
    focus_body_paragraph,
    insert_body_plain_text,
)
from integrations.blog_credentials import (
    get_naver_account_for_blog,
    get_naver_blog_id,
    list_naver_blog_targets,
    naver_write_url,
)

# 네이버 블로그별 Playwright 대기·재시도 (blog_id 키)
_NAVER_TUNING_DEFAULT: dict[str, int] = {
    "main_frame_timeout_ms": 90_000,
    "main_frame_retry_timeout_ms": 45_000,
    "main_frame_retries": 3,
    "recovery_retries": 2,
    "goto_wait_ms": 3_000,
    "retry_goto_wait_ms": 2_200,
    "reload_wait_ms": 1_800,
    "page_goto_timeout_ms": 90_000,
    "smart_editor_timeout_ms": 45_000,
    "post_editor_settle_ms": 2_500,
    "write_ready_retries": 1,
    "publish_panel_retries": 1,
    "confirm_publish_retries": 1,
    "body_fill_retries": 2,
    "between_step_ms": 800,
    "final_browser_hold_ms": 20_000,
}

# hymini11: mainFrame·SE ONE 로딩이 느릴 때 — 재시도·대기를 더 길게
_NAVER_TUNING_HYMINI11: dict[str, int] = {
    "main_frame_timeout_ms": 120_000,
    "main_frame_retry_timeout_ms": 75_000,
    "main_frame_retries": 6,
    "recovery_retries": 4,
    "goto_wait_ms": 4_500,
    "retry_goto_wait_ms": 3_800,
    "reload_wait_ms": 3_200,
    "page_goto_timeout_ms": 120_000,
    "smart_editor_timeout_ms": 70_000,
    "post_editor_settle_ms": 4_500,
    "write_ready_retries": 3,
    "publish_panel_retries": 4,
    "confirm_publish_retries": 4,
    "body_fill_retries": 4,
    "between_step_ms": 1_400,
    "final_browser_hold_ms": 35_000,
}


def _naver_tuning(blog_id: str) -> dict[str, int]:
    bid = (blog_id or "").strip().lower()
    if bid == "hymini11":
        return dict(_NAVER_TUNING_HYMINI11)
    return dict(_NAVER_TUNING_DEFAULT)


def _is_naver_login(url: str) -> bool:
    u = (url or "").lower()
    return "nidlogin" in u or "nid.naver.com/nidlogin" in u


def _get_main_frame(page: Any, *, timeout_ms: int = 90000) -> Any:
    try:
        page.wait_for_selector("iframe#mainFrame, iframe[name='mainFrame']", timeout=timeout_ms)
        page.wait_for_timeout(2000)
    except Exception:
        # 최근 UI에서 iframe 없이 에디터가 루트 문서에 뜨는 경우가 있음
        for root_sel in (
            ".se-main-container",
            ".se-documentTitle",
            ".se-title-text",
        ):
            try:
                if page.locator(root_sel).first.count() > 0:
                    return page
            except Exception:
                continue
    frame = page.frame(name="mainFrame")
    if frame is None:
        for fr in page.frames:
            name = (fr.name or "").lower()
            url = (fr.url or "").lower()
            if name == "mainframe" or "postwrite" in url or "blog.naver.com" in url:
                frame = fr
                break
    if frame is None:
        raise RuntimeError("네이버 mainFrame을 찾을 수 없습니다. 글쓰기 화면인지 확인하세요.")
    return frame


def _get_main_frame_with_retry(
    page: Any,
    *,
    emit: Callable[[str], None],
    blog_write_url: str,
    blog_id: str,
    retries: int | None = None,
    tuning: dict[str, int] | None = None,
) -> Any:
    """mainFrame 탐색 실패 시 글쓰기 URL 재진입 후 재시도."""
    t = tuning or _naver_tuning(blog_id)
    max_try = retries if retries is not None else int(t["main_frame_retries"])
    timeout_ms = int(t["main_frame_retry_timeout_ms"])
    retry_wait = int(t["retry_goto_wait_ms"])
    reload_wait = int(t["reload_wait_ms"])
    goto_timeout = int(t["page_goto_timeout_ms"])
    last_err: Exception | None = None
    for i in range(1, max_try + 1):
        try:
            return _get_main_frame(page, timeout_ms=timeout_ms)
        except Exception as e:
            last_err = e
            emit(f"[네이버] mainFrame 탐색 재시도 {i}/{max_try}...")
            try:
                _goto_write_page(
                    page,
                    blog_write_url=blog_write_url,
                    blog_id=blog_id,
                    emit=emit,
                    tuning=t,
                )
                page.wait_for_timeout(retry_wait)
            except Exception:
                page.reload(wait_until="domcontentloaded", timeout=goto_timeout)
                page.wait_for_timeout(reload_wait)
    raise RuntimeError(f"mainFrame 재시도 실패: {last_err}")


def _dismiss_popups(frame: Any, page: Any) -> None:
    for _ in range(2):
        page.keyboard.press("Escape")
        page.wait_for_timeout(200)
    try:
        frame.evaluate(
            """() => {
              document.querySelectorAll('.se-selection, .se-popup-dim').forEach(el => {
                el.style.pointerEvents = 'none';
                el.style.display = 'none';
              });
            }"""
        )
    except Exception:
        pass
    for sel in (
        "button:has-text('취소')",
        "button:has-text('닫기')",
        "button:has-text('아니오')",
        ".se-popup-button-cancel",
    ):
        try:
            loc = frame.locator(sel).first
            if loc.count() > 0 and loc.is_visible():
                loc.click(timeout=1500)
                page.wait_for_timeout(400)
        except Exception:
            pass


def _goto_write_page(
    page: Any,
    *,
    blog_write_url: str,
    blog_id: str = "",
    emit: Callable[[str], None],
    tuning: dict[str, int] | None = None,
) -> None:
    t = tuning or _naver_tuning(blog_id)
    goto_timeout = int(t["page_goto_timeout_ms"])
    settle = int(t["goto_wait_ms"])
    direct = (blog_write_url or naver_write_url(blog_id) or "").strip()
    if direct and ("PostWriteForm" in direct or "Redirect=Write" in direct):
        emit(f"[네이버] 글쓰기 URL: {direct[:75]}...")
        page.goto(direct, wait_until="domcontentloaded", timeout=goto_timeout)
        page.wait_for_timeout(settle)
        return
    bid = (blog_id or get_naver_blog_id()).strip()
    if bid:
        url = f"https://blog.naver.com/{bid}?Redirect=Write&"
        emit(f"[네이버] 글쓰기 URL: {url}")
        page.goto(url, wait_until="domcontentloaded", timeout=goto_timeout)
        page.wait_for_timeout(settle)
        # Redirect=Write 실패 시 구형 PostWriteForm 폴백
        cur = (page.url or "").lower()
        if "postwriteform" not in cur and "redirect=write" not in cur and "mainframe" not in cur:
            fallback = f"https://blog.naver.com/PostWriteForm.naver?blogId={bid}"
            emit(f"[네이버] 글쓰기 폴백 URL: {fallback}")
            page.goto(fallback, wait_until="domcontentloaded", timeout=goto_timeout)
            page.wait_for_timeout(settle)
        return
    page.goto("https://blog.naver.com/", wait_until="domcontentloaded", timeout=goto_timeout)


def _wait_smart_editor(
    frame: Any,
    page: Any,
    *,
    tuning: dict[str, int] | None = None,
    blog_id: str = "",
) -> None:
    """스마트에디터 ONE 로드 대기."""
    t = tuning or _naver_tuning(blog_id)
    se_timeout = int(t["smart_editor_timeout_ms"])
    if hasattr(frame, "locator"):
        for sel in (
            ".se-documentTitle",
            ".se-title-text",
            ".se-main-container",
            ".se-component-content",
        ):
            try:
                frame.locator(sel).first.wait_for(state="visible", timeout=se_timeout)
                break
            except Exception:
                continue
    page.wait_for_timeout(int(t["post_editor_settle_ms"]))
    _dismiss_popups(frame, page)
    dismiss_editor_overlay(frame, page)
    focus_body_paragraph(frame, page)
    page.wait_for_timeout(int(t["between_step_ms"]))


def _title_locator(frame: Any) -> Any:
    """제목 전용 — 본문(.se-main-container)과 분리."""
    loc = frame.locator(
        ".se-documentTitle .se-text-paragraph, "
        ".se-documentTitle [contenteditable='true'], "
        ".se-title-text"
    ).first
    return loc


def _body_locator(frame: Any) -> Any:
    """본문 첫 문단 — 제목(.se-documentTitle) 영역 제외."""
    selectors = (
        ".se-main-container .se-component.se-text .se-text-paragraph",
        ".se-main-container .se-section-text .se-text-paragraph",
        ".se-main-container .se-text-paragraph",
        ".se-component.se-text .se-text-paragraph",
        ".se-canvas-bottom .se-text-paragraph",
        ".se-component-content[contenteditable='true']",
    )
    for sel in selectors:
        try:
            loc = frame.locator(sel).first
            if loc.count() > 0:
                return loc
        except Exception:
            continue
    return frame.locator(".se-main-container .se-text-paragraph").first


def _ensure_write_ready(
    page: Any,
    emit: Callable[[str], None],
    *,
    blog_write_url: str = "",
    blog_id: str = "",
    tuning: dict[str, int] | None = None,
) -> bool:
    """로그인·기기확인 후 글쓰기 화면인지 확인."""
    t = tuning or _naver_tuning(blog_id)
    max_try = int(t["write_ready_retries"])
    for attempt in range(1, max_try + 1):
        url = (page.url or "").lower()
        if _is_naver_login(url) or "deviceconfirm" in url:
            emit("[네이버] 로그인/기기 확인 대기...")
            from integrations.blog_browser_base import wait_for_url_change

            ok = wait_for_url_change(
                page,
                bad_url_checker=lambda u: _is_naver_login(u or "")
                or "deviceconfirm" in (u or "").lower(),
                on_status=emit,
                timeout_sec=150 if blog_id.lower() == "hymini11" else 120,
                message="네이버 로그인·기기 확인을 완료해 주세요.",
            )
            if not ok:
                return False
        cur = (page.url or "").lower()
        if (
            "postwriteform" in cur
            or "redirect=write" in cur
            or "mainframe" in cur
            or ".se-main-container" in cur
        ):
            return True
        if attempt < max_try:
            emit(f"[네이버] 글쓰기 화면 대기 재시도 {attempt}/{max_try}...")
            _goto_write_page(
                page,
                blog_write_url=blog_write_url,
                blog_id=blog_id,
                emit=emit,
                tuning=t,
            )
            page.wait_for_timeout(int(t["retry_goto_wait_ms"]))
    return False


def _split_body_sections(body_html: str, body_plain: str) -> list[str]:
    """h2 기준 본문 구간 분리 (이미지 교차 삽입용)."""
    html = strip_underline_html(body_html or "")
    parts = re.split(r"<h2[^>]*>(.*?)</h2>", html, flags=re.I | re.S)
    if len(parts) > 1:
        sections: list[str] = []
        if parts[0].strip():
            sections.append(plain_body(parts[0]))
        for i in range(1, len(parts), 2):
            heading = re.sub(r"<[^>]+>", "", parts[i]).strip()
            body = plain_body(parts[i + 1]) if i + 1 < len(parts) else ""
            block = f"{heading}\n\n{body}".strip() if heading else body
            if block:
                sections.append(block)
        return [s for s in sections if s.strip()]
    chunks = [c.strip() for c in body_plain.split("\n\n") if c.strip()]
    return chunks if chunks else [body_plain]


def _insert_image(frame: Any, page: Any, image_path: str, emit: Callable[[str], None]) -> bool:
    from pathlib import Path

    if not image_path or not Path(image_path).is_file():
        return False
    dismiss_editor_overlay(frame, page)
    path = str(Path(image_path).resolve())
    try:
        for sel in (
            "button.se-image-toolbar-button",
            "button[data-name='image']",
            "button:has-text('사진')",
            ".se-toolbar-item-image button",
        ):
            try:
                btn = frame.locator(sel).first
                if btn.count() <= 0 or not btn.is_visible():
                    continue
                # Windows 폴더 창 방지 — file chooser 가로채기
                try:
                    with page.expect_file_chooser(timeout=8000) as fc_info:
                        btn.click(timeout=5000, force=True)
                    fc_info.value.set_files(path)
                    page.wait_for_timeout(2800)
                    emit(f"[네이버] 이미지 삽입(Gemini 파일): {Path(path).name}")
                    return True
                except Exception:
                    pass
                # 숨겨진 input에 직접 주입 (폴더 UI 없음)
                for scope in (frame, page):
                    try:
                        fi = scope.locator("input[type='file']").last
                        if fi.count() > 0:
                            fi.set_input_files(path)
                            page.wait_for_timeout(2800)
                            emit(f"[네이버] 이미지 삽입: {Path(path).name}")
                            return True
                    except Exception:
                        continue
            except Exception:
                continue
        emit("[네이버] 이미지 업로드 실패")
        return False
    except Exception as e:
        emit(f"[네이버] 이미지 실패: {e}")
        return False


def _type_body_fallback(frame: Any, page: Any, text: str, emit: Callable[[str], None]) -> bool:
    """JS 실패 시 본문에 직접 타이핑."""
    dismiss_editor_overlay(frame, page)
    focus_body_paragraph(frame, page)
    try:
        loc = _body_locator(frame)
        if loc.count() == 0:
            return False
        loc.click(timeout=8000, force=True)
        page.wait_for_timeout(200)
        snippet = (text or "")[:3500]
        loc.press_sequentially(snippet, delay=12)
        page.wait_for_timeout(500)
        emit("[네이버] 본문 타이핑 폴백 사용")
        return body_text_length(frame) >= 40
    except Exception as e:
        emit(f"[네이버] 타이핑 폴백 실패: {e}")
        return False


def _insert_body_text(
    frame: Any,
    page: Any,
    text: str,
    emit: Callable[[str], None],
) -> bool:
    """본문 텍스트 삽입 + 검증."""
    dismiss_editor_overlay(frame, page)
    ins = insert_body_plain_text(frame, text, page)
    chars = int(ins.get("body_chars") or body_text_length(frame))
    emit(f"[네이버] 본문 JS 삽입: {ins.get('reason', '?')} · 글자수 {chars}")

    min_need = min(80, max(30, len(text) // 10))
    if chars >= min_need and ins.get("ok"):
        return True

    emit("[네이버] 본문이 비어 있음 — 붙여넣기·타이핑 재시도")
    dismiss_editor_overlay(frame, page)
    focus_body_paragraph(frame, page)
    try:
        loc = _body_locator(frame)
        loc.click(timeout=5000, force=True)
        page.wait_for_timeout(200)
        paste_in_locator(loc, text, strip_underline=True)
        page.wait_for_timeout(800)
        if body_text_length(frame) >= min_need:
            return True
    except Exception:
        pass

    return _type_body_fallback(frame, page, text, emit)


def _fill_body_with_images(
    frame: Any,
    page: Any,
    *,
    title: str,
    body_html: str,
    body_plain: str,
    images: list[str],
    emit: Callable[[str], None],
    blog_id: str = "",
    tuning: dict[str, int] | None = None,
) -> dict[str, Any]:
    """제목 → 본문 텍스트(JS) → 이미지(본문 블록) 순."""
    t = tuning or _naver_tuning(blog_id)
    step = int(t["between_step_ms"])
    result = {
        "title_ok": False,
        "body_ok": False,
        "images_inserted": 0,
        "body_chars": 0,
    }

    title_loc = _title_locator(frame)
    if title_loc.count() > 0:
        result["title_ok"] = fill_title_editable(title_loc, title)
        emit(f"[네이버] 제목 입력: {title[:50]}...")
    else:
        emit("[네이버] 제목 영역 없음")

    page.wait_for_timeout(step)

    valid_images = [p for p in images if p]
    img_wait = step + (600 if blog_id.lower() == "hymini11" else 200)

    # 이미지 먼저 → 본문 글 (이미지 삽입 시 기존 텍스트가 지워지는 SE 동작 대응)
    for img in valid_images:
        dismiss_editor_overlay(frame, page)
        if _insert_image(frame, page, img, emit):
            result["images_inserted"] += 1
        page.wait_for_timeout(img_wait)

    dismiss_editor_overlay(frame, page)
    focus_body_paragraph(frame, page)
    click_new_text_block(frame, page)
    page.wait_for_timeout(step)

    body_retries = int(t["body_fill_retries"])
    for attempt in range(1, body_retries + 1):
        if _insert_body_text(frame, page, body_plain, emit):
            break
        if attempt < body_retries:
            emit(f"[네이버] 본문 재시도 {attempt}/{body_retries}...")
            page.wait_for_timeout(step)
            dismiss_editor_overlay(frame, page)
            focus_body_paragraph(frame, page)
            click_new_text_block(frame, page)

    result["body_chars"] = body_text_length(frame)
    if result["body_chars"] < 40 and valid_images:
        emit("[네이버] 본문 재삽입 (이미지 아래)...")
        click_new_text_block(frame, page)
        _insert_body_text(frame, page, body_plain, emit)
        result["body_chars"] = body_text_length(frame)

    result["body_chars"] = body_text_length(frame)
    result["body_ok"] = result["body_chars"] >= min(80, max(40, len(body_plain) // 15))

    emit(
        f"[네이버] 본문 {'OK' if result['body_ok'] else '실패'} — "
        f"글자 {result['body_chars']}자, 이미지 {result['images_inserted']}장"
    )
    return result


def _fill_naver_tags(frame: Any, page: Any, tags: list[str], emit: Callable[[str], None]) -> int:
    """발행 레이어/에디터 태그 입력 — 최대 30개."""
    tag_list: list[str] = []
    for t in tags or []:
        t = re.sub(r"^#+", "", (t or "").strip())
        if t and t not in tag_list:
            tag_list.append(t[:30])
    tag_list = tag_list[:30]
    if not tag_list:
        return 0
    dismiss_editor_overlay(frame, page)
    filled = 0
    scopes = (frame, page)
    selectors = (
        "input#tag_input",
        "input[placeholder*='태그']",
        "input[placeholder*='tag']",
        "input[placeholder*='Tag']",
        "input[name*='tag']",
        "input[id*='tag']",
        ".tag_input input",
        ".publish_tag input",
        ".publish_layer input[type='text']",
        ".se-tag-input",
        "#tagList input",
        "[class*='TagInput'] input",
        "[class*='tag_input'] input",
        "input[data-testid*='tag']",
        "input[aria-label*='태그']",
        "input[aria-label*='해시태그']",
    )
    for scope in scopes:
        for sel in selectors:
            try:
                loc = scope.locator(sel).first
                if loc.count() == 0 or not loc.is_visible():
                    continue
                loc.click(timeout=3000)
                page.wait_for_timeout(200)
                for t in tag_list:
                    loc.fill(t)
                    page.keyboard.press("Enter")
                    page.wait_for_timeout(120)
                    filled += 1
                if filled > 0:
                    emit(f"[네이버] 해시태그 {filled}개 입력")
                    return min(filled, 30)
            except Exception:
                continue
    # 일괄 붙여넣기 폴백
    tag_str = ",".join(tag_list[:30])
    for scope in scopes:
        for sel in selectors:
            try:
                loc = scope.locator(sel).first
                if loc.count() > 0:
                    loc.fill(tag_str)
                    emit(f"[네이버] 해시태그 일괄 입력 {len(tag_list)}개")
                    return len(tag_list)
            except Exception:
                continue
    emit("[네이버] 태그 입력란을 찾지 못함 — 발행 창에서 수동 입력")
    return 0


def _open_publish_panel(
    frame: Any,
    page: Any,
    emit: Callable[[str], None],
    *,
    blog_id: str = "",
    tuning: dict[str, int] | None = None,
) -> bool:
    """발행 설정 패널만 연다 (태그 입력 전)."""
    t = tuning or _naver_tuning(blog_id)
    aggressive = blog_id.lower() == "hymini11"
    panel_retries = int(t["publish_panel_retries"])
    click_timeout = 12_000 if aggressive else 6000
    settle = int(t["between_step_ms"]) + (900 if aggressive else 700)
    dismiss_editor_overlay(frame, page)
    for attempt in range(1, panel_retries + 1):
        for sel in (
            "button:has-text('발행')",
            "button[aria-label*='발행']",
            "button[title*='발행']",
            "button.publish_btn__m9KHH",
            "button.se-publish-button",
            ".publish_btn",
        ):
            for scope in (frame, page):
                try:
                    btn = scope.locator(sel).first
                    if btn.count() > 0 and btn.is_visible():
                        btn.click(timeout=click_timeout, force=True)
                        page.wait_for_timeout(settle)
                        emit("[네이버] 발행 설정 열기")
                        return True
                except Exception:
                    continue
        if attempt < panel_retries:
            emit(f"[네이버] 발행 패널 재시도 {attempt}/{panel_retries}...")
            page.wait_for_timeout(settle)
    return False


def _confirm_publish(
    frame: Any,
    page: Any,
    emit: Callable[[str], None],
    *,
    blog_id: str = "",
    tuning: dict[str, int] | None = None,
) -> bool:
    """발행 패널에서 최종 발행·확인."""
    t = tuning or _naver_tuning(blog_id)
    aggressive = blog_id.lower() == "hymini11"
    confirm_retries = int(t["confirm_publish_retries"])
    click_timeout = 12_000 if aggressive else 4000
    settle = int(t["post_editor_settle_ms"]) // 2
    max_btns = 12 if aggressive else 8
    for attempt in range(1, confirm_retries + 1):
        for sel in (
            "button:has-text('발행')",
            "button:has-text('확인')",
            "button:has-text('등록')",
            "button[aria-label*='발행']",
            "button.publish_confirm",
            ".confirm_btn",
            ".se-publish-confirm-button",
        ):
            for scope in (frame, page):
                try:
                    btns = scope.locator(sel)
                    for i in range(min(btns.count(), max_btns)):
                        b = btns.nth(i)
                        if b.is_visible():
                            b.click(timeout=click_timeout, force=True)
                            page.wait_for_timeout(settle)
                            emit("[네이버] 발행 확인 클릭")
                            return True
                except Exception:
                    continue
        if attempt < confirm_retries:
            emit(f"[네이버] 발행 확정 재시도 {attempt}/{confirm_retries}...")
            page.wait_for_timeout(settle)
    return False


def login_naver_blog(
    *,
    naver_target: dict[str, Any] | None = None,
    on_status: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    emit = on_status or print
    target = naver_target or {}
    blog_id = (target.get("blog_id") or get_naver_blog_id()).strip()
    label = target.get("label") or blog_id or "naver"
    browser_dir = target.get("browser_dir")
    emit(f"\n=== [{label}] 네이버 로그인 ({blog_id}) ===")
    p, ctx, page = launch_context("naver", browser_dir_rel=browser_dir)
    try:
        page.goto("https://nid.naver.com/nidlogin.login", wait_until="domcontentloaded", timeout=60000)
        acc = get_naver_account_for_blog(blog_id)
        r = ensure_logged_in(
            "naver",
            page,
            is_login_url=_is_naver_login,
            naver_account=acc,
            naver_blog_id=blog_id,
            on_status=emit,
        )
        if r.get("ok"):
            _goto_write_page(page, blog_write_url="", blog_id=blog_id, emit=emit)
            emit(f"[{label}] 로그인·글쓰기 — {page.url[:80]}")
        return {**r, "platform": "naver", "url": page.url, "blog_id": blog_id, "label": label}
    finally:
        emit("[네이버] 10초 후 브라우저 종료 (세션 저장)")
        page.wait_for_timeout(10000)
        ctx.close()
        p.stop()


def publish_naver_blog(
    *,
    title: str,
    body_html: str,
    tags: list[str] | None = None,
    image_paths: list[str] | None = None,
    video_path: str = "",
    blog_write_url: str = "",
    naver_target: dict[str, Any] | None = None,
    on_status: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    emit = on_status or print
    tags = tags or []
    images = [p for p in (image_paths or []) if p]
    body_html = strip_underline_html(body_html)
    body_plain = plain_body(body_html)
    target = naver_target or {}
    blog_id = (target.get("blog_id") or get_naver_blog_id()).strip()
    label = target.get("label") or blog_id or "naver"
    browser_dir = target.get("browser_dir")

    tuning = _naver_tuning(blog_id)
    aggressive = blog_id.lower() == "hymini11"
    if aggressive:
        emit(f"[{label}] hymini11 공격적 대기·재시도 프로필 적용")

    p, ctx, page = launch_context("naver", browser_dir_rel=browser_dir)
    try:
        emit(f"[{label}] 글쓰기 시작 ({blog_id})...")
        _goto_write_page(
            page,
            blog_write_url=blog_write_url,
            blog_id=blog_id,
            emit=emit,
            tuning=tuning,
        )

        naver_acc = get_naver_account_for_blog(blog_id)
        if _is_naver_login(page.url) or "deviceconfirm" in (page.url or "").lower():
            lr = ensure_logged_in(
                "naver",
                page,
                is_login_url=_is_naver_login,
                naver_account=naver_acc,
                naver_blog_id=blog_id,
                on_status=emit,
            )
            if not lr.get("ok"):
                return {"ok": False, "platform": "naver", "error": "로그인 필요", "login": lr}
            _goto_write_page(
                page,
                blog_write_url=blog_write_url,
                blog_id=blog_id,
                emit=emit,
                tuning=tuning,
            )

        if not _ensure_write_ready(
            page,
            emit,
            blog_write_url=blog_write_url,
            blog_id=blog_id,
            tuning=tuning,
        ):
            emit("[네이버] 글쓰기 화면 재진입 시도...")
            _goto_write_page(
                page,
                blog_write_url=blog_write_url,
                blog_id=blog_id,
                emit=emit,
                tuning=tuning,
            )
            if not _ensure_write_ready(
                page,
                emit,
                blog_write_url=blog_write_url,
                blog_id=blog_id,
                tuning=tuning,
            ):
                return {"ok": False, "platform": "naver", "error": "글쓰기 화면 진입 실패"}

        frame = _get_main_frame_with_retry(
            page,
            emit=emit,
            blog_write_url=blog_write_url,
            blog_id=blog_id,
            tuning=tuning,
        )
        _wait_smart_editor(frame, page, tuning=tuning, blog_id=blog_id)

        fill_r = _fill_body_with_images(
            frame,
            page,
            title=title,
            body_html=body_html,
            body_plain=body_plain,
            images=images,
            emit=emit,
            blog_id=blog_id,
            tuning=tuning,
        )

        if video_path:
            emit("[네이버] 동영상 업로드 (--with-video 사용 시)")
            try:
                frame.locator(
                    "button:has-text('동영상'), .se-video-toolbar-button"
                ).first.click(timeout=3000)
                page.wait_for_timeout(500)
                with page.expect_file_chooser(timeout=8000) as fc_info:
                    frame.locator("button:has-text('동영상')").first.click(timeout=3000)
                fc_info.value.set_files(video_path)
                page.wait_for_timeout(3000)
            except Exception as ex:
                emit(f"[네이버] 동영상: {ex}")

        # 제목·본문·이미지 완료 후 → 발행창 → 해시태그 30 → 발행
        emit("[네이버] 순서: 제목·이미지·본문 완료 → 발행창 → 해시태그30 → 발행")
        panel_open = _open_publish_panel(
            frame, page, emit, blog_id=blog_id, tuning=tuning
        )
        if not panel_open:
            emit("[네이버] 발행 패널 자동 열기 실패 — 에디터 발행 버튼 확인")
        page.wait_for_timeout(int(tuning["between_step_ms"]) + 500)
        tags_count = _fill_naver_tags(frame, page, tags, emit)
        published = _confirm_publish(
            frame, page, emit, blog_id=blog_id, tuning=tuning
        )

        core_ok = bool(fill_r.get("title_ok") and fill_r.get("body_ok") and published)
        tags_ok = tags_count >= min(30, len(tags)) if tags else True
        emit(
            f"[네이버] 발행 {'완료' if published else '버튼 확인 필요'} · "
            f"태그 {tags_count}개"
        )
        if core_ok and not tags_ok and tags:
            emit("[네이버] 본문·발행 OK — 해시태그는 발행창에서 수동 보완 권장")
        return {
            "ok": core_ok,
            "platform": "naver",
            "published_clicked": published,
            "title_filled": fill_r.get("title_ok"),
            "body_filled": fill_r.get("body_ok"),
            "tags_filled": tags_count,
            "tags_ok": tags_ok,
            "images_inserted": fill_r.get("images_inserted", 0),
            "body_chars": fill_r.get("body_chars", 0),
            "url": page.url,
            "blog_id": blog_id,
            "label": label,
            "naver_tuning": "hymini11" if aggressive else "default",
        }
    except Exception as e:
        # 프레임/에디터 계열은 자동 복구 시도 (hymini11은 재시도 더 많음)
        msg = str(e)
        if any(k in msg.lower() for k in ("mainframe", "wait_for_selector", "timeout")):
            try:
                recover_n = int(tuning["recovery_retries"])
                emit(f"[{label}] 자동 복구: 글쓰기 재진입 후 최대 {recover_n}회 재시도...")
                _goto_write_page(
                    page,
                    blog_write_url=blog_write_url,
                    blog_id=blog_id,
                    emit=emit,
                    tuning=tuning,
                )
                frame = _get_main_frame_with_retry(
                    page,
                    emit=emit,
                    blog_write_url=blog_write_url,
                    blog_id=blog_id,
                    tuning=tuning,
                )
                _wait_smart_editor(frame, page, tuning=tuning, blog_id=blog_id)
                fill_r = _fill_body_with_images(
                    frame,
                    page,
                    title=title,
                    body_html=body_html,
                    body_plain=body_plain,
                    images=images,
                    emit=emit,
                    blog_id=blog_id,
                    tuning=tuning,
                )
                _open_publish_panel(
                    frame, page, emit, blog_id=blog_id, tuning=tuning
                )
                tags_count = _fill_naver_tags(frame, page, tags, emit)
                published = _confirm_publish(
                    frame, page, emit, blog_id=blog_id, tuning=tuning
                )
                core_ok = bool(fill_r.get("title_ok") and fill_r.get("body_ok") and published)
                tags_ok = tags_count >= min(30, len(tags)) if tags else True
                return {
                    "ok": core_ok,
                    "platform": "naver",
                    "published_clicked": published,
                    "title_filled": fill_r.get("title_ok"),
                    "body_filled": fill_r.get("body_ok"),
                    "tags_filled": tags_count,
                    "tags_ok": tags_ok,
                    "images_inserted": fill_r.get("images_inserted", 0),
                    "body_chars": fill_r.get("body_chars", 0),
                    "url": page.url,
                    "blog_id": blog_id,
                    "label": label,
                    "recovered_once": True,
                    "naver_tuning": "hymini11" if aggressive else "default",
                }
            except Exception as e2:
                return {
                    "ok": False,
                    "platform": "naver",
                    "blog_id": blog_id,
                    "label": label,
                    "error": f"{msg} | recover_failed: {e2}",
                }
        return {"ok": False, "platform": "naver", "blog_id": blog_id, "label": label, "error": msg}
    finally:
        hold_ms = int(_naver_tuning(blog_id).get("final_browser_hold_ms", 20_000))
        emit(f"[네이버] 확인 후 {hold_ms // 1000}초 뒤 브라우저 종료...")
        try:
            page.wait_for_timeout(hold_ms)
        except Exception:
            pass
        ctx.close()
        p.stop()
