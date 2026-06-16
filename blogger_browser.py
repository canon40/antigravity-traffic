"""
구글 Blogger 브라우저 자동화.
- blogger.com 접속 → 로그인 클릭 → canon4040@gmail.com 선택 → draft.blogger.com 대시보드 → 새글 → 제목/본문 입력 → 우측 상단 게시(발행)
"""
import asyncio
import os
import sys
from dotenv import load_dotenv

load_dotenv()
BLOG_ID = os.getenv("BLOG_ID") or "80488746860695244"
# 구글 Blogger 진입 시 반드시 이 주소로 바로 이동 (한국어 소개 페이지)
BLOGGER_ABOUT_URL = "https://www.blogger.com/about/?hl=ko"
DRAFT_URL = f"https://draft.blogger.com/blog/posts/{BLOG_ID}"
BLOGGER_ACCOUNT_EMAIL = os.getenv("BLOGGER_ACCOUNT_EMAIL", "canon4040@gmail.com")
BLOGGER_PASSWORD = os.getenv("BLOGGER_PASSWORD", "")

try:
    import pyperclip
except ImportError:
    pyperclip = None

import re
import base64


def _set_html_clipboard_win(html: str) -> bool:
    """Windows에서 클립보드에 HTML 설정. 붙여넣기 시 서식 유지 가능. 실패 시 False."""
    if sys.platform != "win32":
        return False
    try:
        import ctypes
        CF_HTML = ctypes.windll.kernel32.RegisterClipboardFormatW("HTML Format")
        if not CF_HTML:
            return False
        header = "Version:0.9\r\nStartHTML:00000000\r\nEndHTML:00000000\r\nStartFragment:00000000\r\nEndFragment:00000000\r\n\r\n"
        fragment = f"<!--StartFragment-->{html}<!--EndFragment-->"
        full = header + fragment
        start_html = len(header)
        end_html = len(full)
        start_fragment = full.find("<!--StartFragment-->") + 20
        end_fragment = full.find("<!--EndFragment-->")
        full = full.replace("StartHTML:00000000", f"StartHTML:{start_html:08d}").replace("EndHTML:00000000", f"EndHTML:{end_html:08d}").replace("StartFragment:00000000", f"StartFragment:{start_fragment:08d}").replace("EndFragment:00000000", f"EndFragment:{end_fragment:08d}")
        data = full.encode("utf-16-le")
        if not data:
            return False
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
        user32.OpenClipboard(0)
        try:
            user32.EmptyClipboard()
            mem = kernel32.GlobalAlloc(0x0042, len(data) + 2)
            ptr = kernel32.GlobalLock(mem)
            if ptr:
                ctypes.memmove(ptr, data, len(data))
                kernel32.GlobalUnlock(mem)
                user32.SetClipboardData(CF_HTML, mem)
                return True
        finally:
            user32.CloseClipboard()
    except Exception:
        pass
    return False


def _copy_image_to_clipboard(file_path: str) -> bool:
    """이미지 파일을 Windows 클립보드에 넣음. Ctrl+V 시 이미지로 붙여넣기 가능. Gemini/Vertex 생성 이미지용."""
    if sys.platform != "win32":
        return False
    if not file_path or not os.path.isfile(file_path):
        return False
    try:
        from PIL import Image
        from io import BytesIO
        import ctypes
        img = Image.open(file_path).convert("RGB")
        output = BytesIO()
        img.save(output, "BMP")
        data = output.getvalue()[14:]
        output.close()
        if not data:
            return False
        CF_DIB = 8
        GMEM_MOVEABLE = 0x0002
        kernel32 = ctypes.windll.kernel32
        user32 = ctypes.windll.user32
        msvcrt = ctypes.cdll.msvcrt
        global_mem = kernel32.GlobalAlloc(GMEM_MOVEABLE, len(data))
        if not global_mem:
            return False
        global_data = kernel32.GlobalLock(global_mem)
        if global_data:
            msvcrt.memcpy(ctypes.c_char_p(global_data), data, len(data))
            kernel32.GlobalUnlock(global_mem)
        user32.OpenClipboard(0)
        try:
            user32.EmptyClipboard()
            user32.SetClipboardData(CF_DIB, global_mem)
            return True
        finally:
            user32.CloseClipboard()
    except Exception:
        pass
    return False


