# -*- coding: utf-8 -*-
"""블로그 파이프라인 — JARVIS 연동 시 integrations 사용, 없으면 login2 단독 실행."""

from __future__ import annotations

import os
import subprocess
import sys
import threading
from pathlib import Path
from typing import Any, Callable

_ROOT = Path(__file__).resolve().parent


def resolve_jarvis_root() -> Path:
    bundled = _ROOT / "javis"
    external = Path(os.environ.get("JARVIS_ROOT", r"D:\@code\javis"))
    for candidate in (external, bundled):
        if (candidate / "integrations" / "blog_auto_pipeline.py").is_file():
            return candidate.resolve()
    if external.is_dir():
        return external.resolve()
    if bundled.is_dir():
        return bundled.resolve()
    return external


def jarvis_pipeline_available() -> bool:
    root = resolve_jarvis_root()
    return (root / "integrations" / "blog_auto_pipeline.py").is_file()


def _ensure_jarvis_on_path() -> bool:
    root = resolve_jarvis_root()
    if not jarvis_pipeline_available():
        return False
    root_s = str(root)
    if root_s not in sys.path:
        sys.path.insert(0, root_s)
    return True


def _platforms_from_payload(p: dict[str, Any]) -> list[str] | None:
    if p.get("platforms") and isinstance(p["platforms"], list):
        return [str(x) for x in p["platforms"] if str(x).strip()]
    out: list[str] = []
    if p.get("use_tistory", True):
        out.append("tistory")
    if p.get("use_naver1", True) or p.get("use_naver2", True) or p.get("use_naver", True):
        out.append("naver")
    if p.get("use_google", False) or p.get("use_blogger", False):
        out.append("blogger")
    return out or None


def _keyword_from_payload(payload: dict[str, Any]) -> str:
    kw = (payload.get("keyword") or payload.get("topic") or "").strip()
    if not kw:
        kws = payload.get("keywords")
        if isinstance(kws, list) and kws:
            kw = ", ".join(str(x).strip() for x in kws if str(x).strip())
    return kw


