# -*- coding: utf-8
"""티스토리·네이버·Google 자동 로그인 + 봇/캡차 감지 → 수동 대기."""

from __future__ import annotations

import time
from typing import Any, Callable

from integrations.blog_browser_base import login_timeout, wait_for_url_change
from integrations.blog_credentials import get_platform_creds, has_credentials
from integrations.blog_notify import alert_login_required


def detect_bot_or_captcha(page: Any) -> bool:
    """캡차·자동입력 방지·보안 확인 페이지."""
    try:
        url = (page.url or "").lower()
        if any(k in url for k in ("captcha", "recaptcha", "challenge", "verify")):
            return True
        body = page.locator("body").inner_text(timeout=3000).lower()
        keywords = (
            "자동입력 방지",
            "captcha",
            "보안문자",
            "로봇",
            "recaptcha",
            "추가 인증",
            "휴대폰으로 인증",
            "2단계",
        )
        if any(k in body for k in keywords):
            return True
        for sel in (
            "iframe[src*='recaptcha']",
            "#captcha",
            ".captcha",
            "[id*='captcha']",
            "img[alt*='캡']",
        ):
            if page.locator(sel).count() > 0:
                return True
    except Exception:
        pass
    return False


def _human_type(page: Any, selector: str, text: str) -> None:
    """네이버 등 붙여넣기 차단 필드 — 키보드로 한 글자씩 입력."""
    loc = page.locator(selector).first
    loc.click(timeout=8000)
    page.wait_for_timeout(300)
    try:
        loc.fill("")
    except Exception:
        pass
    page.wait_for_timeout(150)
    # delay(ms) — 너무 빠르면 자동입력 방지에 걸림
    loc.press_sequentially(text, delay=85)


def _fill_slow(page: Any, selector: str, text: str, *, human: bool = False) -> None:
    if human:
        _human_type(page, selector, text)
        return
    loc = page.locator(selector).first
    loc.click(timeout=5000)
    loc.fill("")
    page.wait_for_timeout(200)
    try:
        import pyperclip

        pyperclip.copy(text)
        page.keyboard.press("Control+V")
    except Exception:
        loc.fill(text)