def _normalize_table_block(text: str) -> str:
    """표가 줄바꿈으로 깨진 경우 한 행으로 합침."""
    lines = text.split("\n")
    out = []
    i = 0
    while i < len(lines):
        line = lines[i]
        while line.strip().startswith("|") and not line.strip().endswith("|") and "---" not in line and i + 1 < len(lines):
            i += 1
            line = (line.rstrip() + " " + lines[i].strip()).strip()
        out.append(line)
        i += 1
    return "\n".join(out)


def _linkify(text: str) -> str:
    """URL을 클릭 가능한 링크로 변환."""
    return re.sub(
        r"(https?://[^\s<>]+)",
        r'<a href="\1" target="_blank" rel="noopener">\1</a>',
        text,
    )


def _body_to_html(body: str, img_paths=None):
    """본문을 타인이 보기 좋은 HTML로 변환. 문단·리스트·표·여백·링크 적용."""
    if not body or not body.strip():
        return "<p></p>"
    img_paths = list(img_paths) if img_paths else []
    # 문단별 구분·줄간격 명확 (Blogger 가독성)
    wrap = "max-width:680px; margin:0 auto; line-height:1.85; color:#333; font-size:1em;"
    p_ = "margin:0 0 1.5em 0; line-height:1.85; text-align:left;"
    h2_ = "margin:1.8em 0 0.7em 0; padding:0; font-size:1.35em; font-weight:bold; color:#222; border-bottom:1px solid #eee; padding-bottom:0.35em; line-height:1.4;"
    h3_ = "margin:1.4em 0 0.5em 0; font-size:1.15em; font-weight:bold; color:#333; line-height:1.45;"
    ul_ = "margin:0.8em 0 1em 1.5em; padding:0 0 0 1.2em; line-height:1.7;"
    li_ = "margin:0 0 0.35em 0;"
    tbl_ = "border-collapse:collapse; margin:1.2em 0; width:100%; max-width:100%; table-layout:fixed; font-size:0.95em;"
    th_ = "border:1px solid #bbb; padding:10px 12px; background:#f8f8f8; font-weight:bold; text-align:left; vertical-align:top;"
    td_ = "border:1px solid #ddd; padding:10px 12px; vertical-align:top; word-break:break-word;"

    parts = re.split(r"\[IMAGE[^\]]*\]", body, flags=re.I)
    out_parts = []
    for i, part in enumerate(parts):
        part = part.strip()
        if not part:
            continue
        part = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", part)
        part = re.sub(r"^###\s+(.+)$", r"<h3 style=\"" + h3_ + r"\">\1</h3>", part, flags=re.MULTILINE)
        part = re.sub(r"^##\s+(.+)$", r"<h2 style=\"" + h2_ + r"\">\1</h2>", part, flags=re.MULTILINE)
        part = _normalize_table_block(part)
        # 먼저 빈 줄(\n\n) 기준으로 문단 블록 나누기 → 맥락에 맞는 줄바꿈
        blocks = re.split(r"\n\s*\n", part)
        buf = []
        for block in blocks:
            block = block.strip()
            if not block:
                continue
            lines = block.split("\n")
            i_line = 0
            while i_line < len(lines):
                line = lines[i_line]
                stripped = line.strip()
                # 표
                if stripped.startswith("|") and "---" not in stripped:
                    rows = []
                    while i_line < len(lines):
                        l = lines[i_line].strip()
                        if not l.startswith("|"):
                            break
                        if "---" in l:
                            i_line += 1
                            continue
                        l_flat = l.replace("\n", " ")
                        cells = [c.strip().replace("\n", " ") for c in l_flat.strip("|").split("|")]
                        if cells:
                            tag = "th" if not rows else "td"
                            sty = th_ if tag == "th" else td_
                            rows.append("".join(f"<{tag} style=\"{sty}\">{c}</{tag}>" for c in cells))
                        i_line += 1
                    if rows:
                        buf.append(f"<table style=\"{tbl_}\"><thead><tr>{rows[0]}</tr></thead><tbody>" + "".join(f"<tr>{r}</tr>" for r in rows[1:]) + "</tbody></table>")
                    continue
                # 리스트 (* / - / • 로 시작하는 연속 줄)
                if re.match(r"^[\*\-•]\s+", stripped) or (stripped.startswith("* ") or stripped.startswith("- ")):
                    list_items = []
                    while i_line < len(lines):
                        l = lines[i_line].strip()
                        if not l:
                            i_line += 1
                            break
                        m = re.match(r"^[\*\-•]\s+(.*)", l)
                        if not m:
                            break
                        list_items.append(f"<li style=\"{li_}\">{_linkify(m.group(1))}</li>")
                        i_line += 1
                    if list_items:
                        buf.append(f"<ul style=\"{ul_}\">" + "".join(list_items) + "</ul>")
                    continue
                if stripped:
                    if stripped.startswith("<h2") or stripped.startswith("<h3") or stripped.startswith("<table"):
                        buf.append(stripped)
                    else:
                        # 긴 한 줄은 문장 단위로 끊어서 줄바꿈 (가독성)
                        s = _linkify(stripped)
                        if len(stripped) > 120:
                            for sent in re.split(r"(?<=[.!?。])\s+", stripped):
                                if sent.strip():
                                    buf.append(f"<p style=\"{p_}\">{_linkify(sent.strip())}</p>")
                        else:
                            buf.append(f"<p style=\"{p_}\">{s}</p>")
                i_line += 1
        block = "\n".join(buf) if buf else f"<p style=\"{p_}\">{_linkify(part.replace(chr(10), '<br/>'))}</p>"
        out_parts.append(block)
        if i < len(img_paths) and os.path.isfile(img_paths[i]):
            try:
                with open(img_paths[i], "rb") as f:
                    b64 = base64.b64encode(f.read()).decode("ascii")
                ext = os.path.splitext(img_paths[i])[1].lower()
                mime = "image/png" if ext == ".png" else "image/jpeg" if ext in (".jpg", ".jpeg") else "image/png"
                out_parts.append(f'<p style="{p_}"><img src="data:{mime};base64,{b64}" alt="" style="max-width:100%;height:auto;display:block;margin:0.8em 0;"/></p>')
            except Exception:
                pass
    html = "\n".join(out_parts)
    if not re.search(r"<p |<h[23]|<table|<ul", html):
        html = f"<p style=\"{p_}\">" + _linkify(html.replace("\n", "<br/>")) + "</p>"
    return f'<div style="{wrap}">' + html + "</div>"


