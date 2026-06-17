# -*- coding: utf-8 -*-
"""SEO 허브(permacoat.shop) 실행 전 점검."""

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
    try:
        import app  # noqa: F401
        import rank_tracker  # noqa: F401
        import seo_content_builder  # noqa: F401

        return _step("SEO 허브 모듈", True, "app / rank_tracker / seo_content_builder")
    except Exception as e:
        return _step("SEO 허브 모듈", False, str(e)[:120], "pip install -r requirements.txt")


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
            text=True,
            timeout=120,
            cwd=_ROOT,
        )
        if proc.returncode != 0:
            return _step("SEO 허브 API", False, (proc.stdout or proc.stderr)[:200], "run_seo_hub_verify.bat")
        data = json.loads(proc.stdout or "{}")
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
        print(json.dumps({"ok": all_ok, "steps": steps}, ensure_ascii=False, indent=2))
        return 0 if all_ok else 1

    print("=" * 56)
    print("  Permacoat SEO Hub - programs check")
    print("=" * 56)
    for i, s in enumerate(steps, 1):
        mark = "OK" if s["ok"] else "FAIL"
        print(f"  [{i:02d}] [{mark}] {s['name']}")
        if s.get("detail"):
            print(f"        {s['detail']}")
        if not s["ok"] and s.get("fix"):
            print(f"        -> {s['fix']}")
    print("=" * 56)
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
