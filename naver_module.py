import asyncio
import os
import random
import re
import io
import pyperclip
from datetime import datetime, timedelta
from PIL import Image
import sys

if sys.platform == "win32":
    import win32clipboard
    # Blogger에서 사용하던 HTML 클립보드 유틸 재사용
    from blogger_browser import _set_html_clipboard_win

from blog_text_utils import strip_strikethrough_markers

_SMART_EDITOR_SELECTOR = ".se-documentTitle, .se-canvas, .se-main-container, .se-edit-area"
_WRITE_BTN_SELECTORS = (
    "a#btn_write_top",
    "a.btn_write",
    ".btn_area_write a",
    "a:has-text('글쓰기')",
    "span:has-text('글쓰기')",
)


def _clean_style_line_through(m, quote):
    """style 속성에서 line-through만 제거 (취소선 제거, hymini11 등)."""
    if not m or not m.group(1):
        return m.group(0) if m else ""
    s = re.sub(r"text-decoration\s*:\s*line-through\s*;?\s*", "", m.group(1), flags=re.I)
    s = re.sub(r";\s*;", ";", s).strip("; ")
    return f" style={quote}{s}{quote}" if s else ""


def _markdown_table_to_html(table_text: str) -> str:
    """
    마크다운 표(|로 시작하는 줄들)를 네이버/티스토리 에디터가 인식 가능한 <table> HTML로 변환.
    **텍스트**는 <b>텍스트</b>로 바꿔서 굵게 표시한다.
    """
    lines = [ln.strip() for ln in table_text.splitlines() if ln.strip()]
    if len(lines) < 2:
        return ""

    def parse_row(line: str):
        cells = [c.strip() for c in line.strip("|").split("|")]
        bolded = []
        for c in cells:
            # 마크다운 굵게(**텍스트**) → HTML <b>
            c_html = re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", c)
            bolded.append(c_html)
        return bolded

    header_cells = parse_row(lines[0])
    data_lines = lines[2:] if "---" in lines[1] else lines[1:]
    body_rows = [parse_row(ln) for ln in data_lines if ln.strip().startswith("|") or "|" in ln]

    if not body_rows:
        return ""

    tbl_style = (
        "border-collapse:collapse; margin:1.2em 0; width:100%; "
        "table-layout:fixed; font-size:0.95em;"
    )
    th_style = (
        "border:1px solid #bbb; padding:10px 12px; background:#f8f8f8; "
        "font-weight:bold; text-align:left; vertical-align:top;"
    )
    td_style = (
        "border:1px solid #ddd; padding:10px 12px; vertical-align:top; "
        "word-break:break-word;"
    )

    def cells_to_html(tag, style, cells):
        return "".join(f"<{tag} style=\"{style}\">{c}</{tag}>" for c in cells)

    thead = f"<thead><tr>{cells_to_html('th', th_style, header_cells)}</tr></thead>"
    tbody_rows = []
    for row in body_rows:
        tbody_rows.append(f"<tr>{cells_to_html('td', td_style, row)}</tr>")
    tbody = "<tbody>" + "".join(tbody_rows) + "</tbody>"
    return f"<table style=\"{tbl_style}\">{thead}{tbody}</table>"


async def _dismiss_file_transfer_error(page, log_func):
    """'파일 전송 오류' 팝업이 떠 있으면 확인 버튼을 눌러 닫는다. (hymini1 등 이미지 업로드 중 발생 시)"""
    try:
        err_loc = page.get_by_text("파일 전송 오류").or_(page.get_by_text("일시적으로 파일전송"))
        if await err_loc.count() > 0 and await err_loc.first.is_visible(timeout=500):
            ok_btn = page.locator("button:has-text('확인')").first
            if await ok_btn.count() > 0 and await ok_btn.is_visible(timeout=1000):
                await ok_btn.click()
                if log_func:
                    log_func("      ⚠️ '파일 전송 오류' 창이 떴습니다. 확인 버튼을 눌러 계속 진행합니다.")
                await asyncio.sleep(0.5)
                return True
    except Exception:
        pass
    return False


