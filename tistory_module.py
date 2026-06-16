import asyncio
import os
import re
import io
import pyperclip
from datetime import datetime, timedelta
from PIL import Image
import sys

if sys.platform == "win32":
    import win32clipboard
    from blogger_browser import _body_to_html, _set_html_clipboard_win


def _markdown_table_to_html(table_text: str) -> str:
    """
    마크다운 표(|로 시작하는 줄들)를 티스토리 에디터가 인식 가능한 <table> HTML로 변환.
    **텍스트**는 <b>텍스트</b>로 바꿔서 굵게 표시한다.
    """
    lines = [ln.strip() for ln in table_text.splitlines() if ln.strip()]
    if len(lines) < 2:
        return ""

    def parse_row(line: str):
        cells = [c.strip() for c in line.strip("|").split("|")]
        bolded = []
        for c in cells:
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

class TistoryWriter:
    def __init__(self, page, log_func):
        self.page = page
        self.log = log_func
        # 임시 저장글 팝업 등 차단: '취소'를 눌러 무시하도록 설정
        self.page.on("dialog", lambda dialog: asyncio.create_task(dialog.dismiss()))
        self.wait_func = None

    async def wait(self, seconds):
        if self.wait_func:
            await self.wait_func(seconds)
        else:
            await asyncio.sleep(seconds)

    async def is_logged_in(self):
        """현재 브라우저 세션의 티스토리 로그인 여부만 빠르게 확인."""
        try:
            await self.page.goto("https://www.tistory.com/", wait_until="domcontentloaded", timeout=30000)
            await self.wait(2)
            return await self.page.locator("a:has-text('로그아웃'), .link_logout, a[href*='/manage']").count() > 0
        except Exception:
            return False

    async def ensure_logged_in(self, t_id, t_pw):
        """로그인되어 있지 않으면 login()을 호출한다."""
        if await self.is_logged_in():
            self.log("      ✅ 티스토리 로그인 세션 확인됨")
            return True
        return await self.login(t_id, t_pw)

    async def login(self, t_id, t_pw):
        self.log("   🏰 티스토리 상태 확인 중...")
        try:
            # 0. 이미 로그인되어 있는지 확인
            if await self.is_logged_in():
                self.log("      ✅ 이미 티스토리에 로그인되어 있습니다.")
                return True

            # 1. 로그인 페이지로 이동
            self.log("   🏰 티스토리 로그인 시도 중...")
            await self.page.goto("https://www.tistory.com/auth/login")
            await self.wait(2)

            # 2. (가능하면) '카카오계정으로 시작하기' 버튼 자동 클릭
            try:
                kakao_start = self.page.locator(".txt_login:has-text('카카오계정으로 시작하기'), .btn_login.link_kakao")
                if await kakao_start.count() > 0 and await kakao_start.first.is_visible():
                    await kakao_start.first.click()
                    await self.wait(3)
                    # 카카오 로그인 페이지에서 이메일/비밀번호 자동 입력 시도 (비밀번호는 한 글자씩 입력해 봇 감지 회피)
                    try:
                        email_selectors = ["#loginKey--1", "input[name='email']", "input[type='email']", "input[id*='loginKey']"]
                        pw_selectors = ["#password--1", "input[name='password']", "input[type='password']", "input[id*='password']"]
                        email_filled = await self._robust_fill(email_selectors, t_id)
                        pw_filled = await self._fill_password_by_typing(pw_selectors, t_pw)
                        if email_filled or pw_filled:
                            self.log("      📝 카카오 로그인란 자동 입력 완료 (비밀번호는 한 글자씩 입력). 로그인 버튼 클릭 및 2단계 인증을 완료해 주세요.")
                        else:
                            self.log("   👀 카카오 로그인창에서 이메일·비밀번호를 입력해 주세요. 비밀번호는 붙여넣기 대신 한 글자씩 입력하면 봇 감지를 피할 수 있습니다.")
                    except Exception as _e:
                        self.log("   👀 티스토리/카카오 로그인 창에서 직접 이메일과 비밀번호, 2단계 인증을 완료해 주세요.")
                else:
                    self.log("   👀 티스토리/카카오 로그인 창에서 직접 이메일과 비밀번호, 2단계 인증을 완료해 주세요.")
            except Exception:
                self.log("   👀 티스토리/카카오 로그인 창에서 직접 이메일과 비밀번호, 2단계 인증을 완료해 주세요.")

            # 3. 사용자가 직접 로그인 버튼 클릭/2단계 인증을 완료하도록 대기
            self.log("      (최대 5분 동안 로그인 완료를 감지하며, 완료되면 자동으로 다음 단계로 진행됩니다.)")

            try:
                # auth/confirm/security 등이 아닌 일반 티스토리 페이지로 돌아올 때까지 대기
                await self.page.wait_for_url(
                    lambda url: "tistory.com" in url and all(x not in url for x in ["auth", "confirm", "security"]),
                    timeout=300000
                )
            except:
                self.log("      ⚠️ 5분 안에 로그인 완료를 감지하지 못했습니다.", "error")
                return False

            # 최종 로그인 여부 재확인
            await self.wait(2)
            if await self.page.locator("a:has-text('로그아웃'), .link_logout, a[href*='/manage']").count() > 0:
                self.log("      ✅ 티스토리 로그인 완료 확인")
                return True

            self.log("      ⚠️ 로그인 완료 페이지로 보이지만 로그아웃 버튼을 찾지 못했습니다.", "warn")
            return False
        except Exception as e:
            self.log(f"      ⚠️ 티스토리 로그인 과정 중 오류: {e}", "error")
            return False

    async def _robust_fill(self, selectors, value):
        for sel in selectors:
            try:
                field = self.page.locator(sel).first
                if await field.count() > 0 and await field.is_visible(timeout=3000):
                    await field.click()
                    await self.wait(0.5)
                    pyperclip.copy(value)
                    if sys.platform == "win32":
                         await self.page.keyboard.press("Control+v")
                    else:
                         await self.page.keyboard.press("Meta+v")
                    await self.wait(0.5)
                    return True
            except: continue
        return False

    async def _fill_password_by_typing(self, selectors, password):
        """비밀번호를 한 글자씩 입력 (복사·붙여넣기 시 봇 감지 우회)."""
        for sel in selectors:
            try:
                field = self.page.locator(sel).first
                if await field.count() > 0 and await field.is_visible(timeout=3000):
                    await field.click()
                    await self.wait(0.5)
                    await field.fill("")
                    await self.wait(0.2)
                    await self.page.keyboard.type(password, delay=80)
                    await self.wait(0.3)
                    return True
            except: continue
        return False

    async def navigate_to_editor(self):
        self.log("      🏰 티스토리 에디터 진입 시도...")
        try:
            # 0. 로그인 상태 및 에디터 여부 확인
            if "manage/newpost" in self.page.url:
                if await self.page.locator("#post-title-inp, .ProseMirror").count() > 0:
                    self.log("      ✅ 이미 에디터 화면에 있습니다.")
                    await self._clear_tistory_popups()
                    return True

            # 1. 현재 페이지에서 우선 '글쓰기' 버튼 탐색 (다른 페이지로 이동하기 전)
            self.log("      🚀 현재 페이지에서 '글쓰기' 버튼 탐색...")
            write_selectors = [
                "a.link_tab:has-text('글쓰기')", 
                "a.link_tab[href*='manage/newpost']",
                "a[href*='manage/newpost']",
                "a:has-text('글쓰기')",
                ".link_write",
                ".btn_write",
                "a.link_tab"
            ]

            for ws in write_selectors:
                try:
                    write_btn = self.page.locator(ws).first
                    if await write_btn.count() > 0 and await write_btn.is_visible():
                        self.log(f"         🖱 현재 페이지({self.page.url[:30]})에서 '{ws}' 클릭...")
                        ctx = self.page.context
                        before_pages = ctx.pages.copy()
                        await write_btn.click()
                        await self.wait(3)
                        after_pages = ctx.pages
                        # 새 탭이 열린 경우 해당 탭으로 전환
                        if len(after_pages) > len(before_pages):
                            new_page_candidates = [p for p in after_pages if p not in before_pages]
                            if new_page_candidates:
                                self.page = new_page_candidates[0]
                        await self.page.bring_to_front()
                        if await self.page.locator("#post-title-inp, .ProseMirror").count() > 0:
                            self.log("      ✅ '글쓰기' 버튼 클릭 성공")
                            return True
                except Exception:
                    continue

            # 2. 버튼 세트가 없거나 공지사항 페이징 등에 있는 경우 관리 홈으로 이동
            if "notice.tistory.com" in self.page.url or "manage" not in self.page.url:
                self.log("      🏰 티스토리 관리 홈(Manage)으로 강제 이동 중...")
                await self.page.goto("https://www.tistory.com/manage", wait_until="networkidle")
                await self.wait(4)

            # 3. 관리 홈에서 다시 버튼 탐색
            self.log("      🚀 관리 홈에서 '글쓰기' 버튼 다시 탐색...")
            for ws in write_selectors:
                try:
                    write_btn = self.page.locator(ws).first
                    if await write_btn.count() > 0 and await write_btn.is_visible():
                        self.log(f"         🖱 '{ws}' 버튼 클릭...")
                        ctx = self.page.context
                        before_pages = ctx.pages.copy()
                        await write_btn.click()
                        await self.wait(3)
                        after_pages = ctx.pages
                        if len(after_pages) > len(before_pages):
                            new_page_candidates = [p for p in after_pages if p not in before_pages]
                            if new_page_candidates:
                                self.page = new_page_candidates[0]
                        await self.page.bring_to_front()
                        if await self.page.locator("#post-title-inp, .ProseMirror").count() > 0:
                            self.log("      ✅ '글쓰기' 버튼 클릭을 통해 에디터 진입 성공")
                            return True
                except Exception:
                    continue

            # 4. 폴백: 서브도메인 직접 이동
            subdomain = await self.page.evaluate("""() => {
                const links = Array.from(document.querySelectorAll('a[href*=".tistory.com"]'));
                for (const link of links) {
                    const match = link.href.match(/https?:\/\/([^.]+)\.tistory\.com/);
                    if (match && !['notice', 'www', 'support', 'main', 'tistory'].includes(match[1])) return match[1];
                }
                return null;
            }""")

            if subdomain:
                url = f"https://{subdomain}.tistory.com/manage/newpost"
                self.log(f"         🔗 직접 이동 폴백: {url}")
                await self.page.goto(url, wait_until="load")
                await self.wait(3)
                if await self.page.locator("#post-title-inp, .ProseMirror").count() > 0:
                    return True

            self.log("      ❌ 티스토리 에디터 진입 최종 실패", "error")
            return False
        except Exception as e:
            self.log(f"      ❌ 에디터 진입 중 오류: {e}", "error")
            return False

    async def _save_draft_and_exit(self):
        self.log("         💾 임시저장(Draft) 프로세스 시작...")
        try:
            # 임시저장 버튼 탐색 (사용자 제공: a.action '임시저장')
            draft_btn = self.page.locator("a.action:has-text('임시저장'), button:has-text('임시저장')").first
            if await draft_btn.count() > 0:
                await draft_btn.click()
                await self.wait(3)
                self.log("         ✅ 임시저장 완료. 작업을 종료합니다.")
                # 임시저장 후에는 에디터를 벗어나거나 탭을 닫아도 안전함
                return False # 포스팅 성공은 아니므로 False 반환
            else:
                self.log("         ❌ 임시저장 버튼을 찾지 못했습니다.")
        except Exception as e:
            self.log(f"         ❌ 임시저장 중 오류: {e}")
        return False

    async def _clear_tistory_popups(self):
        # '불러오기' 팝업, 안내문 등 강제 제거
        pop_selectors = [
            "button:has-text('취소')", 
            "button:has-text('닫기')", 
            ".btn_close", 
            ".layer_post_confirm button:last-child",
            ".bundle_btn button",
            "button:has-text('아니오')"
        ]
        for sel in pop_selectors:
            try:
                loc = self.page.locator(sel).filter(visible=True)
                # Playwright 버전에 따라 .all() 또는 count()/nth() 사용
                btns = await loc.all()
                for btn in btns:
                    if await btn.is_visible():
                        await btn.click()
                        await self.wait(0.5)
            except: pass
        # ESC 키로 레이어 닫기 시도
        await self.page.keyboard.press("Escape")

    async def _upload_image(self, img_path, idx):
        try:
            self.log(f"         📸 이미지 #{idx+1} 클립보드 복사 및 붙여넣기 시도...")
            abs_path = os.path.abspath(img_path)
            
            # 0. 이미지를 클립보드에 복사 (Windows 전용 비트맵 방식)
            def copy_image_to_clipboard(path):
                try:
                    image = Image.open(path)
                    output = io.BytesIO()
                    image.convert("RGB").save(output, "BMP")
                    data = output.getvalue()[14:] # BMP 헤더 14바이트 제거
                    output.close()

                    win32clipboard.OpenClipboard()
                    win32clipboard.EmptyClipboard()
                    win32clipboard.SetClipboardData(win32clipboard.CF_DIB, data)
                    win32clipboard.CloseClipboard()
                    return True
                except Exception as e:
                    self.log(f"            ❌ 클립보드 복사 실패: {e}")
                    return False

            if not copy_image_to_clipboard(abs_path):
                return False

            # 1. 에디터 영역 포커스
            await self.page.keyboard.press("End")
            await self.page.keyboard.press("Enter")
            await self.wait(1)
            
            # 현재 위치에 붙여넣기
            await self.page.keyboard.press("Control+v")
            self.log(f"            ✅ 이미지 #{idx+1} 붙여넣기 완료 (Clipboard)")
            await self.wait(4)  # 업로드 대기 (연속 발행 속도 개선)
            return True

        except Exception as e:
            self.log(f"            ⚠️ 이미지 삽입 중 오류: {e}", "warn")
        return False

    async def _paste_formatted_body(self, editor, text_content: str) -> bool:
        """마크다운 본문을 HTML로 변환해 문단·제목·표 정렬을 유지하며 붙여넣기."""
        text_content = (text_content or "").strip()
        if not text_content:
            return True
        if editor is not None:
            await editor.focus()
        await self.page.keyboard.press("End")

        if sys.platform == "win32":
            html = _body_to_html(text_content)
            if html and _set_html_clipboard_win(html):
                await self.wait(0.2)
                await self.page.keyboard.press("Control+v")
                await self.wait(1.2)
                await self.page.keyboard.press("Enter")
                await self.wait(0.5)
                return True

        # HTML 붙여넣기 실패 시: 문단 단위 plain text (네이버와 동일 패턴)
        chunks = [text_content]
        if len(text_content) > 1200:
            chunks = []
            buf = ""
            for para in text_content.split("\n\n"):
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

        for idx, chunk in enumerate(chunks):
            pyperclip.copy(chunk)
            await self.page.keyboard.press("Control+v")
            await self.wait(0.5)
            if idx < len(chunks) - 1:
                await self.page.keyboard.press("Enter")
                await self.page.keyboard.press("Enter")
                await self.wait(0.3)
        return True

    async def fill_and_publish(self, title, body, tags, img_paths=None, mode="immediate", post_index=0, gap=30):
        self.log("      ✍ 티스토리 제목 및 본문 입력을 시작합니다.")
        try:
            await self.page.bring_to_front()
            await self._clear_tistory_popups()

            # 1. 제목 입력
            title_sel = "#post-title-inp"
            try:
                await self.page.wait_for_selector(title_sel, timeout=15000)
            except:
                self.log("         ❌ 제목 입력란(#post-title-inp)을 찾지 못했습니다.")
                return False

            title_field = self.page.locator(title_sel).first
            await title_field.click()
            await self.page.keyboard.press("Control+a")
            await self.page.keyboard.press("Backspace")
            await title_field.type(title, delay=50)
            await self.wait(0.5)
            self.log("         ✅ 제목 입력 완료")
            
            # 2. 본문 영역 타겟팅 (ProseMirror / contenteditable / Tab 포커스 등 여러 방식 시도)
            editor = None
            use_active_element = False
            
            # 제목 입력 후 Tab으로 본문 에디터 포커스 시도 (가장 먼저 시도)
            await self.wait(1)
            for _ in range(8):
                await self.page.keyboard.press("Tab")
                await self.wait(0.35)
                try:
                    if await self.page.evaluate("document.activeElement && document.activeElement.isContentEditable === true"):
                        use_active_element = True
                        self.log("         ✅ 제목 다음 Tab으로 본문 에디터 포커스 성공")
                        break
                except Exception:
                    pass

            # 2-1) DOM 선택자로 직접 찾기 (Tab으로 못 찾았을 때만)
            if not use_active_element:
                editor_selectors = [
                    ".ProseMirror",
                    ".ProseMirror.ProseMirror-focused",
                    "div.contents_edit [contenteditable=\"true\"]",
                    "[contenteditable=\"true\"]",
                    "div[contenteditable=\"true\"]",
                    "p[data-ke-size=\"size16\"]",
                ]
                for sel in editor_selectors:
                    try:
                        loc = self.page.locator(sel).first
                        await self.page.wait_for_selector(sel, state="visible", timeout=5000)
                        if await loc.count() > 0 and await loc.is_visible(timeout=2000):
                            editor = loc
                            self.log(f"         ✅ 본문 에디터 영역 발견: {sel}")
                            break
                    except Exception:
                        continue

                # 2-2) ProseMirror 재시도
                if editor is None:
                    await self.wait(2)
                    try:
                        loc = self.page.locator(".ProseMirror").first
                        if await loc.count() > 0 and await loc.is_visible(timeout=5000):
                            editor = loc
                            self.log("         ✅ 본문 에디터 영역 발견: .ProseMirror (재시도)")
                    except Exception:
                        pass

                # 2-3) iframe 내 에디터 찾기
                if editor is None:
                    try:
                        for frame in self.page.frames:
                            for sel in editor_selectors:
                                try:
                                    loc = frame.locator(sel).first
                                    if await loc.count() > 0 and await loc.is_visible(timeout=2000):
                                        editor = loc
                                        self.log(f"         ✅ iframe 내 본문 에디터 영역 발견: {sel}")
                                        break
                                except Exception:
                                    continue
                            if editor is not None:
                                break
                    except Exception:
                        pass

                # 2-4) Tab 키로 contenteditable 포커스
                if editor is None:
                    self.log("         🔍 DOM 선택자로 에디터를 찾지 못해 Tab 키로 포커스를 시도합니다.")
                    for _ in range(12):
                        await self.page.keyboard.press("Tab")
                        await self.wait(0.4)
                        try:
                            is_editable = await self.page.evaluate(
                                "document.activeElement && document.activeElement.isContentEditable === true"
                            )
                        except Exception:
                            is_editable = False
                        if is_editable:
                            use_active_element = True
                            self.log("         ✅ 본문 에디터 영역 포커스 성공 (Tab 탐색)")
                            break

            # 2-5) JS로 에디터 포커스 시도 (메인 + iframe)
            if editor is None and not use_active_element:
                try:
                    focused = await self.page.evaluate("""() => {
                        const el = document.querySelector('.ProseMirror') || document.querySelector('[contenteditable="true"]');
                        if (el) { el.focus(); return true; }
                        return false;
                    }""")
                    if focused:
                        use_active_element = True
                        self.log("         ✅ 본문 에디터 포커스 성공 (JS)")
                    if not focused:
                        for frame in self.page.frames:
                            try:
                                focused = await frame.evaluate("""() => {
                                    const el = document.querySelector('.ProseMirror') || document.querySelector('[contenteditable="true"]');
                                    if (el) { el.focus(); return true; }
                                    return false;
                                }""")
                                if focused:
                                    use_active_element = True
                                    self.log("         ✅ iframe 내 본문 에디터 포커스 성공 (JS)")
                                    break
                            except Exception:
                                continue
                except Exception:
                    pass

            if editor is None and not use_active_element:
                self.log("         ⚠️ 본문 에디터 영역(.ProseMirror 등) 진입 실패")
                return False

            # 2-4) 에디터 클릭 및 초기 포커스
            if editor is not None:
                await editor.scroll_into_view_if_needed()
                await self.wait(0.5)
                await editor.click(force=True)
                await self.wait(1)
            
            # 에디터 초기화 (현재 포커스된 contenteditable이 에디터라고 가정)
            await self.page.keyboard.press("Control+a")
            await self.page.keyboard.press("Backspace")
            await self.wait(1)

            # 3. 본문 및 이미지 교차 입력
            #    - [IMAGE], [IMAGE1], [이미지1] 등 마커 개수만큼만 이미지를 끼워넣고
            #    - 마커가 아예 없으면 글 하단에만 이미지들을 순서대로 삽입
            parts = re.split(r'\[IMAGE\d*\]|\[이미지\d*\]', body, flags=re.I)
            marker_count = max(len(parts) - 1, 0)

            for i, part in enumerate(parts):
                text_content = part.strip()
                if text_content:
                    self.log(f"         ✍ 본문 파트 {i+1} 입력 중...")
                    if not await self._paste_formatted_body(editor, text_content):
                        self.log(f"         ⚠️ 본문 파트 {i+1} 입력 실패")
                        return False
                
                # i 번째 본문 뒤에 오는 [IMAGE] 마커에만 이미지 매핑
                if img_paths and i < marker_count and i < len(img_paths):
                    await self._upload_image(img_paths[i], i)

            # 마커가 없는데 이미지가 있는 경우: 글 하단에만 이미지 삽입
            if img_paths and marker_count == 0:
                self.log("         📸 본문 내 [IMAGE] 마커가 없어, 글 하단에 이미지를 정리해서 삽입합니다.")
                for idx, path in enumerate(img_paths):
                    await self._upload_image(path, idx)

            # 4. 해시태그 (사용자 제공: #tagText, 20개 제한)
            self.log("         🏷 해시태그 입력 중...")
            tag_input = self.page.locator("#tagText").first
            if await tag_input.count() > 0:
                await tag_input.scroll_into_view_if_needed()
                await tag_input.click()
                
                tag_list = re.split(r'[,\s\n]+', tags)[:20] # 최대 20개
                for t in tag_list:
                    clean_tag = t.strip().replace("#", "")
                    if clean_tag:
                        await self.page.keyboard.type(clean_tag)
                        await self.page.keyboard.press("Enter")
                        await self.wait(0.2)
            
            # 5. 발행 준비 (사용자 제공: #publish-layer-btn)
            self.log("         📢 포스팅 발행 레이어 오픈...")
            layer_btn = self.page.locator("#publish-layer-btn").first
            if await layer_btn.count() == 0:
                 layer_btn = self.page.locator("button:has-text('완료'), .btn_ready").first

            if await layer_btn.count() > 0:
                await layer_btn.click()
                await self.wait(2)
                
                # 6. 예약 설정 (mode가 reserve인 경우)
                if mode == "reserve":
                    self.log("         ⏰ 예약 발행 설정 중...")
                    # '예약' 버튼 클릭 (사용자 제공: button.btn_date)
                    reserve_tab = self.page.locator("button.btn_date").first
                    if await reserve_tab.count() > 0:
                        await reserve_tab.click()
                        await self.wait(1)
                        
                        # 예약 시간 계산
                        target_time = datetime.now() + timedelta(minutes=gap * (post_index + 1) + 10)
                        h_str = target_time.strftime("%H")
                        m_str = target_time.strftime("%M")
                        
                        # 시간/분 입력 (#dateHour, #dateMinute)
                        await self._robust_fill(["#dateHour"], h_str)
                        await self._robust_fill(["#dateMinute"], m_str)
                        self.log(f"            🕒 예약 시간 설정: {target_time.strftime('%Y-%m-%d %H:%M')}")

                # 7. 최종 발행 (사용자 제공: #publish-btn '공개 발행')
                final_btn = self.page.locator("#publish-btn").first
                if await final_btn.count() > 0:
                    try:
                        await final_btn.click(timeout=10000)
                        self.log("         ✅ 티스토리 발행 요청 완료")
                        await self.wait(3)
                        
                        # 15개 제한 확인: 여전히 에디터라면 발행 실패 → 임시저장으로 저장
                        if "manage/newpost" in self.page.url:
                            self.log("         ⚠️ 하루 발행 한도(15편)에 걸린 것으로 보입니다. 임시저장을 눌러 저장합니다.", "warn")
                            return await self._save_draft_and_exit()
                        return True
                    except:
                        self.log("         ⚠️ 발행 버튼 클릭 후 응답 없음. 임시저장 시도...")
                        return await self._save_draft_and_exit()

            self.log("         ❌ 발행 버튼을 찾을 수 없어 임시저장을 시도합니다.")
            return await self._save_draft_and_exit()

        except Exception as e:
            self.log(f"      ❌ 티스토리 작성 중 오류: {e}", "error")
            return False