class BloggerBrowserWriter:
    def __init__(self, page, log_func):
        self.page = page
        self.log = log_func
        self.wait_func = None
        self.blog_id = BLOG_ID

    async def wait(self, seconds):
        if self.wait_func:
            await self.wait_func(seconds)
        else:
            await asyncio.sleep(seconds)

    async def _paste_text(self, text: str):
        """클립보드에 복사 후 Ctrl+V로 붙여넣기 (사용자 요청: 복사해서 붙여넣기)."""
        if pyperclip:
            pyperclip.copy(text)
            await self.wait(0.2)
            if sys.platform == "win32":
                await self.page.keyboard.press("Control+v")
            else:
                await self.page.keyboard.press("Meta+v")
        else:
            await self.page.keyboard.type(text, delay=30)
        await self.wait(0.3)

    async def _fill_google_login(self) -> bool:
        """accounts.google.com에서 이메일/비밀번호 입력란 있으면 붙여넣기로 입력 후 다음 클릭."""
        if not BLOGGER_PASSWORD:
            return False
        try:
            # 1) 이메일/전화번호 입력란 있으면 붙여넣기 후 '다음'
            email_selectors = ["input[type='email']", "input#identifierId", "input[name='identifier']"]
            for sel in email_selectors:
                try:
                    el = self.page.locator(sel).first
                    if await el.count() > 0 and await el.is_visible(timeout=3000):
                        await el.click()
                        await self.wait(0.3)
                        await self._paste_text(BLOGGER_ACCOUNT_EMAIL)
                        self.log("      [구글 Blogger] 이메일 붙여넣기 완료.")
                        await self.wait(1)
                        next_btn = self.page.locator("span:has-text('다음'), button:has-text('다음'), #identifierNext, span:has-text('Next')").first
                        if await next_btn.count() > 0 and await next_btn.is_visible(timeout=3000):
                            await next_btn.click()
                            await self.wait(3)
                        return True
                except Exception:
                    continue

            # 2) 비밀번호 입력란 있으면 붙여넣기 후 '다음'/'로그인'
            pw_selectors = ["input[type='password']", "input[name='password']", "input[aria-label*='비밀번호']", "input[aria-label*='Password']"]
            for sel in pw_selectors:
                try:
                    el = self.page.locator(sel).first
                    if await el.count() > 0 and await el.is_visible(timeout=3000):
                        await el.click()
                        await self.wait(0.3)
                        await self._paste_text(BLOGGER_PASSWORD)
                        self.log("      [구글 Blogger] 비밀번호 붙여넣기 완료.")
                        await self.wait(1)
                        next_btn = self.page.locator("span:has-text('다음'), button:has-text('다음'), #passwordNext, span:has-text('Next'), span:has-text('로그인')").first
                        if await next_btn.count() > 0 and await next_btn.is_visible(timeout=3000):
                            await next_btn.click()
                            await self.wait(3)
                        return True
                except Exception:
                    continue
        except Exception as e:
            self.log(f"      [구글 Blogger] 로그인 자동 입력 오류: {e}")
        return False

    async def login_or_ensure_logged_in(self):
        """blogger.com 접속 → 로그인 클릭 → 계정 선택(canon4040@gmail.com) → 대시보드."""
        self.log("      [구글 Blogger] blogger.com 접속 중...")
        try:
            await self.page.goto(BLOGGER_ABOUT_URL, wait_until="domcontentloaded", timeout=60000)
            await self.wait(3)

            # 이미 대시보드에 있으면 draft URL로만 이동
            if "draft.blogger.com" in self.page.url or ("blogger.com/blog/posts" in self.page.url):
                self.log("      [구글 Blogger] 이미 로그인된 상태입니다.")
                if DRAFT_URL not in self.page.url:
                    await self.page.goto(DRAFT_URL, wait_until="domcontentloaded", timeout=30000)
                    await self.wait(2)
                return True

            # '로그인' 클릭 → 반드시 Blogger용 계정 선택(계정을 선택하세요)으로 이동하도록
            if "blogger.com" in self.page.url and "accounts.google.com" not in self.page.url:
                self.log("      [구글 Blogger] '로그인' 버튼 클릭...")
                # 1) Blogger 전용 로그인 링크 우선 (href에 blogger 포함 → 계정 선택 화면으로 감)
                clicked = False
                for sel in [
                    "a[href*='accounts.google.com'][href*='blogger']",
                    "a[href*='blogger'][href*='accounts.google.com']",
                    "a:has-text('로그인')[href*='accounts.google.com']",
                    "a:has-text('로그인')",
                    "span:has-text('로그인')",
                    "a[href*='accounts.google.com']",
                ]:
                    try:
                        lnk = self.page.locator(sel).first
                        if await lnk.count() > 0 and await lnk.is_visible(timeout=3000):
                            await lnk.click()
                            await self.wait(3)
                            clicked = True
                            break
                    except Exception:
                        continue
                # 2) 여전히 blogger.com에 있으면(다른 곳으로 빠짐) → Blogger 계정 선택(계정을 선택하세요)으로 직접 이동
                if "accounts.google.com" not in self.page.url:
                    self.log("      [구글 Blogger] '계정을 선택하세요' 화면으로 직접 이동...")
                    chooser_url = "https://accounts.google.com/v3/signin/accountchooser?continue=https://www.blogger.com/home&hl=ko&service=blogger"
                    await self.page.goto(chooser_url, wait_until="domcontentloaded", timeout=30000)
                    await self.wait(3)

            # accounts.google.com: 계정 선택 또는 이메일/비밀번호 입력
            if "accounts.google.com" in self.page.url:
                self.log("      [구글 Blogger] 구글 로그인 화면입니다.")
                # 1) 계정 선택 목록이 있으면 canon4040@gmail.com 클릭
                for sel in [
                    f"div:has-text('{BLOGGER_ACCOUNT_EMAIL}')",
                    f"span:has-text('{BLOGGER_ACCOUNT_EMAIL}')",
                    f"a:has-text('{BLOGGER_ACCOUNT_EMAIL}')",
                ]:
                    try:
                        el = self.page.locator(sel).first
                        if await el.count() > 0 and await el.is_visible(timeout=5000):
                            await el.click()
                            self.log(f"      [구글 Blogger] 계정 {BLOGGER_ACCOUNT_EMAIL} 선택함.")
                            await self.wait(4)
                            break
                    except Exception:
                        continue

                # 2) 아직 로그인 폼이면 이메일/비밀번호 붙여넣기로 입력 (복사해서 붙여넣기)
                if "accounts.google.com" in self.page.url and BLOGGER_PASSWORD:
                    await self._fill_google_login()
                    await self.wait(3)
                    if "accounts.google.com" in self.page.url:
                        await self._fill_google_login()

                self.log("      [구글 Blogger] 로그인 완료 후 대시보드 대기 중...")
                try:
                    await self.page.wait_for_url(
                        lambda url: "draft.blogger.com" in url or ("blogger.com" in url and "about" not in url),
                        timeout=60000
                    )
                    await self.wait(2)
                except Exception:
                    pass

            if "draft.blogger.com" not in self.page.url or "/posts/" not in self.page.url:
                await self.page.goto(DRAFT_URL, wait_until="domcontentloaded", timeout=30000)
                await self.wait(2)

            # '로그인할 수 없음' 등 오류 페이지면 수동 로그인 안내 후 대기
            try:
                content = await self.page.content()
                if "로그인할 수 없음" in content or "안전하지 않을 수 있습니다" in content:
                    self.log("      [구글 Blogger] 수동으로 로그인해 주세요. ('다시 시도' 또는 브라우저에서 직접 로그인)")
                    self.log("      완료하시면 자동으로 새글 작성으로 이어갑니다. (최대 3분 대기)")
                    self.log("      (대안: 브라우저 주소창 code= 뒤 코드를 복사해 save_token_from_callback_url로 API 발행 가능)")
            except Exception:
                pass

            # 아직 로그인 페이지에 있으면 수동 로그인 완료까지 대기 (3분)
            if "accounts.google.com" in self.page.url:
                self.log("      [구글 Blogger] 수동 로그인 완료될 때까지 대기 중...")
                try:
                    await self.page.wait_for_url(
                        lambda url: "draft.blogger.com" in url or ("blogger.com" in url and "about" not in url and "accounts" not in url),
                        timeout=180000
                    )
                    await self.wait(2)
                    self.log("      [구글 Blogger] 로그인 완료 감지. 대시보드로 이동합니다.")
                except Exception:
                    self.log("      [구글 Blogger] 3분 안에 로그인 완료를 감지하지 못했습니다.")
                    return False

            # 대시보드 URL로 한 번 더 확실히
            if "draft.blogger.com" not in self.page.url or "/posts/" not in self.page.url:
                await self.page.goto(DRAFT_URL, wait_until="domcontentloaded", timeout=30000)
                await self.wait(2)

            await self.wait(2)
            self.log("      [구글 Blogger] Blogger 대시보드 로드 완료. 이제 새글 작성으로 진행합니다.")
            return True
        except Exception as e:
            self.log(f"      [구글 Blogger] 접속 오류: {e}")
            return False

    async def navigate_to_new_post(self):
        """'+ 새글' 버튼 클릭 후 새 글 편집 화면으로 이동."""
        self.log("      [구글 Blogger] '새글' 버튼 클릭 시도...")
        try:
            await self.page.bring_to_front()
            await self.wait(3)
            # 좌측 사이드바/대시보드 로드 대기
            try:
                await self.page.wait_for_selector("nav, [role='navigation'], aside, .sidebar, [class*='sidebar']", timeout=8000)
            except Exception:
                pass
            await self.wait(2)

            # 1차 시도: role 기반 텍스트 매칭 (반응형/클래스 변경 대비)
            try:
                for name in ["+ 새 글", "+ 새글", "새 글", "New post"]:
                    try:
                        btn = self.page.get_by_role("button", name=name)
                        if await btn.count() > 0:
                            await btn.first.click()
                            await self.wait(4)
                            self.log("      [구글 Blogger] 새글 버튼 클릭(get_by_role).")
                            return True
                    except Exception:
                        continue
            except Exception:
                pass

            # 2차 시도: 기존 CSS/text 셀렉터들
            # 왼쪽 사이드바 '+ 새글' 버튼 (실제 DOM: span.MIJMVe "새 글")
            selectors = [
                "button:has(span.MIJMVe)",
                "a:has(span.MIJMVe)",
                "[role='button']:has(span.MIJMVe)",
                "span.MIJMVe",
                ".MIJMVe",
                "span.MIJMVe:has-text('새 글')",
                "[class*='MIJMVe']",
                "nav button:has-text('+ 새글')",
                "nav button:has-text('새글')",
                "nav button:has-text('새 글')",
                "nav .MIJMVe",
                "aside button:has-text('+ 새글')",
                "aside button:has-text('새글')",
                "button:has-text('+ 새글')",
                "button:has-text('새글')",
                "button:has-text('새 글')",
                "[role='button']:has-text('+ 새글')",
                "[role='button']:has-text('새글')",
                "a:has-text('+ 새글')",
                "a:has-text('+ 새 글')",
                "a:has-text('새글')",
                "a:has-text('새 글')",
                "nav [role='button']:has-text('새글')",
                "[aria-label*='새글']",
                "[aria-label*='새 글']",
                "[aria-label*='New post']",
                "span:has-text('새글')",
                "div:has-text('새글')",
                "button:has-text('New post')",
                "a[href*='/post/edit']",
                "a[href*='/post/create']",
            ]
            for attempt in range(3):
                for sel in selectors:
                    try:
                        btn = self.page.locator(sel).first
                        if await btn.count() > 0 and await btn.is_visible(timeout=4000):
                            await btn.click()
                            await self.wait(4)
                            self.log("      [구글 Blogger] 새글 편집 화면으로 이동 중...")
                            return True
                    except Exception:
                        continue
                if attempt < 2:
                    await self.wait(2)
            self.log("      [구글 Blogger] '새글' 버튼을 찾지 못했습니다. 대시보드에서 수동으로 '+ 새글'을 눌러 주세요.")
            return False
        except Exception as e:
            self.log(f"      [구글 Blogger] 새글 진입 오류: {e}")
            return False

    async def fill_and_publish(self, title: str, body: str, img_paths=None) -> bool:
        """제목·본문 입력 후 게시.
        1) 먼저 HTML 모드에서 body_html을 그대로 붙여넣고 '새 글 작성 보기'로 전환해 시각적으로 확인 가능한 상태를 만든 뒤,
        2) 실패 시에만 일반 에디터 모드에서 텍스트/이미지를 순서대로 넣는다.
        """
        img_paths = list(img_paths) if img_paths else []
        # HTML 모드 작성 시 사용할 전체 본문 HTML (텍스트 + 표 + 이미지)
        body_html = _body_to_html(body, img_paths)
        self.log("      [구글 Blogger] 제목·본문 입력 시작...")
        try:
            await self.wait(2)
            try:
                await self.page.wait_for_load_state("networkidle", timeout=20000)
            except Exception:
                pass
            await self.wait(3)

            # 1) 제목 입력만 — input만 사용. contenteditable은 본문(<p>&nbsp;</p> 영역)과 구분 위해 제외
            title_selectors = [
                "input[aria-label='제목']",
                "input.whsOnd",
                "input.zHQkBf",
                "input[jsname='YPqjbf']",
                "input[placeholder*='제목']",
                "input[aria-label*='제목']",
                "input[placeholder*='Title']",
                "[contenteditable='true'][data-placeholder*='제목']",
            ]
            title_done = False
            for sel in title_selectors:
                try:
                    el = self.page.locator(sel).first
                    if await el.count() > 0 and await el.is_visible(timeout=3000):
                        await el.click()
                        await self.wait(0.3)
                        await el.fill("")
                        await el.fill(title)
                        await self.wait(0.5)
                        title_done = True
                        self.log("      [구글 Blogger] 제목 입력 완료.")
                        break
                except Exception:
                    continue

            if not title_done:
                self.log("      [구글 Blogger] 제목 입력란을 찾지 못해 키보드로 시도합니다.")
                await self.page.keyboard.press("Control+Home")
                await self.wait(0.3)
                await self.page.keyboard.type(title, delay=30)

            # 제목란에서 포커스 빼기 (본문에 안 넣기 위해)
            await self.page.keyboard.press("Escape")
            await self.wait(0.3)

            import re

            await self.wait(1)

            # 2) 1차 시도: HTML 보기 모드에서 body_html을 그대로 붙여넣고, 다시 '새 글 작성 보기'로 전환
            body_done = False
            self.log("      [구글 Blogger] HTML 모드에서 본문을 작성한 뒤 '새 글 작성 보기'로 전환합니다.")
            html_toggled = False
            try:
                for sel in [
                    "button:has-text('HTML 보기')",
                    "button:has-text('HTML')",
                    "div[role='button']:has-text('HTML 보기')",
                    "div[role='button']:has-text('HTML')",
                    "span:has-text('HTML 보기')",
                ]:
                    try:
                        btn = self.page.locator(sel).first
                        if await btn.count() > 0 and await btn.is_visible(timeout=2000):
                            await btn.click()
                            await self.wait(1.5)
                            html_toggled = True
                            break
                    except Exception:
                        continue
            except Exception:
                html_toggled = False

            if html_toggled:
                try:
                    # HTML 편집창에 포커스
                    try:
                        editor = self.page.locator("textarea, [role='textbox']").first
                        if await editor.count() > 0:
                            await editor.click()
                            await self.wait(0.3)
                    except Exception:
                        editor = None

                    # 기존 내용 전체 삭제
                    try:
                        await self.page.keyboard.press("Control+a")
                        await self.wait(0.1)
                        await self.page.keyboard.press("Delete")
                        await self.wait(0.1)
                    except Exception:
                        pass

                    pasted = False
                    if pyperclip:
                        pyperclip.copy(body_html)
                        await self.wait(0.15)
                        await self.page.keyboard.press("Control+v")
                        pasted = True
                    elif sys.platform == "win32" and _set_html_clipboard_win(body_html):
                        await self.wait(0.15)
                        await self.page.keyboard.press("Control+v")
                        pasted = True
                    else:
                        await self.page.keyboard.type(body_html[:8000], delay=5)
                        pasted = True

                    if pasted:
                        self.log("      [구글 Blogger] HTML 모드에서 본문 HTML 붙여넣기 완료.")
                        body_done = True
                        # body_html 안에 이미 이미지(<img>)가 포함되어 있으므로, 이후 수동 이미지 삽입은 생략
                        img_paths = []

                    # 다시 '새 글 작성 보기'로 전환 (사용자가 보는 화면은 일반 모드)
                    for sel in [
                        "button:has-text('새 글 작성 보기')",
                        "div[role='button']:has-text('새 글 작성 보기')",
                        "span:has-text('새 글 작성 보기')",
                        ".DPvwYc.GHpiyd",
                    ]:
                        try:
                            btn = self.page.locator(sel).first
                            if await btn.count() > 0 and await btn.is_visible(timeout=2500):
                                await btn.click()
                                await self.wait(1.5)
                                self.log("      [구글 Blogger] '새 글 작성 보기'로 전환 완료.")
                                break
                        except Exception:
                            continue
                except Exception as e:
                    self.log(f"      [구글 Blogger] HTML 모드 작성/전환 실패: {e}")

            # 2-1) HTML 모드가 실패했을 때만 일반 에디터 모드에서 [IMAGE] 기준으로 텍스트/이미지를 순서대로 삽입
            if not body_done:
                self.log("      [구글 Blogger] HTML 모드 실패 또는 미사용 → 일반 모드로 본문을 입력합니다.")

            if not body_done:
                # 에디터(contenteditable) 영역에 포커스 먼저 시도 (iframe 포함)
                try:
                    focused = False
                    for frame in self.page.frames:
                        try:
                            el = frame.locator("[contenteditable='true'], [role='textbox']").first
                            if await el.count() > 0 and await el.is_visible(timeout=1500):
                                await el.click()
                                await self.wait(0.5)
                                focused = True
                                break
                        except Exception:
                            continue
                    if not focused:
                        try:
                            el = self.page.locator("[contenteditable='true'], [role='textbox']").first
                            if await el.count() > 0 and await el.is_visible(timeout=1500):
                                await el.click()
                                await self.wait(0.5)
                        except Exception:
                            pass
                except Exception:
                    pass

                # 기존 Tab 기반 포커스 이동은 보조용으로 유지
                for _ in range(10):
                    await self.page.keyboard.press("Tab")
                    await self.wait(0.2)
                await self.wait(0.5)

                parts = re.split(r'\[IMAGE\d*\]|\[이미지\d*\]', body, flags=re.I)
                marker_count = max(len(parts) - 1, 0)
                used_imgs = 0

                for i, part in enumerate(parts):
                    text_content = part.strip()
                    if text_content:
                        self.log(f"      [구글 Blogger] 본문 파트 {i+1} 입력 중...")
                        await self._paste_text(text_content)
                        await self.page.keyboard.press("Enter")
                        await self.page.keyboard.press("Enter")
                        await self.wait(0.3)

                    # 각 [IMAGE] 마커 위치에 맞춰 이미지 삽입
                    if img_paths and used_imgs < len(img_paths) and i < marker_count:
                        path = img_paths[used_imgs]
                        if path and os.path.isfile(path):
                            pasted = False
                            if sys.platform == "win32" and _copy_image_to_clipboard(path):
                                await self.wait(0.15)
                                await self.page.keyboard.press("Control+v")
                                # 업로드가 완료될 때까지 넉넉하게 대기
                                await self.wait(3.0)
                                pasted = True
                                self.log(f"      [구글 Blogger] 이미지 {used_imgs+1}/{len(img_paths)} 삽입.")
                            if not pasted:
                                self.log(f"      [구글 Blogger] 이미지 {used_imgs+1} 클립보드 삽입 실패.",)
                        used_imgs += 1

                # 마커가 없고 이미지가 남아 있으면 글 하단에만 이미지들을 순서대로 삽입
                if img_paths and marker_count == 0:
                    self.log("      [구글 Blogger] 본문 내 [IMAGE] 마커가 없어, 글 하단에 이미지를 정리해서 삽입합니다.")
                    for idx, path in enumerate(img_paths):
                        if not path or not os.path.isfile(path):
                            continue
                        if sys.platform == "win32" and _copy_image_to_clipboard(path):
                            await self.wait(0.15)
                            await self.page.keyboard.press("Control+v")
                            # 이미지 1장마다 업로드 완료까지 충분히 대기
                            await self.wait(3.0)
                            self.log(f"      [구글 Blogger] 이미지 {idx+1}/{len(img_paths)} 삽입.")

                # 모든 이미지를 붙여넣은 뒤, Blogger가 실제 업로드를 마칠 시간을 한 번 더 확보
                if img_paths:
                    # 이미지 개수에 비례해서 최소 5초 이상 대기
                    extra_secs = max(5, len(img_paths) * 2)
                    self.log(f"      [구글 Blogger] 모든 이미지 업로드 안정화 대기 중... (약 {extra_secs}초)")
                    for _ in range(extra_secs):
                        await self.wait(1)

                await self.wait(1)

            # 3) 게시 버튼 클릭 (우측 상단 오렌지 '게시' / 'Publish')
            publish_selectors = [
                "div.A2yzVd:has-text('게시')",
                "div.gNdO9b:has-text('게시')",
                "button:has-text('게시')",
                "span:has-text('게시')",
                "[aria-label*='게시']",
                "[aria-label*='Publish']",
                "button:has-text('Publish')",
                "div[role='button']:has-text('게시')",
                "div[role='button']:has-text('Publish')",
                "button:has-text('발행')",
                ".A2yzVd",
                ".gNdO9b",
                "div:has-text('게시')",
                "span:has-text('지금 게시')",
                "button:has-text('지금 게시')",
            ]
            published = False
            for attempt in range(3):
                for sel in publish_selectors:
                    # 메인 프레임 + 모든 iframe에서 게시 버튼 탐색
                    for ctx in [self.page, *self.page.frames]:
                        try:
                            btn = ctx.locator(sel).first
                            if await btn.count() > 0 and await btn.is_visible(timeout=2000):
                                await btn.scroll_into_view_if_needed()
                                await self.wait(0.3)
                                await btn.click(force=True)
                                await self.wait(2)
                                self.log("      [구글 Blogger] 게시 버튼 클릭.")
                                published = True
                                break
                        except Exception:
                            continue
                    if published:
                        break
                if published:
                    break
                await self.wait(1.5)
            if published:
                await self.wait(2)
                # 게시 확인 대화상자( '글을 게시하시겠습니까?'의 '확인' / '게시' / 'Publish' ) 클릭
                confirm_selectors = [
                    "div[role='dialog'] button:has-text('확인')",
                    "div[role='dialog'] button:has-text('게시')",
                    "button:has-text('확인')",
                    "button:has-text('게시')",
                    "span:has-text('확인')",
                    "span:has-text('게시')",
                    "button:has-text('Publish')",
                    "div[role='dialog'] button:has-text('Publish')",
                    "[aria-label*='게시']",
                ]
                confirmed = False
                for sel in confirm_selectors:
                    for ctx in [self.page, *self.page.frames]:
                        try:
                            confirm_btn = ctx.locator(sel).first
                            if await confirm_btn.count() > 0 and await confirm_btn.is_visible(timeout=1500):
                                await confirm_btn.click(force=True)
                                await self.wait(2)
                                self.log("      [구글 Blogger] 게시 확인 클릭 완료.")
                                confirmed = True
                                break
                        except Exception:
                            continue
                    if confirmed:
                        break
                return True

            # 게시 버튼을 못 찾으면 초안 저장 시도
            for sel in ["button:has-text('초안 저장')", "span:has-text('초안 저장')", "[aria-label*='저장']"]:
                try:
                    btn = self.page.locator(sel).first
                    if await btn.count() > 0 and await btn.is_visible(timeout=2000):
                        await btn.click()
                        await self.wait(2)
                        self.log("      [구글 Blogger] 초안 저장만 완료. (게시 버튼을 찾지 못했습니다.)")
                        return True
                except Exception:
                    continue
            await self.page.keyboard.press("Control+s")
            await self.wait(2)
            self.log("      [구글 Blogger] Ctrl+S로 저장 시도했습니다.")
            return True

        except Exception as e:
            self.log(f"      [구글 Blogger] 작성/저장 오류: {e}")
            return False

    async def write_draft(self, title: str, body: str, img_paths=None) -> bool:
        """전체 흐름: blogger.com → 로그인 → 계정 선택 → 새글 → 제목/본문 입력 → 게시(발행). img_paths 있으면 [IMAGE] 자리에 이미지 삽입."""
        if not await self.login_or_ensure_logged_in():
            return False
        if not await self.navigate_to_new_post():
            return False
        return await self.fill_and_publish(title, body, img_paths)