class NaverBlogWriter:
    def __init__(self, page, log_func):
        self.page = page
        self.log = log_func
        self.wait_func = None

    async def wait(self, seconds):
        if self.wait_func:
            await self.wait_func(seconds)
        else:
            await asyncio.sleep(seconds)

    async def _recover_from_login_redirect(self, naver_id, naver_pw):
        """글쓰기 URL 접속 시 로그인 페이지로 튕긴 경우 자동 로그인."""
        if "nid.naver.com" not in (self.page.url or ""):
            return True
        self.log("      🔑 로그인 페이지로 이동됨 — 자동 로그인을 시도합니다...")
        if not naver_pw:
            self.log(f"      ❌ [{naver_id}] 로그인이 필요하지만 패스워드가 없습니다.")
            return False
        if not await self._handle_login(naver_id, naver_pw):
            return False
        if "nid.naver.com" in (self.page.url or ""):
            self.log("      ❌ 로그인 후에도 로그인 페이지에 머물러 있습니다. (캡차·2단계 인증 확인)")
            return False
        return True

    async def _get_main_frame(self):
        el = await self.page.query_selector("#mainFrame")
        if el:
            return await el.content_frame()
        return None

    async def _is_smart_editor_visible(self, ctx):
        """제목+본문 영역이 모두 있어야 실제 글쓰기 화면으로 판단."""
        if ctx is None:
            return False
        try:
            has_title = await ctx.locator(".se-documentTitle").count() > 0
            has_body = await ctx.locator(
                ".se-text-paragraph, .se-component-text, .se-section-text, .se-canvas"
            ).count() > 0
            return has_title and has_body
        except Exception:
            return False

    async def _get_title_text_length(self, frame) -> int:
        try:
            return int(
                await frame.evaluate(
                    """() => {
                        const t = document.querySelector('.se-documentTitle [contenteditable="true"]')
                            || document.querySelector('.se-documentTitle');
                        return ((t && (t.innerText || t.textContent)) || '').trim().length;
                    }"""
                )
            )
        except Exception:
            return 0

    async def _get_body_text_length(self, frame) -> int:
        try:
            return int(
                await frame.evaluate(
                    """() => {
                        const title = document.querySelector('.se-documentTitle');
                        const parts = [];
                        const nodes = document.querySelectorAll(
                            '.se-text-paragraph, .se-component-text, .se-section-text p'
                        );
                        for (const n of nodes) {
                            if (title && title.contains(n)) continue;
                            const t = (n.innerText || n.textContent || '').trim();
                            if (t) parts.push(t);
                        }
                        if (!parts.length) {
                            const edits = [...document.querySelectorAll('[contenteditable="true"]')]
                                .filter(e => !title || !title.contains(e));
                            for (const e of edits) {
                                const t = (e.innerText || e.textContent || '').trim();
                                if (t) parts.push(t);
                            }
                        }
                        return parts.join(' ').trim().length;
                    }"""
                )
            )
        except Exception:
            return 0

    async def _focus_title_area(self, frame) -> bool:
        for sel in (
            ".se-documentTitle [contenteditable='true']",
            ".se-documentTitle",
            ".se-placeholder:has-text('제목')",
        ):
            try:
                el = self._get_locator(frame, sel).first
                if await el.count() > 0:
                    await el.scroll_into_view_if_needed(timeout=5000)
                    await el.click(force=True, timeout=5000)
                    await self.wait(0.3)
                    return True
            except Exception:
                continue
        return False

    async def _focus_body_area(self, frame) -> bool:
        try:
            ok = await frame.evaluate(
                """() => {
                    const title = document.querySelector('.se-documentTitle');
                    const pick = (nodes) => {
                        for (const el of nodes) {
                            if (title && title.contains(el)) continue;
                            const r = el.getBoundingClientRect();
                            if (r.width < 2 || r.height < 2) continue;
                            el.focus();
                            el.click();
                            return true;
                        }
                        return false;
                    };
                    if (pick(document.querySelectorAll(
                        '.se-text-paragraph [contenteditable="true"], .se-component-text [contenteditable="true"]'
                    ))) return true;
                    if (pick(document.querySelectorAll('.se-main-container [contenteditable="true"]'))) return true;
                    const block = document.querySelector('.se-text-paragraph, .se-section-text, .se-canvas');
                    if (block) { block.click(); return true; }
                    return false;
                }"""
            )
            if ok:
                await self.wait(0.3)
            return bool(ok)
        except Exception:
            return False

    async def _resolve_editor_handle(self, frame=None):
        """FrameLocator 등 evaluate 불가 객체를 Frame/Page로 변환."""
        from playwright.async_api import Frame, Page

        if isinstance(frame, (Page, Frame)):
            return frame
        if frame is not None and hasattr(frame, "evaluate"):
            return frame
        mf = await self._get_main_frame()
        if mf and await self._is_smart_editor_visible(mf):
            return mf
        if await self._is_smart_editor_visible(self.page):
            return self.page
        return mf or self.page

    async def _click_write_button(self, ctx):
        for sel in _WRITE_BTN_SELECTORS:
            try:
                btn = ctx.locator(sel).first
                if await btn.count() > 0 and await btn.is_visible():
                    self.log(f"      🖱 글쓰기 버튼 클릭 ({sel})")
                    await btn.click()
                    await self.wait(3)
                    return True
            except Exception:
                continue
        return False

    async def _wait_until_editor_ready(self, naver_id, naver_pw, timeout_sec=45):
        self.log(f"      ⏳ 스마트에디터 로드 대기 (최대 {timeout_sec}초)...")
        for i in range(timeout_sec):
            url = self.page.url or ""
            if "nid.naver.com" in url:
                if not await self._recover_from_login_redirect(naver_id, naver_pw):
                    return None
                await self.page.goto(
                    "https://blog.naver.com/GoBlogWrite.naver",
                    wait_until="domcontentloaded",
                    timeout=30000,
                )
                await self.wait(3)
                continue

            if "editor.blog.naver.com" in url and await self._is_smart_editor_visible(self.page):
                return await self._resolve_editor_handle(self.page)

            mf = await self._get_main_frame()
            if mf and await self._is_smart_editor_visible(mf):
                return mf

            if "blog.naver.com" in url and "editor.blog.naver.com" not in url:
                if mf and i % 3 == 0:
                    await self._click_write_button(mf)
                elif i % 5 == 0:
                    await self.page.goto(
                        "https://blog.naver.com/GoBlogWrite.naver",
                        wait_until="domcontentloaded",
                        timeout=25000,
                    )
                    await self.wait(2)

            if i > 0 and i % 10 == 0:
                self.log(f"      ⏳ 에디터 대기 중... ({url[:55]})")
            await self.wait(1)

        self.log(f"      ❌ 스마트에디터 로드 실패 (URL: {(self.page.url or '')[:70]})")
        return None

    async def _human_type_field(self, selector: str, value: str) -> None:
        """봇 탐지 완화: 한 글자씩 천천히 입력."""
        field = self.page.locator(selector).first
        await field.click()
        await self.wait(random.uniform(0.25, 0.55))
        try:
            await field.fill("")
        except Exception:
            await self.page.keyboard.press("Control+a")
            await self.page.keyboard.press("Backspace")
        for ch in value:
            await self.page.keyboard.type(ch, delay=random.randint(45, 130))
        await self.wait(random.uniform(0.2, 0.45))

    async def _paste_field(self, selector: str, value: str) -> None:
        """클립보드 붙여넣기 (폴백)."""
        await self.page.click(selector)
        await self.wait(0.35)
        pyperclip.copy(value)
        if sys.platform == "win32":
            await self.page.keyboard.press("Control+v")
        else:
            await self.page.keyboard.press("Meta+v")
        await self.wait(0.35)

    async def _is_login_challenge_visible(self) -> bool:
        """캡차·자동입력 방지·2단계 인증 화면."""
        checks = [
            "iframe[src*='captcha']",
            "#captcha",
            ".captcha",
            "text=자동입력 방지",
            "text=보안문자",
            "text=영수증",
            "text=기기를 등록",
            "text=OTP",
            "text=2단계",
        ]
        for sel in checks:
            try:
                loc = self.page.locator(sel).first
                if await loc.count() > 0 and await loc.is_visible(timeout=400):
                    return True
            except Exception:
                pass
        return False

    async def _wait_manual_login_completion(self, naver_id: str, max_sec: int = 240) -> bool:
        """캡차·2단계 등 수동 완료 대기."""
        if "nid.naver.com" not in (self.page.url or ""):
            return True
        if await self._is_login_challenge_visible():
            self.log(
                f"      [주의] [{naver_id}] 봇/캡차 검증이 감지되었습니다. "
                "브라우저 창에서 아이디·비밀번호·캡차를 직접 입력해 주세요."
            )
        else:
            self.log(
                f"      [주의] [{naver_id}] 추가 인증이 필요합니다. "
                "브라우저에서 로그인을 직접 완료해 주세요."
            )
        self.log(f"      최대 {max_sec}초 대기합니다...")
        try:
            await self.page.wait_for_url(
                lambda u: "nid.naver.com" not in (u or "")
                and ("blog.naver.com" in (u or "") or "www.naver.com" in (u or "")),
                timeout=max_sec * 1000,
            )
            self.log("      로그인·인증 완료 확인")
            return True
        except Exception:
            self.log("      로그인 대기 시간 초과 — 브라우저에서 직접 완료 후 다시 시도해 주세요.")
            return False

    async def _handle_login(self, naver_id, naver_pw):
        if not naver_pw:
            self.log(f"      ❌ [{naver_id}] 로그인이 필요하지만 패스워드가 없습니다.")
            return False

        self.log(f"      🔑 [{naver_id}] 자동 로그인 프로세스 시작...")
        try:
            try:
                await self.page.wait_for_selector("#id", timeout=15000)
            except Exception:
                self.log("      ⚠️ 로그인 필드(#id)를 찾을 수 없습니다. 페이지 재로딩...")
                await self.page.reload()
                await self.wait(3)
                await self.page.wait_for_selector("#id", timeout=10000)

            await self.wait(random.uniform(0.8, 1.6))
            if await self._is_login_challenge_visible():
                self.log(
                    f"      [주의] [{naver_id}] 로그인 화면에 보안 검증이 있습니다. "
                    "자동 입력을 건너뛰고 브라우저에서 직접 로그인해 주세요."
                )
                return await self._wait_manual_login_completion(naver_id, max_sec=240)

            for field, val in [("#id", naver_id), ("#pw", naver_pw)]:
                try:
                    await self._human_type_field(field, val)
                except Exception:
                    self.log(f"      ⚠️ {field} 직접 입력 실패 — 붙여넣기로 재시도")
                    await self._paste_field(field, val)

            await self.wait(random.uniform(0.4, 0.9))
            login_btn_selectors = [".btn_login", "#log\\.login", "button[type='submit']", ".btn_global"]
            btn_clicked = False
            for sel in login_btn_selectors:
                btn = self.page.locator(sel).first
                if await btn.count() > 0 and await btn.is_visible():
                    await btn.click()
                    btn_clicked = True
                    break

            if not btn_clicked:
                self.log("      ⚠️ 로그인 버튼을 찾지 못해 Enter 키를 입력합니다.")
                await self.page.keyboard.press("Enter")

            await self.wait(random.uniform(2.5, 4.0))

            if "nid.naver.com" in (self.page.url or ""):
                if not await self._wait_manual_login_completion(naver_id, max_sec=240):
                    return False

            for skip in [
                "button:has-text('등록안함')",
                "#new\\.dontsave",
                ".btn_cancel",
                "button:has-text('아니오')",
                "button:has-text('다음에')",
            ]:
                try:
                    btn = self.page.locator(skip).first
                    if await btn.count() > 0 and await btn.is_visible(timeout=500):
                        await btn.click()
                        await self.wait(2)
                        break
                except Exception:
                    pass
            return True
        except Exception as e:
            self.log(f"      ❌ 로그인 처리 중 오류: {e}")
            return False

    async def warmup_session(self, config_data):
        """에디터 진입 없이 네이버 홈 접속·로그인만 확인 (시작 지연 방지)."""
        naver_id = config_data if isinstance(config_data, str) else config_data.get("naver_id", "Unknown")
        naver_pw = config_data.get("naver_pw", "") if isinstance(config_data, dict) else ""
        self.log(f"   🔐 [{naver_id}] 네이버 로그인 세션 확인 중...")
        try:
            await self.page.bring_to_front()
            await self.page.goto("https://www.naver.com/", wait_until="domcontentloaded", timeout=45000)
            await self.wait(2)
            if await self.page.locator(
                ".MyView-module__my_info___S9Scl, .MyView-module__link_logout___vA6iS, a:has-text('로그아웃')"
            ).count() > 0:
                self.log(f"      ✅ [{naver_id}] 네이버 로그인됨")
                return True
            login_btn = None
            for sel in (
                "a.MyView-module__link_login___HpHMW",
                "a:has-text('로그인')",
                ".link_login",
                "#gnb_login_button",
            ):
                target = self.page.locator(sel).first
                if await target.count() > 0 and await target.is_visible():
                    login_btn = target
                    break
            if login_btn:
                await login_btn.click()
                try:
                    await self.page.wait_for_url(lambda u: "nid.naver.com" in u, timeout=15000)
                except Exception:
                    pass
                if await self._handle_login(naver_id, naver_pw):
                    self.log(f"      ✅ [{naver_id}] 네이버 로그인 완료")
                    return True
                self.log(f"      ⚠️ [{naver_id}] 네이버 로그인 실패 — 포스팅 단계에서 재시도")
                return False
            self.log(f"      ℹ️ [{naver_id}] 로그인 버튼 없음(세션 유지 추정)")
            return True
        except Exception as e:
            self.log(f"      ⚠️ [{naver_id}] 네이버 워밍업 오류: {e}")
            return False

    async def navigate_to_editor(self, config_data):
        naver_id = config_data if isinstance(config_data, str) else config_data.get("naver_id", "Unknown")
        naver_pw = config_data.get("naver_pw", "") if isinstance(config_data, dict) else ""
        
        self.log(f"   📝 [{naver_id}] 에디터 진입 시도 (네이버 홈 경유)...")
        await self.page.bring_to_front()
        
        # 1. 네이버 홈 접속
        try:
            self.log("      🌐 네이버 메인 접속 중: https://www.naver.com/")
            await self.page.goto("https://www.naver.com/", wait_until="domcontentloaded", timeout=45000)
            await self.wait(2)
            
            # 2. 로그인 여부 확인 및 로그인 단계 진행
            # 여러 패턴의 로그인 버튼/링크 탐색
            login_selectors = [
                "a.MyView-module__link_login___HpHMW", 
                "a:has-text('로그인')", 
                ".link_login", 
                "#gnb_login_button"
            ]
            
            is_logged_in = False
            # 먼저 로그인된 상태를 나타내는 요소가 있는지 확인
            if await self.page.locator(".MyView-module__my_info___S9Scl, .MyView-module__link_logout___vA6iS, a:has-text('로그아웃')").count() > 0:
                is_logged_in = True
                self.log("      ✅ 네이버 로그인 상태 확인됨")
            
            if not is_logged_in:
                login_btn = None
                for sel in login_selectors:
                    target = self.page.locator(sel).first
                    if await target.count() > 0 and await target.is_visible():
                        login_btn = target
                        break
                
                if login_btn:
                    self.log(f"      🔑 로그인 버튼 클릭 ({sel})...")
                    await login_btn.click()
                    try:
                        await self.page.wait_for_url(lambda u: "nid.naver.com" in u, timeout=15000)
                    except: pass
                    
                    if not await self._handle_login(naver_id, naver_pw):
                        self.log("      ❌ 로그인 프로세스 최종 실패")
                        return None
                    
                    if "www.naver.com" not in self.page.url:
                        await self.page.goto("https://www.naver.com/", wait_until="domcontentloaded")
                        await self.wait(2)
                else:
                    self.log("      ⚠️ 로그인 버튼을 찾을 수 없습니다. 직접 블로그 글쓰기 주소로 시도합니다.")
                    # 로그인 버튼 못 찾으면 세션이 살아있을 가능성 있으니 일단 진행

            # 3. 블로그 메뉴 및 글쓰기 버튼 찾기
            self.log("      📂 에디터 진입 및 버튼 탐색 중...")
            
            # 주소 후보군: 네이버 표준 글쓰기 URL 우선 사용 후, 계정별 Redirect URL 시도
            # (일부 계정은 로그인 아이디와 블로그 주소(ID)가 달라 selfcoat 같은 별칭을 쓰므로,
            #  GoBlogWrite → 계정별 Redirect 순서가 가장 안전하다.)
            direct_urls = [
                "https://blog.naver.com/GoBlogWrite.naver",
                f"https://blog.naver.com/{naver_id}?Redirect=Write",
            ]

            for durl in direct_urls:
                try:
                    self.log(f"      🚀 직접 주소 시도: {durl}")
                    await self.page.goto(durl, wait_until="load", timeout=20000)
                    await self.wait(3)
                    if not await self._recover_from_login_redirect(naver_id, naver_pw):
                        continue
                    if "nid.naver.com" in (self.page.url or ""):
                        continue
                    ready = await self._wait_until_editor_ready(naver_id, naver_pw, timeout_sec=25)
                    if ready:
                        await self._clear_editor_popups(ready)
                        self.log("      ✅ 에디터 진입 성공")
                        return ready
                except: continue

            # 만약 블로그 홈(/id)에 있다면 거기서 '글쓰기' 버튼 찾기
            if naver_id in self.page.url and "PostWrite" not in self.page.url:
                self.log(f"      📍 [{naver_id}] 블로그 홈 감지. 페이지 내 글쓰기 버튼 탐색...")
                # 블로그 내부의 글쓰기 버튼 리스트
                internal_write_selectors = [
                    "a#btn_write_top", "a.btn_write", ".btn_area_write a", 
                    "span:has-text('글쓰기')", "a:has-text('글쓰기')"
                ]
                for iws in internal_write_selectors:
                    btn = self.page.locator(iws).first
                    if await btn.count() > 0 and await btn.is_visible():
                        self.log(f"      🖱 내부 '{iws}' 클릭...")
                        await btn.click(); await self.wait(3); break

            # 네이버 메인 홈이라면 블로그 탭 클릭 (한정된 영역 내에서)
            if "www.naver.com" in self.page.url:
                self.log("      🖱 메인 MyView 영역 블로그 탭 클릭...")
                blog_tab = self.page.locator(".MyView-module__item_text___VTQQM").filter(has_text="블로그").first
                if await blog_tab.count() > 0:
                    await blog_tab.click(); await self.wait(2)

            # 사용자 제공 및 표준 글쓰기 버튼 셀렉터
            write_btn_selectors = [
                "a.item[alt='글쓰기']", 
                "a.MyView-module__link_tool___tAoH1.MyView-module__type_write___l9FOk",
                "a.MyView-module__type_write___l9FOk",
                "a.item:has-text('글쓰기')",
                "a[href*='GoBlogWrite.naver']"
            ]
            
            for ws in write_btn_selectors:
                btn = self.page.locator(ws).first
                if await btn.count() > 0 and await btn.is_visible():
                    self.log(f"      🖱 '{ws}' 버튼 클릭...")
                    try:
                        async with self.page.context.expect_page(timeout=10000) as new_page_info:
                            await btn.click()
                        self.page = await new_page_info.value
                        await self.page.bring_to_front()
                        self.log(f"      🆕 새 탭 에디터 진입: {self.page.url[:40]}...")
                        ready = await self._wait_until_editor_ready(naver_id, naver_pw, timeout_sec=30)
                        if ready:
                            await self._clear_editor_popups(ready)
                            return ready
                    except:
                        self.log("      ⚠️ 새 탭 전환 실패, 현재 페이지 이동 시도")
                        await self.page.goto("https://blog.naver.com/GoBlogWrite.naver", wait_until="domcontentloaded")
                        break
            
            # 최종 폴백
            self.log("      ⚠️ 최종 주소 강제 이동")
            await self.page.goto(f"https://blog.naver.com/{naver_id}?Redirect=Write", wait_until="domcontentloaded")

            ready = await self._wait_until_editor_ready(naver_id, naver_pw, timeout_sec=45)
            if ready:
                await self._clear_editor_popups(ready)
                self.log(f"      ✅ [{naver_id}] 에디터 준비 완료")
                return ready
            self.log(f"      ❌ 에디터 접속 실패 (최종 URL: {(self.page.url or '')[:60]})")
                
        except Exception as e:
            self.log(f"      ❌ 진입 중 치명적 오류: {str(e)[:100]}")
            
        return None

    async def _clear_editor_popups(self, frame):
        # 방해되는 팝업들 (불러오기 취소 등)
        pop_selectors = ["button:has-text('취소')", "button:has-text('닫기')", ".se-popup-button-cancel", ".se-help-panel-close-button"]
        for sel in pop_selectors:
            try:
                btn = frame.locator(sel).first
                if await btn.count() > 0 and await btn.is_visible():
                    await btn.click(); await self.wait(0.5)
            except: pass

    def _get_locator(self, frame, selector):
        """frame이 Page 또는 FrameLocator일 때 모두 동작하는 locator 반환"""
        try:
            return frame.locator(selector)
        except Exception:
            return self.page.locator(selector)

    async def _paste_plain_text(self, frame, text: str) -> bool:
        """본문 삽입. 성공 여부를 반환한다."""
        plain = strip_strikethrough_markers(text or "")
        if not plain.strip():
            return True

        before = await self._get_body_text_length(frame)
        if not await self._focus_body_area(frame):
            await self.page.keyboard.press("Tab")
            await self.wait(0.3)
            await self._focus_body_area(frame)

        chunks = [plain]
        if len(plain) > 1200:
            chunks = []
            buf = ""
            for para in plain.split("\n\n"):
                piece = para.strip()
                if not piece:
                    continue
                if buf and len(buf) + len(piece) + 2 > 1200:
                    chunks.append(buf)
                    buf = piece
                else:
                    buf = f"{buf}\n\n{piece}" if buf else piece
            if buf:
                chunks.append(buf)

        for chunk in chunks:
            pyperclip.copy(chunk)
            await self.page.keyboard.press("End")
            await self.wait(0.2)
            await self.page.keyboard.press("Control+v")
            await self.wait(0.5)
            if chunk != chunks[-1]:
                await self.page.keyboard.press("Enter")
                await self.page.keyboard.press("Enter")
                await self.wait(0.2)

        after = await self._get_body_text_length(frame)
        min_gain = max(20, len(plain) // 6)
        if after >= before + min_gain:
            return True

        try:
            await self._focus_body_area(frame)
            await frame.evaluate(
                """(t) => {
                    const title = document.querySelector('.se-documentTitle');
                    const edit = [...document.querySelectorAll('[contenteditable="true"]')]
                        .find(e => !title || !title.contains(e));
                    if (!edit) return false;
                    edit.focus();
                    return document.execCommand('insertText', false, t);
                }""",
                plain[:6000],
            )
            await self.wait(0.5)
        except Exception:
            pass

        after = await self._get_body_text_length(frame)
        return after >= before + min_gain

    async def _remove_strikethrough(self, frame):
        """
        에디터 안에서 취소선(<s>, <strike>, style, class) 제거. Naver2 취소선 계속 적용 대응.
        """
        script = """() => {
            const doc = document;
            // 1) <s>, <strike> 태그는 내용만 남기고 태그 제거
            for (const el of Array.from(doc.querySelectorAll('s, strike'))) {
                const parent = el.parentNode;
                if (!parent) continue;
                while (el.firstChild) parent.insertBefore(el.firstChild, el);
                parent.removeChild(el);
            }
            // 2) line-through 스타일 제거
            const styled = doc.querySelectorAll('[style*="line-through"]');
            for (const el of Array.from(styled)) {
                if (!el.style) continue;
                el.style.textDecoration = (el.style.textDecoration || '')
                    .replace(/line-through/gi, '')
                    .replace(/\\s+/g, ' ')
                    .trim();
                if (!el.style.textDecoration) el.style.removeProperty('text-decoration');
            }
            // 3) 취소선용 클래스 제거 (Naver2 스마트에디터 se-text-strikethrough 등)
            const byClass = doc.querySelectorAll('[class*="strikethrough"], [class*="strike-through"], [class*="se-text-strike"]');
            for (const el of Array.from(byClass)) {
                if (el.className && typeof el.className === 'string' && /strike/i.test(el.className)) {
                    el.removeAttribute('class');
                }
            }
            // 4) 모든 contenteditable 전체 선택 후 removeFormat
            const edits = doc.querySelectorAll('[contenteditable="true"]');
            for (const edit of Array.from(edits)) {
                try {
                    edit.focus();
                    const sel = doc.defaultView && doc.defaultView.getSelection();
                    if (sel) {
                        const r = doc.createRange();
                        r.selectNodeContents(edit);
                        sel.removeAllRanges();
                        sel.addRange(r);
                        doc.execCommand('removeFormat', false, null);
                        sel.removeAllRanges();
                    } else {
                        doc.execCommand('selectAll', false, null);
                        doc.execCommand('removeFormat', false, null);
                    }
                } catch (e2) {}
            }
        }"""
        try:
            await frame.evaluate(script)
        except Exception:
            pass

    async def write_content(self, frame, title, body, img_paths):
        try:
            title = strip_strikethrough_markers(title or "")
            body = strip_strikethrough_markers(body or "")
            self.log("      ✍ 네이버 본문 작성 프로세스 시작...")
            await self.page.bring_to_front()
            await self.wait(1)  # 에디터 로드 대기 (연속 발행 속도 개선)
            frame = await self._resolve_editor_handle(frame)
            if not await self._is_smart_editor_visible(frame):
                self.log("      ⚠️ 스마트에디터 영역 미감지 — 글쓰기 화면을 다시 엽니다.")
                await self.page.goto(
                    "https://blog.naver.com/GoBlogWrite.naver",
                    wait_until="domcontentloaded",
                    timeout=30000,
                )
                await self.wait(3)
                mf = await self._get_main_frame()
                frame = mf if mf and await self._is_smart_editor_visible(mf) else self.page
                if not await self._is_smart_editor_visible(frame):
                    self.log("      ❌ 글쓰기용 스마트에디터를 찾지 못했습니다.")
                    return False
            await _dismiss_file_transfer_error(self.page, self.log)

            # 본문에서 취소선 전부 제거 — hymini11 등 에디터 깨짐·발행 불가 방지
            body = re.sub(r"~~([^~]*?)~~", r"\1", body)
            body = re.sub(r"<s>(.*?)</s>", r"\1", body, flags=re.I | re.DOTALL)
            body = re.sub(r"<strike>(.*?)</strike>", r"\1", body, flags=re.I | re.DOTALL)
            body = re.sub(r"</?s\b[^>]*>", "", body, flags=re.I)
            body = re.sub(r"</?strike\b[^>]*>", "", body, flags=re.I)
            body = re.sub(r'\s+style="([^"]*)"', lambda m: _clean_style_line_through(m, '"') if m and "line-through" in (m.group(1) or "").lower() else (m.group(0) if m else ""), body, flags=re.I)
            body = re.sub(r"\s+style='([^']*)'", lambda m: _clean_style_line_through(m, "'") if m and "line-through" in (m.group(1) or "").lower() else (m.group(0) if m else ""), body, flags=re.I)

            # 1. 팝업 및 방해 요소 제거 (강화)
            self.log("      🧹 방해 팝업 및 안내창 정리 중...")
            stop_btns = [
                ".se-popup-close", 
                "button[aria-label='닫기']", 
                ".se-help-panel-close-button",
                ".se-popup-button-cancel", 
                ".se-button-close",
                "button:has-text('취소')",
                "button:has-text('닫기')",
                ".se-editor-popup button",
                ".se-onboarding-finish-button", # 튜토리얼 종료 버튼
                ".se-help-panel-close",
                ".se-popup-button-close"
            ]
            for _ in range(3):  # 횟수 증가
                for sel in stop_btns:
                    try:
                        loc = self._get_locator(frame, sel)
                        btns = await loc.all()
                        for btn in btns:
                            if await btn.is_visible():
                                await btn.click(force=True)
                                await self.wait(0.7)
                    except: continue
                # ESC 키로 안내창 닫기 시도
                await self.page.keyboard.press("Escape")
                await self.wait(0.5)

            # hymini11: 툴바 아이콘 클릭 제거 — 취소선이 계속 적용되고 발행 버튼을 누르지 못하는 현상 방지
            # (기존에는 툴바 클릭으로 에디터 활성화를 시도했으나, 서식 메뉴가 열리며 발행이 막히는 경우가 있음)

            # 2. 제목 입력 영역 활성화
            self.log("      ✍ 제목 입력 시도 중...")
            await self._focus_title_area(frame)
            title_selectors = [
                ".se-placeholder:has-text('제목')",
                "p.se-text-paragraph-align-left span.se-placeholder",
                ".se-documentTitle .se-ff-nanumgothic",
                ".se-ff-nanumgothic.se-documentTitle",
                ".se-documentTitle [contenteditable='true']",
                ".se-title-text",
                "textarea.se-ff-nanumgothic", # 간혹 텍스트에어리어인 경우
                ".se-documentTitle"
            ]
            
            title_el = None
            for sel in title_selectors:
                try:
                    el = self._get_locator(frame, sel).first
                    if await el.count() > 0:
                        await el.scroll_into_view_if_needed(timeout=5000)
                        await el.click(force=True, timeout=5000)
                        title_el = el
                        break
                except: continue
                
            # 제목 초기화 및 입력
            await self.page.keyboard.press("Control+a")
            await self.page.keyboard.press("Backspace")
            await self.wait(0.5)
            await self.page.keyboard.type(title, delay=50)
            await self.wait(1)
            typed_len = await self._get_title_text_length(frame)
            if title and typed_len < max(3, len(title) // 3):
                self.log("      ⚠️ 제목 입력 확인 실패 — 제목 영역 재클릭 후 재입력")
                for sel in (".se-documentTitle", ".se-placeholder:has-text('제목')"):
                    try:
                        el = self._get_locator(frame, sel).first
                        if await el.count() > 0:
                            await el.click(force=True, timeout=5000)
                            break
                    except Exception:
                        continue
                await self.page.keyboard.press("Control+a")
                await self.page.keyboard.press("Backspace")
                await self.page.keyboard.type(title, delay=50)
                await self.wait(1)
            self.log("         ✅ 제목 입력 완료")
            
            # 3. 본문 영역 진입
            await self.page.keyboard.press("Enter")
            await self.wait(1)

            self.log("      ✍ 본문 영역 활성화...")
            if not await self._focus_body_area(frame):
                self.log("      ⚠️ 본문 영역을 찾지 못해 에디터 중앙 강제 클릭")
                await self.page.mouse.click(600, 600)
                await self.wait(1)
                await self._focus_body_area(frame)

            # 본문 깨우기
            await self.page.keyboard.type(" ")
            await self.page.keyboard.press("Backspace")
            await self.wait(0.5)

            # 혹시 에디터에 남아 있는 이전 취소선 서식을 먼저 제거 (특히 hymini11 계정용)
            self.log("      🔧 기존 취소선 서식을 정리한 뒤 본문을 입력합니다.")
            await self._remove_strikethrough(frame)
            # 취소선 해제: 툴바에서 취소선이 켜져 있으면 끄고, 서식 제거로 일반 글자만 쓰이게 함
            try:
                for ctx in [frame, self.page]:
                    try:
                        # 툴바 취소선 버튼이 눌려 있으면 한 번 클릭해 해제
                        strike_btn = ctx.locator(
                            "button[aria-pressed='true'][title*='취소선'], "
                            "button[aria-pressed='true'][aria-label*='취소선'], "
                            "[role='button'][aria-pressed='true']:has([class*='strike']), "
                            ".se-toolbar-group button[aria-pressed='true']"
                        ).first
                        if await strike_btn.count() > 0 and await strike_btn.is_visible(timeout=500):
                            await strike_btn.click(force=True)
                            self.log("      🔧 툴바 취소선 버튼 해제")
                            await self.wait(0.5)
                            break
                    except Exception:
                        pass
                # 현재 커서 위치/선택 영역 서식 제거 → Naver1/Naver2 동일: frame 기준으로 실행
                try:
                    await frame.evaluate("""() => {
                        try {
                            const d = document;
                            if (d.body) d.execCommand('removeFormat', false, null);
                            const sel = d.defaultView && d.defaultView.getSelection && d.defaultView.getSelection();
                            if (sel && sel.anchorNode) {
                                const el = sel.anchorNode.nodeType === 3 ? sel.anchorNode.parentElement : sel.anchorNode;
                                if (el && el.closest && el.closest('[contenteditable="true"]')) {
                                    el.closest('[contenteditable="true"]').focus();
                                    d.execCommand('removeFormat', false, null);
                                }
                            }
                        } catch (e) {}
                    }""")
                except Exception:
                    pass
                await self.wait(0.3)
            except Exception:
                pass

            # 4. 본문 및 이미지 교차 입력
            #    - [IMAGE], [IMAGE1], [이미지1] 등 마커 기준으로 본문을 분할
            #    - 마커 개수만큼만 이미지를 끼워 넣고, 마커가 전혀 없으면 글 하단에만 이미지 정리해서 삽입
            parts = re.split(r'\[IMAGE\d*\]|\[이미지\d*\]', body, flags=re.I)
            marker_count = max(len(parts) - 1, 0)  # [IMAGE] 마커 개수

            for i, part in enumerate(parts):
                text_content = part.strip()
                if text_content:
                    # 마크다운 표 블록(|로 시작, --- 구분선 포함)이면 HTML <table>로 변환해 붙여넣기
                    if (
                        sys.platform == "win32"
                        and text_content.startswith("|")
                        and "|---" in text_content
                    ):
                        html = _markdown_table_to_html(text_content)
                        if html:
                            self.log(f"         📊 마크다운 표를 HTML 표로 변환해서 삽입합니다. (파트 {i+1})")
                            await self.page.keyboard.press("End")
                            # HTML을 클립보드에 넣고 Ctrl+V로 서식 유지 붙여넣기
                            if _set_html_clipboard_win(html):
                                await self.wait(0.2)
                                await self.page.keyboard.press("Control+v")
                                await self.wait(1.5)
                                await self.page.keyboard.press("Enter")
                                await self.wait(0.5)
                                # 표는 이미 처리했으므로 일반 텍스트 붙여넣기 로직은 생략
                                text_content = ""

                    if text_content:
                        self.log(f"         ✍ 본문 파트 {i+1} 입력 중...")
                        text_content = strip_strikethrough_markers(text_content)
                        if not await self._paste_plain_text(frame, text_content):
                            self.log(f"         ⚠️ 본문 파트 {i+1} 입력 실패 — 재시도")
                            await self._focus_body_area(frame)
                            if not await self._paste_plain_text(frame, text_content):
                                self.log(f"         ❌ 본문 파트 {i+1} 입력 최종 실패")
                                return False
                        await self.wait(0.5)
                        await self._remove_strikethrough(frame)
                        await self.wait(0.5)
                        await self.page.keyboard.press("Enter")
                        await self.page.keyboard.press("Enter")
                        await self.wait(0.5)

                # i 번째 본문 뒤에 오는 [IMAGE] 마커에 대해서만 이미지 매핑
                if i < marker_count and i < len(img_paths):
                    await self.upload_image(frame, img_paths[i], i)

            # 마커가 전혀 없고, 이미지가 있는 경우에는 글 맨 아래에만 이미지들을 순서대로 삽입
            if marker_count == 0 and img_paths:
                self.log("      📸 본문 내 [IMAGE] 마커가 없어, 글 하단에 이미지를 정리해서 삽입합니다.")
                for idx, path in enumerate(img_paths):
                    await self.upload_image(frame, path, idx)

            # 취소선 완전 제거 (Naver2 반복 적용 대응: 3회 + 클래스/스타일/removeFormat)
            for _ in range(3):
                await self._remove_strikethrough(frame)
                await self.wait(0.25)

            expected_plain = re.sub(r"\s+", "", body or "")
            actual_body = await self._get_body_text_length(frame)
            if expected_plain and len(expected_plain) > 30:
                if actual_body < max(30, len(expected_plain) // 5):
                    self.log(
                        f"      ❌ 본문 입력 확인 실패 (약 {actual_body}자 / 기대 {len(expected_plain)}자)"
                    )
                    return False

            await _dismiss_file_transfer_error(self.page, self.log)
            self.log("      ✅ 네이버 본문/이미지 작성 완료")
            return True

        except Exception as e:
            self.log(f"      ❌ 네이버 본문 작성 중 오류: {e}", "error")
            return False

    async def upload_image(self, frame, img_path, idx):
        try:
            self.log(f"      📸 이미지 #{idx+1} 클립보드 복사 및 붙여넣기 시도...")
            abs_path = os.path.abspath(img_path)
            
            # 1. 이미지를 클립보드에 비트맵 데이터로 복사
            image = Image.open(abs_path)
            output = io.BytesIO()
            image.convert("RGB").save(output, "BMP")
            data = output.getvalue()[14:] # BMP 헤더 제거
            output.close()

            win32clipboard.OpenClipboard()
            win32clipboard.EmptyClipboard()
            win32clipboard.SetClipboardData(win32clipboard.CF_DIB, data)
            win32clipboard.CloseClipboard()

            # 2. 본문 영역에 포커스 후 붙여넣기 (제목란 오삽입 방지)
            if not await self._focus_body_area(frame):
                await self.page.keyboard.press("Tab")
                await self.wait(0.3)
                await self._focus_body_area(frame)
            await self.page.keyboard.press("End")
            await self.wait(0.3)
            await self.page.keyboard.press("Control+v")
            self.log(f"         ✅ 이미지 #{idx+1} 삽입 성공 (Clipboard)")
            await self.wait(3)  # 업로드 대기 (연속 발행 속도 개선)
            await _dismiss_file_transfer_error(self.page, self.log)  # '파일 전송 오류' 팝업 시 확인 클릭
            return True

        except Exception as e:
            self.log(f"         ⚠️ 이미지 삽입 실패: {e}", "warn")
            return False

class NaverBlogPublisher:
    def __init__(self, page, log_func):
        self.page = page
        self.log = log_func
        self.wait_func = None

    async def wait(self, seconds):
        if self.wait_func:
            await self.wait_func(seconds)
        else:
            await asyncio.sleep(seconds)

    async def clear_popups(self, frame):
        try:
            # 다양한 팝업 및 도움말 패널 닫기 버튼들
            selectors = [
                ".se-popup-close", 
                "button[aria-label='닫기']", 
                ".se-help-panel-close-button",
                "button:has-text('닫기')",
                ".se-popup-button-close"
            ]
            for sel in selectors:
                btns = await frame.locator(sel).all()
                for btn in btns:
                    if await btn.is_visible():
                        await btn.click(force=True)
                        await self.wait(0.5)
        except: pass

    async def open_publish_layer(self, frame):
        self.log("   📢 발행 레이어 오픈 시도...")
        await _dismiss_file_transfer_error(self.page, self.log)
        await self.clear_popups(frame)
        try:
            # 1차 발행 버튼 (상위 프레임/페이지 통합 검색)
            selectors = [
                "button[data-testid='se-publish-button']", # 가장 우선적인 최신 test-id
                "button:has-text('발행'):not([disabled])", # 비활성화되지 않은 '발행' 버튼
                ".text__d09H7", 
                "button.publish_btn__m9KHH", 
                ".btn_publish", 
                "button:has-text('발행하기')"
            ]
            publish_btn = None
            for sel in selectors:
                for ctx in [frame, self.page]:
                    btn = ctx.locator(sel).filter(visible=True).first
                    if await btn.count() > 0:
                        publish_btn = btn
                        break
                if publish_btn: break
            
            if publish_btn:
                await publish_btn.click(force=True)
                await self.wait(2.5)
                self.log("      ✅ 발행 레이어 오픈 성공")
                return True
            else:
                # 폴백: 페이지 내 버튼 텍스트로 직접 클릭 시도
                try:
                    for ctx in [frame, self.page]:
                        await ctx.evaluate("() => { const btns = Array.from(document.querySelectorAll('button')); for(const b of btns){ if(b.innerText && b.innerText.trim().includes('발행')){ b.click(); break; } } }")
                    self.log("      ⚠️ 1차 발행 버튼을 텍스트 폴백으로 클릭 시도함")
                    await self.wait(4)
                    return True
                except Exception as e:
                    self.log(f"      ⚠️ 1차 발행 버튼 폴백 실패: {e}", "error")
                    return False
        except Exception as e:
            self.log(f"   ⚠️ 발행 레이어 오픈 중 오류: {e}", "error")
            return False

    async def set_tags(self, frame, tags):
        try:
            self.log("      🏷 네이버 해시태그 입력 시도 중...")
            if not (tags or "").strip():
                self.log("         (입력할 태그 없음)")
                return True

            # 1. 태그 목록 정제 (최대 30개)
            tag_list = re.split(r'[,\s\n]+', tags)
            unique_tags = []
            seen = set()
            for t in tag_list:
                clean_t = t.strip().replace("#", "")
                if clean_t and clean_t not in seen:
                    unique_tags.append(clean_t)
                    seen.add(clean_t)
            unique_tags = unique_tags[:30]
            if not unique_tags:
                return True

            # 2. 발행 레이어가 완전히 뜬 뒤 태그 영역 로드 대기 (폴백 클릭 시 레이어 지연 대응)
            await self.wait(3.5)

            # 3. 태그 입력창 찾기 (페이지·프레임 모두, 최신 스마트에디터 선택자 포함)
            tag_input = None
            selectors = [
                "input[data-testid*='tag']",
                "input[data-testid*='Tag']",
                "[data-testid='se-tag-input']",
                "#tag-input",
                ".tag_input__rvUB5",
                "input[placeholder*='태그']",
                "input[placeholder*='해시태그']",
                "input[placeholder*='태그를 입력']",
                ".se-tag-input",
                ".tag_input",
                ".tag-input",
                "input[name*='tag']",
                "input[id*='tag']",
                "input[class*='tag']",
                "input[aria-label*='태그']",
                ".publish_layer input[type='text']",
                ".se-layer input[type='text']",
                "[class*='publish'] input[placeholder*='태그']",
                "[class*='PublishLayer'] input",
                "input[type='text'][placeholder]",
            ]
            for ctx in [self.page, frame]:
                for sel in selectors:
                    try:
                        el = ctx.locator(sel).first
                        if await el.count() > 0 and await el.is_visible(timeout=2000):
                            tag_input = el
                            self.log(f"         📍 태그 입력창 발견: {sel}")
                            break
                    except Exception:
                        continue
                    if tag_input:
                        break
                if tag_input:
                    break

            if not tag_input:
                # '태그' 라벨 클릭으로 입력창 활성화 시도
                for ctx in [self.page, frame]:
                    try:
                        label = ctx.locator("label:has-text('태그'), span:has-text('태그'), [class*='tag'] label, .se-tag").first
                        if await label.count() > 0 and await label.is_visible(timeout=1000):
                            await label.click(force=True)
                            await self.wait(0.8)
                            break
                    except Exception:
                        pass

            for ctx in [self.page, frame]:
                for sel in selectors:
                    try:
                        el = ctx.locator(sel).first
                        if await el.count() > 0 and await el.is_visible(timeout=1500):
                            tag_input = el
                            self.log(f"         📍 태그 입력창 발견(재시도): {sel}")
                            break
                    except Exception:
                        continue
                    if tag_input:
                        break
                if tag_input:
                    break

            if tag_input:
                await tag_input.scroll_into_view_if_needed()
                await self.wait(0.3)
                await tag_input.click(force=True)
                await self.wait(0.5)
                for i, tag in enumerate(unique_tags):
                    try:
                        await tag_input.focus()
                        await self.page.keyboard.type(tag, delay=60)
                        await self.wait(0.25)
                        await self.page.keyboard.press("Enter")
                        await self.wait(0.4)
                    except Exception as e:
                        self.log(f"         ⚠️ 태그 '{tag}' 입력 중 오류: {e}")
                self.log(f"         ✅ 태그 {len(unique_tags)}개 입력 완료")
                return True

            # 4. JS로 입력창 찾아 포커스 후 키보드 입력
            self.log("      ⚠️ 태그 입력창을 찾지 못해 JS로 시도합니다...")
            found = await self.page.evaluate("""() => {
                const sel = (doc) => {
                    const q = doc.querySelector.bind(doc);
                    return q('[data-testid*="tag"]') || q('#tag-input') || q('.tag_input__rvUB5') || q('.se-tag-input') || q('input[placeholder*="태그"]') || q('input[placeholder*="해시태그"]') || q('input[name*="tag"]') || q('input[id*="tag"]') || q('input[class*="tag"]');
                };
                const el = sel(document);
                if (el) { el.focus(); el.click(); return true; }
                const fr = document.getElementById('mainFrame');
                if (fr && fr.contentDocument) {
                    const inFr = sel(fr.contentDocument);
                    if (inFr) { inFr.focus(); inFr.click(); return true; }
                }
                return false;
            }""")
            if found:
                await self.wait(0.5)
                for tag in unique_tags[:15]:
                    await self.page.keyboard.type(tag, delay=50)
                    await self.page.keyboard.press("Enter")
                    await self.wait(0.4)
                self.log(f"         ✅ 태그 {len(unique_tags[:15])}개 JS로 입력 완료")
                return True
            self.log("      ⚠️ 태그 입력창을 찾지 못해 해시태그를 건너뜁니다.")
            return False
        except Exception as e:
            self.log(f"      ⚠️ 태그 입력 과정 중 오류: {e}", "warn")
            return False

    async def set_reservation(self, frame, config, post_index, base_time):
        if config["mode"] != "reserve": return True
        self.log(f"   ⏰ #{post_index+1} 포스팅 예약 설정 시도...")
        try:
            # 1. '예약' 라벨 클릭
            reserve_selectors = [
                "input#radio_time2",
                "label[for='radio_time2']",
                ".radio_label__mB6ia:has-text('예약')",
                "input[data-testid='preTimeRadioBtn']",
                "label:has-text('예약')"
            ]
            
            reserve_label = None
            for sel in reserve_selectors:
                for ctx in [frame, self.page]:
                    cand = ctx.locator(sel).first
                    if await cand.count() > 0:
                        reserve_label = cand
                        break
                if reserve_label: break

            if reserve_label:
                await reserve_label.click(force=True)
                self.log("      ✅ '예약' 선택 완료")
                await self.wait(2)
            else:
                self.log("      ⚠️ '예약' 버튼 탐색 실패. JS 강제 선택 시도...")
                for ctx in [frame, self.page]:
                    await ctx.evaluate("""() => {
                        const rb = document.getElementById('radio_time2');
                        if(rb) { 
                            rb.click(); 
                            rb.checked = true; 
                            rb.dispatchEvent(new Event('change', {bubbles:true})); 
                        }
                        const lb = document.querySelector('label[for="radio_time2"]');
                        if(lb) lb.click();
                    }""")
                await self.wait(2)

            # 2. 목표 예약 시간 계산
            # 현재 시간 기준으로 gap만큼 뒤로 설정
            now = datetime.now()
            total_offset_minutes = config["gap"] * (post_index + 1)
            target_time = now + timedelta(minutes=total_offset_minutes)
            
            # 네이버 분 단위 옵션(00, 10, 20, 30, 40, 50)에 맞게 올림 처리
            minutes = target_time.minute
            remainder = minutes % 10
            if remainder > 0:
                target_time += timedelta(minutes=(10 - remainder))
            target_time = target_time.replace(second=0, microsecond=0)
            
            # 만약 계산된 시간이 현재보다 과거라면 강제로 미룸 (최소 20분 뒤)
            if target_time <= datetime.now():
                target_time = datetime.now() + timedelta(minutes=20)
                target_time = target_time.replace(minute=(target_time.minute // 10 * 10), second=0, microsecond=0)

            date_str = target_time.strftime("%Y. %m. %d")
            h_str = target_time.strftime("%H")
            m_str = target_time.strftime("%M")

            self.log(f"      🕒 예약 설정 시간: {date_str} {h_str}:{m_str}")

            # 3. 날짜, 시간, 분 입력
            success = False
            for ctx in [frame, self.page]:
                try:
                    # 날짜 입력 (.input_date__QmA0s)
                    d_input = ctx.locator(".input_date__QmA0s").first
                    if await d_input.count() > 0:
                        await ctx.evaluate(f'''(val) => {{
                            const el = document.querySelector(".input_date__QmA0s");
                            if(el) {{
                                el.readOnly = false;
                                el.value = val;
                                el.dispatchEvent(new Event('input', {{ bubbles: true }}));
                                el.dispatchEvent(new Event('change', {{ bubbles: true }}));
                            }}
                        }}''', date_str)
                        await self.wait(1)

                    # 시간 셀렉트 박스 (.hour_option__J_heO)
                    h_sel = ctx.locator(".hour_option__J_heO").first
                    # 분 셀렉트 박스 (.minute_option__Vb3xB)
                    m_sel = ctx.locator(".minute_option__Vb3xB").first
                    
                    if await h_sel.count() > 0:
                        await h_sel.select_option(value=h_str)
                        await self.wait(0.5)
                    if await m_sel.count() > 0:
                        await m_sel.select_option(value=m_str)
                        await self.wait(0.5)
                        
                    success = True
                    break
                except Exception as e:
                    self.log(f"         ⚠️ 필드 입력 중 오류: {e}")
                    continue
                
            return success
        except Exception as e:
            self.log(f"      ⚠️ 예약 설정 로직 오류: {e}", "warn")
            return False

    async def finalize_publish(self, frame):
        self.log("   🚀 최종 발행 버튼 클릭 시도 중...")
        await _dismiss_file_transfer_error(self.page, self.log)
        try:
            selectors = [
                "button.confirm_btn__WEaBq[data-testid='seOnePublishBtn']",
                ".confirm_btn__WEaBq[data-testid='seOnePublishBtn']",
                "button[data-testid='seOnePublishBtn']",
                "button[data-click-area='tpb*i.publish']",
                "button:has-text('발행')"
            ]
            
            await self.wait(1)

            for sel in selectors:
                for ctx in [self.page, frame]:
                    try:
                        btns = ctx.locator(sel)
                        if await btns.count() > 0:
                            btn = btns.last
                            await btn.scroll_into_view_if_needed()
                            await self.wait(0.5)
                            try:
                                await btn.click(force=True, timeout=5000)
                            except Exception:
                                # 요소가 viewport 밖으로 판정될 때 JS 강제 클릭 폴백
                                await btn.evaluate("(el) => { el.scrollIntoView({block:'center'}); el.click(); }")
                            self.log("         ✅ 최종 발행 클릭 성공!")
                            return True
                    except: continue

            for ctx in [self.page, frame]:
                success = await ctx.evaluate("""() => {
                    const b = document.querySelector('button.confirm_btn__WEaBq[data-testid="seOnePublishBtn"]')
                           || Array.from(document.querySelectorAll('button')).find(el => el.innerText.includes('발행') && el.offsetHeight > 0);
                    if (b) { b.click(); return true; }
                    return false;
                }""")
                if success:
                    self.log("         ✅ 최종 발행 클릭 성공 (JS)")
                    return True

            await self.page.keyboard.press("Enter")
            return True
        except Exception as e:
            self.log(f"      ⚠️ 최종 발행 오류: {e}", "error")
            return False
