# -*- coding: utf-8 -*-
"""
실행 전 프로그램·의존성 순차 점검.
에이전트 작업 전에 이 스크립트가 모두 OK여야 합니다.

  python programs_check.py
  python programs_check.py --json
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys

_ROOT = os.path.dirname(os.path.abspath(__file__))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)


def _step(name: str, ok: bool, detail: str = "", fix: str = "") -> dict:
    return {"name": name, "ok": ok, "detail": detail, "fix": fix}


def check_python() -> dict:
    v = sys.version_info
    ok = v.major >= 3 and v.minor >= 10
    return _step(
        "Python 3.10+",
        ok,
        f"{v.major}.{v.minor}.{v.micro}",
        "python.org 또는 .venv 재생성",
    )


def check_venv() -> dict:
    venv_py = os.path.join(_ROOT, ".venv", "Scripts", "python.exe")
    ok = os.path.isfile(venv_py)
    return _step(
        "가상환경 .venv",
        ok,
        venv_py if ok else "없음",
        "python -m venv .venv && .venv\\Scripts\\pip install -r requirements.txt",
    )


def check_accounts() -> dict:
    path = os.path.join(_ROOT, "accounts.json")
    if not os.path.isfile(path):
        return _step("accounts.json", False, "없음", "GUI 설정 탭에서 저장하거나 accounts.json 생성")
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        return _step("accounts.json", False, str(e)[:80], "JSON 형식 수정")
    has_naver = bool((data.get("naver_id1") or "").strip())
    has_gemini = bool((data.get("gemini_key") or "").strip())
    detail = f"naver={'Y' if has_naver else 'N'}, gemini_key={'Y' if has_gemini else 'N'}"
    return _step("accounts.json", True, detail, "이미지용 gemini_key 권장" if not has_gemini else "")


def check_wiki() -> dict:
    wiki = os.path.join(_ROOT, "wiki", "00_core.md")
    ok = os.path.isfile(wiki)
    return _step(
        "wiki 지침 슬라이스",
        ok,
        wiki if ok else "wiki/00_core.md 없음",
        "wiki/ 폴더 확인 (LLM Wiki 스타일)",
    )


def check_drawer() -> dict:
    try:
        from drawer.registry import agents_config, loaded_modules
        from blog_constants import DRAWER_MODULES

        cfg = agents_config()
        n_workers = len(cfg.get("workers") or {})
        ok = n_workers >= 3 and "blog" in DRAWER_MODULES
        return _step(
            "서랍(drawer) 패키지",
            ok,
            f"modules={len(DRAWER_MODULES)}, workers={n_workers}, loaded={len(loaded_modules())}",
        )
    except Exception as e:
        return _step("서랍(drawer) 패키지", False, str(e)[:100])


def check_gui_import() -> dict:
    try:
        import blog_main  # noqa: F401 — heavy 모듈 없이 import 가능해야 함

        return _step("GUI 경량 import (blog_main)", True, "Playwright/content_gen 미로드")
    except Exception as e:
        return _step("GUI 경량 import (blog_main)", False, str(e)[:120])


def check_ollama() -> dict:
    try:
        import urllib.request

        req = urllib.request.Request("http://127.0.0.1:11434/api/tags", method="GET")
        with urllib.request.urlopen(req, timeout=3) as resp:
            data = json.loads(resp.read().decode())
        models = [m.get("name", "") for m in (data.get("models") or [])]
        want = os.environ.get("BLOG_OLLAMA_MODEL", "qwen3:4b")
        has_model = any(want in m or m.startswith(want.split(":")[0]) for m in models)
        return _step(
            "Ollama (로컬 LLM)",
            True,
            f"models={len(models)}, target={want}, ready={'Y' if has_model else 'N'}",
            f"ollama pull {want}" if not has_model else "",
        )
    except Exception:
        return _step(
            "Ollama (로컬 LLM)",
            False,
            "http://127.0.0.1:11434 응답 없음",
            "터미널에서 ollama serve 실행 후 ollama pull qwen3:4b",
        )


def check_playwright() -> dict:
    try:
        import playwright  # noqa: F401

        return _step("Playwright (블로그 발행)", True, "설치됨", "발행 시에만 로드")
    except ImportError:
        return _step(
            "Playwright (블로그 발행)",
            False,
            "미설치",
            "pip install playwright && playwright install chromium",
        )


def check_javis_port() -> dict:
    port = int(os.environ.get("CANON_AUTOBLOG_PORT", "8790"))
    try:
        import urllib.request

        urllib.request.urlopen(f"http://127.0.0.1:{port}/api/javis/health", timeout=1)
        return _step("JARVIS 브리지 (GUI 실행 중)", True, f"port {port}")
    except Exception:
        return _step(
            "JARVIS 브리지 (GUI 실행 중)",
            False,
            f"port {port} — GUI 미실행",
            "run_gui.bat 실행 후 JARVIS 연동",
        )


def run_checks(*, include_optional: bool = True) -> list[dict]:
    steps = [
        check_python(),
        check_venv(),
        check_accounts(),
        check_wiki(),
        check_drawer(),
        check_gui_import(),
        check_ollama(),
    ]
    if include_optional:
        steps.append(check_playwright())
        steps.append(check_javis_port())
    return steps


def _safe_print(line: str) -> None:
    if sys.platform == "win32":
        enc = sys.stdout.encoding or "utf-8"
        try:
            print(line.encode(enc, errors="replace").decode(enc, errors="replace"), flush=True)
        except Exception:
            print(line, flush=True)
    else:
        print(line, flush=True)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Autoblog 프로그램 순차 점검")
    p.add_argument("--json", action="store_true")
    p.add_argument("--minimal", action="store_true", help="필수만 (Playwright/JARVIS 제외)")
    args = p.parse_args(argv)

    steps = run_checks(include_optional=not args.minimal)
    required = steps if args.minimal else steps[:7]
    all_required_ok = all(s["ok"] for s in required)
    all_ok = all(s["ok"] for s in steps)

    if args.json:
        print(
            json.dumps(
                {
                    "required_ok": all_required_ok,
                    "all_ok": all_ok,
                    "steps": steps,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0 if all_required_ok else 1

    _safe_print("=" * 60)
    _safe_print("  Canon4040 Autoblog - 프로그램 점검 (에이전트 작업 전)")
    _safe_print("=" * 60)
    for i, s in enumerate(steps, 1):
        mark = "OK" if s["ok"] else "FAIL"
        _safe_print(f"  [{i:02d}] [{mark}] {s['name']}")
        if s.get("detail"):
            _safe_print(f"        {s['detail']}")
        if not s["ok"] and s.get("fix"):
            _safe_print(f"        -> {s['fix']}")
    _safe_print("-" * 60)
    if all_required_ok:
        _safe_print("  필수 항목: 통과 - 에이전트 파이프라인 시작 가능")
    else:
        _safe_print("  필수 항목: 실패 - 위 FAIL 항목을 먼저 해결하세요")
    if not all_ok and all_required_ok:
        _safe_print("  (선택 항목 일부 미충족 - 원고만: run_draft.bat / 발행: Playwright+GUI)")
    _safe_print("=" * 60)
    return 0 if all_required_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