def run_jarvis_pipeline(
    payload: dict[str, Any],
    *,
    on_status: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    if not _ensure_jarvis_on_path():
        return {"ok": False, "error": f"JARVIS 파이프라인 없음: {resolve_jarvis_root()}"}

    kw = _keyword_from_payload(payload)
    if not kw:
        return {"ok": False, "error": "키워드가 비어 있습니다."}

    publish = bool(payload.get("publish"))
    if payload.get("dry_run") is True or payload.get("preview_only") is True:
        publish = False

    skip_media = payload.get("skip_media")
    if skip_media is None:
        skip_media = not bool(payload.get("with_media"))

    with_video = bool(payload.get("with_video")) and not skip_media
    guideline = (payload.get("guideline") or payload.get("guideline_text") or "").strip()
    gl_path = (payload.get("guideline_path") or "").strip()
    if not guideline and gl_path:
        gp = Path(gl_path)
        if gp.is_file():
            try:
                guideline = gp.read_text(encoding="utf-8").strip()
            except OSError:
                pass

    log = on_status or (lambda _m: None)
    try:
        from integrations.blog_auto_pipeline import format_failure_summary_ko, run_blog_auto

        log(f"JARVIS 블로그 파이프라인: {kw[:80]}")
        report = run_blog_auto(
            kw,
            platforms=_platforms_from_payload(payload),
            publish=publish,
            skip_media=bool(skip_media),
            with_video=with_video,
            guideline=guideline,
            on_status=log,
        )
        if isinstance(report, dict) and not report.get("ok"):
            report.setdefault("error", format_failure_summary_ko(report))
        return report if isinstance(report, dict) else {"ok": False, "raw": report}
    except Exception as exc:
        return {"ok": False, "error": str(exc), "keyword": kw}


def run_standalone_pipeline(
    payload: dict[str, Any],
    *,
    on_status: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    """login2 _run_blog_session.py — JARVIS 없이 GUI·허브에서 호출."""
    log = on_status or (lambda _m: None)
    kw = _keyword_from_payload(payload)
    session = _ROOT / "_run_blog_session.py"
    if not session.is_file():
        return {"ok": False, "error": "_run_blog_session.py 없음"}

    publish = bool(payload.get("publish"))
    if payload.get("dry_run") is True or payload.get("preview_only") is True:
        publish = False
    if not publish:
        log("미리보기 모드 — accounts.json 설정으로 초안만 생성합니다.")

    env = os.environ.copy()
    env.setdefault("BLOG_STANDALONE", "1")
    env.setdefault("BLOG_JARVIS_BRIDGE", "0")
    if kw:
        env["BLOG_OVERRIDE_KEYWORD"] = kw

    log(f"단독 블로그 세션 시작: {kw or '(accounts.json)'}")
    py = sys.executable
    try:
        proc = subprocess.run(
            [py, str(session)],
            cwd=str(_ROOT),
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=int(os.environ.get("BLOG_SESSION_TIMEOUT", "3600")),
        )
        tail = (proc.stdout or "") + (proc.stderr or "")
        for line in tail.splitlines()[-40:]:
            if line.strip():
                log(line.strip())
        ok = proc.returncode == 0
        return {
            "ok": ok,
            "keyword": kw,
            "mode": "standalone",
            "returncode": proc.returncode,
            "error": None if ok else f"세션 종료 코드 {proc.returncode}",
        }
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "블로그 세션 시간 초과", "keyword": kw, "mode": "standalone"}
    except OSError as exc:
        return {"ok": False, "error": str(exc), "keyword": kw, "mode": "standalone"}


def run_pipeline(
    payload: dict[str, Any],
    *,
    on_status: Callable[[str], None] | None = None,
    prefer_jarvis: bool | None = None,
) -> dict[str, Any]:
    """JARVIS 있으면 integrations, 없으면 login2 단독. 클라우드는 콘텐츠 생성."""
    try:
        from hub_runtime import is_cloud_hub

        if is_cloud_hub():
            return _cloud_content_fallback(payload, on_status=on_status)
    except ImportError:
        pass

    use_jarvis = jarvis_pipeline_available() if prefer_jarvis is None else bool(prefer_jarvis)
    if use_jarvis and jarvis_pipeline_available():
        result = run_jarvis_pipeline(payload, on_status=on_status)
        if result.get("ok") or prefer_jarvis is True:
            return result
    return run_standalone_pipeline(payload, on_status=on_status)


def _cloud_content_fallback(
    payload: dict[str, Any],
    *,
    on_status: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    log = on_status or (lambda _m: None)
    kw = _keyword_from_payload(payload) or "나눔랩 코팅"
    log(f"클라우드 블로그 초안: {kw[:80]}")
    try:
        from seo_content_builder import generate_content, save_content

        result = generate_content("blog_review", kw, product_name=kw)
        if result.get("success"):
            try:
                result["saved_path"] = save_content(result)
            except OSError as exc:
                result["save_warning"] = str(exc)
        ok = bool(result.get("success"))
        content = result.get("content") or {}
        body = content.get("body") or ""
        if not body and content.get("sections"):
            body = "\n\n".join(
                f"## {k}\n{v}" for k, v in content["sections"].items()
            )
        article = {
            "title": content.get("title") or content.get("product_title_suggestion") or kw,
            "body_plain": body,
            "tags": content.get("seo_tags") or content.get("tags") or [],
        }
        return {
            "ok": ok,
            "keyword": kw,
            "mode": "cloud_content",
            "steps": {"article": {"article": article}},
            "result": result,
            "saved_path": result.get("saved_path"),
            "message": "클라우드에서 블로그 초안을 생성했습니다. 발행·이미지는 PC run_gui.bat을 사용하세요.",
            "error": None if ok else result.get("error"),
        }
    except Exception as exc:
        return {"ok": False, "error": str(exc), "keyword": kw, "mode": "cloud_content"}


def start_pipeline_async(
    payload: dict[str, Any],
    *,
    on_status: Callable[[str], None] | None = None,
    on_done: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    kw = _keyword_from_payload(payload)

    def _worker() -> None:
        result = run_pipeline(payload, on_status=on_status)
        if on_done:
            on_done(result)

    threading.Thread(target=_worker, daemon=True).start()
    return {"ok": True, "message": "블로그 파이프라인을 시작했습니다.", "keyword": kw, "async": True}