def auto_login_naver(
    page: Any,
    *,
    account: dict[str, Any] | None = None,
    blog_id: str = "",
    on_status: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    emit = on_status or print
    if account:
        accounts = [account]
    else:
        from integrations.blog_credentials import get_naver_account_for_blog

        acc = get_naver_account_for_blog(blog_id)
        if acc:
            accounts = [acc]
        else:
            creds = get_platform_creds("naver")
            accounts = creds.get("accounts") or []
            if creds.get("id"):
                accounts = [
                    {"id": creds["id"], "password": creds.get("password", ""), "primary": True},
                    *list(accounts),
                ]

    if not accounts:
        return {"ok": False, "error": "naver credentials 없음", "needs_manual": True}

    page.goto("https://nid.naver.com/nidlogin.login", wait_until="domcontentloaded", timeout=60000)
    page.wait_for_timeout(1000)

    for acc in accounts:
        uid = (acc.get("id") or acc.get("email") or "").strip()
        pw = (acc.get("password") or "").strip()
        if not uid or not pw:
            continue
        emit(f"[네이버] 자동 로그인 시도: {uid[:20]}...")
        try:
            # 네이버 로그인창은 붙여넣기·fill 차단 → human_type 필수
            _fill_slow(page, "#id", uid, human=True)
            page.wait_for_timeout(500)
            _fill_slow(page, "#pw", pw, human=True)
            page.wait_for_timeout(600)
            for sel in ("#log\\.login", "button.btn_login", "input.btn_login"):
                try:
                    page.locator(sel).first.click(timeout=3000)
                    break
                except Exception:
                    continue
            page.wait_for_timeout(3500)
            if detect_bot_or_captcha(page):
                alert_login_required("naver", reason="captcha", detail=uid, on_status=emit)
                ok = wait_for_url_change(
                    page,
                    bad_url_checker=lambda u: "nidlogin" in (u or "").lower(),
                    on_status=emit,
                    timeout_sec=login_timeout("naver"),
                    message="네이버 캡차/봇 — 수동 로그인 후 Enter 대기",
                )
                return {"ok": ok, "account": uid, "manual": True}
            if "nidlogin" not in (page.url or "").lower():
                emit(f"[네이버] 로그인 성공 — {page.url[:60]}")
                return {"ok": True, "account": uid}
        except Exception as e:
            emit(f"[네이버] 시도 실패: {e}")

    alert_login_required("naver", reason="auto_login_failed", on_status=emit)
    ok = wait_for_url_change(
        page,
        bad_url_checker=lambda u: "nidlogin" in (u or "").lower(),
        on_status=emit,
        timeout_sec=login_timeout("naver"),
    )
    return {"ok": ok, "manual": True}


def auto_login_google(
    page: Any,
    *,
    on_status: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    emit = on_status or print
    creds = get_platform_creds("google")
    email = (creds.get("email") or "").strip()
    passwords = list(creds.get("passwords") or [])
    if creds.get("password"):
        passwords.insert(0, creds["password"])
    passwords = [p for p in passwords if p]

    if not email or not passwords:
        return {"ok": False, "error": "google credentials 없음", "needs_manual": True}

    page.goto("https://accounts.google.com/signin", wait_until="domcontentloaded", timeout=60000)
    page.wait_for_timeout(1500)

    try:
        if page.locator('input[type="email"]').count() > 0:
            _fill_slow(page, 'input[type="email"]', email, human=True)
            for sel in ("#identifierNext", "button:has-text('Next')", "button:has-text('다음')"):
                try:
                    page.locator(sel).first.click(timeout=3000)
                    break
                except Exception:
                    continue
            page.wait_for_timeout(2500)
    except Exception as e:
        emit(f"[Google] 이메일 단계: {e}")

    for pw in passwords:
        emit("[Google] 비밀번호 시도...")
        try:
            if page.locator('input[type="password"]').count() > 0:
                _fill_slow(page, 'input[type="password"]', pw, human=True)
                for sel in ("#passwordNext", "button:has-text('Next')", "button:has-text('다음')"):
                    try:
                        page.locator(sel).first.click(timeout=3000)
                        break
                    except Exception:
                        continue
                page.wait_for_timeout(4000)
            if detect_bot_or_captcha(page):
                alert_login_required("google", reason="captcha", detail=email, on_status=emit)
                ok = wait_for_url_change(
                    page,
                    bad_url_checker=lambda u: "accounts.google.com" in (u or "").lower()
                    and ("signin" in (u or "").lower() or "challenge" in (u or "").lower()),
                    on_status=emit,
                    timeout_sec=login_timeout("blogger"),
                )
                return {"ok": ok, "email": email, "manual": True}
            url = page.url or ""
            if "accounts.google.com/signin" not in url and "challenge" not in url.lower():
                emit(f"[Google] 로그인 성공")
                return {"ok": True, "email": email}
        except Exception as e:
            emit(f"[Google] 비밀번호 실패: {e}")

    alert_login_required("google", reason="auto_login_failed", detail=email, on_status=emit)
    ok = wait_for_url_change(
        page,
        bad_url_checker=lambda u: "signin" in (u or "").lower() or "challenge" in (u or "").lower(),
        on_status=emit,
        timeout_sec=login_timeout("blogger"),
    )
    return {"ok": ok, "email": email, "manual": True}


def auto_login_tistory(
    page: Any,
    *,
    on_status: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    emit = on_status or print
    creds = get_platform_creds("tistory")
    email = (creds.get("email") or "").strip()
    login_id = (creds.get("loginId") or creds.get("id") or "").strip()
    password = (creds.get("password") or "").strip()
    use_naver = creds.get("use_naver_login", True)

    page.goto("https://www.tistory.com/auth/login", wait_until="domcontentloaded", timeout=60000)
    page.wait_for_timeout(1500)

    if (email or login_id) and password:
        emit("[티스토리] 카카오/이메일 로그인 시도...")
        filled_id = False
        for sel, val in (
            ("#loginId", login_id or email),
            ("input[name='loginId']", login_id or email),
            ("input[type='email']", email or login_id),
        ):
            if not val:
                continue
            try:
                if page.locator(sel).count() > 0:
                    _fill_slow(page, sel, val)
                    filled_id = True
                    break
            except Exception:
                continue
        if not filled_id and email:
            for sel in ("input[type='text']", "input[placeholder*='아이디']"):
                try:
                    if page.locator(sel).count() > 0:
                        _fill_slow(page, sel, login_id or email)
                        break
                except Exception:
                    continue
        for sel in ("input[type='password']", "input[name='password']", "#password"):
            try:
                if page.locator(sel).count() > 0:
                    _fill_slow(page, sel, password)
                    break
            except Exception:
                continue
        for sel in ("button[type='submit']", "button:has-text('로그인')", ".btn_login"):
            try:
                page.locator(sel).first.click(timeout=3000)
                page.wait_for_timeout(3500)
                break
            except Exception:
                continue
        if not detect_bot_or_captcha(page) and "login" not in (page.url or "").lower():
            return {"ok": True, "method": "email"}

    if use_naver:
        emit("[티스토리] 네이버 계정 연동 로그인...")
        for sel in (
            "a:has-text('네이버')",
            "button:has-text('네이버')",
            "[class*='naver']",
        ):
            try:
                page.locator(sel).first.click(timeout=4000)
                page.wait_for_timeout(2000)
                break
            except Exception:
                continue
        if "nidlogin" in (page.url or "").lower():
            nr = auto_login_naver(page, on_status=emit)
            if nr.get("ok"):
                page.wait_for_timeout(3000)
                if "login" not in (page.url or "").lower():
                    return {"ok": True, "method": "naver"}

    if detect_bot_or_captcha(page):
        alert_login_required("tistory", reason="captcha", on_status=emit)
    else:
        alert_login_required("tistory", reason="auto_login_failed", on_status=emit)

    ok = wait_for_url_change(
        page,
        bad_url_checker=lambda u: "login" in (u or "").lower() and "tistory" in (u or "").lower(),
        on_status=emit,
        timeout_sec=login_timeout("tistory"),
    )
    return {"ok": ok, "manual": True}


def ensure_logged_in(
    platform: str,
    page: Any,
    *,
    is_login_url: Callable[[str], bool],
    naver_account: dict[str, Any] | None = None,
    naver_blog_id: str = "",
    on_status: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    """세션 없으면 자동 로그인 → 실패 시 알림 + 수동 대기."""
    emit = on_status or print
    try:
        url = page.url or ""
    except Exception:
        url = ""

    if url and not is_login_url(url):
        return {"ok": True, "already_logged_in": True}

    if not has_credentials(platform):
        emit(f"[{platform}] 저장된 계정 없음 — 수동 로그인 대기")
        alert_login_required(platform, reason="no_credentials", on_status=emit)
        ok = wait_for_url_change(page, bad_url_checker=is_login_url, on_status=emit, timeout_sec=login_timeout(platform))
        return {"ok": ok, "manual": True}

    emit(f"[{platform}] 자동 로그인...")
    if platform in ("naver",):
        r = auto_login_naver(
            page,
            account=naver_account,
            blog_id=naver_blog_id,
            on_status=emit,
        )
    elif platform in ("blogger", "google"):
        r = auto_login_google(page, on_status=emit)
    elif platform == "tistory":
        r = auto_login_tistory(page, on_status=emit)
    else:
        r = {"ok": False, "error": f"unknown platform {platform}"}

    if r.get("ok"):
        return r

    if not r.get("manual"):
        alert_login_required(platform, reason=r.get("error", "failed"), on_status=emit)
        ok = wait_for_url_change(page, bad_url_checker=is_login_url, on_status=emit, timeout_sec=login_timeout(platform))
        r["ok"] = ok
        r["manual"] = True
    return r
