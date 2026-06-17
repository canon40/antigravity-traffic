# -*- coding: utf-8 -*-
"""SEO 허브(permacoat.shop) 실행 전 점검."""

from __future__ import annotations

import argparse
import json
import locale
import os
import subprocess
import sys

_ROOT = os.path.dirname(os.path.abspath(__file__))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)


def _step(name: str, ok: bool, detail: str = "", fix: str = "") -> dict:
    return {"name": name, "ok": ok, "detail": detail, "fix": fix}


def _safe_console_print(text: str) -> None:
    """Windows cp949 콘솔에서도 안전 출력."""
    stream = sys.stdout
    encoding = (
        getattr(stream, "encoding", None)
        or locale.getpreferredencoding(False)
        or "utf-8"
    )
    try:
        print(text)
    except UnicodeEncodeError:
        safe = text.encode(encoding, errors="backslashreplace").decode(encoding, errors="replace")
        print(safe)


def _decode_output(raw: bytes) -> str:
    if not raw:
        return ""
    for enc in ("utf-8", locale.getpreferredencoding(False) or "cp949", "cp949"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def check_python() -> dict:
    v = sys.version_info
    ok = v.major >= 3 and v.minor >= 10
    return _step("Python 3.10+", ok, f"{v.major}.{v.minor}.{v.micro}", "python.org 설치")


def check_venv() -> dict:
    venv_py = os.path.join(_ROOT, ".venv", "Scripts", "python.exe")
    ok = os.path.isfile(venv_py)
    return _step(
        "가상환경 .venv",
        ok,
        venv_py if ok else "없음",
        "run_install.bat 실행",
    )


def check_hub_imports() -> dict:
    prev = os.environ.get("AUTO_START_SCHEDULER")
    os.environ["AUTO_START_SCHEDULER"] = "0"
    try:
        import app  # noqa: F401
        import rank_tracker  # noqa: F401
        import seo_content_builder  # noqa: F401

        return _step("SEO 허브 모듈", True, "app / rank_tracker / seo_content_builder")
    except Exception as e:
        return _step("SEO 허브 모듈", False, str(e)[:120], "pip install -r requirements.txt")
    finally:
        if prev is None:
            os.environ.pop("AUTO_START_SCHEDULER", None)
        else:
            os.environ["AUTO_START_SCHEDULER"] = prev


def check_config_defaults() -> dict:
    path = os.path.join(_ROOT, "config.defaults.json")
    ok = os.path.isfile(path)
    return _step("config.defaults.json", ok, path if ok else "없음")


def check_traffic_session() -> dict:
    try:
        vt = os.path.join(_ROOT, "vercel_traffic")
        if vt not in sys.path:
            sys.path.insert(0, vt)
        from traffic_session import run_traffic_session  # noqa: F401

        return _step("traffic_session", True, "vercel_traffic/traffic_session.py")
    except Exception as e:
        return _step("traffic_session", False, str(e)[:120])


def check_seo_hub() -> dict:
    try:
        proc = subprocess.run(
            [sys.executable, os.path.join(_ROOT, "scripts", "verify_seo_hub.py"), "--json"],
            capture_output=True,
            text=False,
            timeout=120,
            cwd=_ROOT,
        )
        stdout_text = _decode_output(proc.stdout)
        stderr_text = _decode_output(proc.stderr)
        if proc.returncode != 0:
            return _step("SEO 허브 API", False, (stdout_text or stderr_text)[:200], "run_seo_hub_verify.bat")

        raw = (stdout_text or "").strip()
        # 일부 환경에서 stdout 앞에 잡문자가 섞일 수 있어 JSON 객체 부분만 추출
        if raw:
            start = raw.find("{")
            end = raw.rfind("}")
            if start >= 0 and end >= start:
                raw = raw[start : end + 1]
        data = json.loads(raw or "{}")
        return _step("SEO 허브 API", data.get("ok", False), f"checks={len(data.get('results') or [])}")
    except Exception as e:
        return _step("SEO 허브 API", False, str(e)[:100], "run_seo_hub_verify.bat")


def run_checks() -> list[dict]:
    return [
        check_python(),
        check_venv(),
        check_hub_imports(),
        check_config_defaults(),
        check_traffic_session(),
        check_seo_hub(),
    ]


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="SEO 허브 점검")
    p.add_argument("--json", action="store_true")
    p.add_argument("--minimal", action="store_true", help="호환용 — 전체와 동일")
    args = p.parse_args(argv)

    steps = run_checks()
    all_ok = all(s["ok"] for s in steps)

    if args.json:
        _safe_console_print(json.dumps({"ok": all_ok, "steps": steps}, ensure_ascii=False, indent=2))
        return 0 if all_ok else 1

    _safe_console_print("=" * 56)
    _safe_console_print("  Permacoat SEO Hub - programs check")
    _safe_console_print("=" * 56)
    for i, s in enumerate(steps, 1):
        mark = "OK" if s["ok"] else "FAIL"
        _safe_console_print(f"  [{i:02d}] [{mark}] {s['name']}")
        if s.get("detail"):
            _safe_console_print(f"        {s['detail']}")
        if not s["ok"] and s.get("fix"):
            _safe_console_print(f"        -> {s['fix']}")
    _safe_console_print("=" * 56)
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
