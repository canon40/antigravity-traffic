# -*- coding: utf-8 -*-
"""Claude Fable 5 · OpenClaw 연동 상태 점검."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

_ROOT = Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

JARVIS_ROOT = Path(os.environ.get("JARVIS_ROOT", r"D:\@code\javis"))
OPENCLAW_WS = _ROOT / ".openclaw" / "workspace"
GATEWAY_URL = "http://127.0.0.1:18789/"


def _ok(msg: str) -> None:
    print(f"  [OK] {msg}")


def _fail(msg: str) -> None:
    print(f"  [XX] {msg}")


def _warn(msg: str) -> None:
    print(f"  [!!] {msg}")


def check_fable() -> bool:
    print("\n=== Claude Fable 5 ===")
    ok = True
    if not JARVIS_ROOT.is_dir():
        _fail(f"JARVIS_ROOT 없음: {JARVIS_ROOT}")
        return False
    bridge = JARVIS_ROOT / "integrations" / "claude_fable_bridge.py"
    if bridge.is_file():
        _ok("JARVIS claude_fable_bridge")
    else:
        _fail("claude_fable_bridge.py 없음")
        ok = False

    loop = _ROOT / "LOOP.md"
    if loop.is_file():
        _ok(f"LOOP.md ({loop.stat().st_size} bytes)")
    else:
        _warn("LOOP.md 없음 — run_fable5.bat apply")

    try:
        import config  # noqa: F401 — _apply_jarvis_claude_fable

        model = os.environ.get("BLOG_CLAUDE_MODEL", "").strip() or "claude-fable-5"
        if "fable" in model.lower():
            _ok(f"BLOG_CLAUDE_MODEL = {model}")
        else:
            _warn(f"BLOG_CLAUDE_MODEL = {model} (fable 아님)")
        key = (os.environ.get("ANTHROPIC_API_KEY") or "").strip()
        if key and len(key) > 8:
            _ok("ANTHROPIC_API_KEY 설정됨")
        else:
            _warn("ANTHROPIC_API_KEY 없음 — Claude API 직접 호출 시 필요 (Ollama만 쓰면 생략 가능)")
    except Exception as e:
        _fail(f"config 로드: {e}")
        ok = False

    return ok


def _openclaw_cli() -> str | None:
    return shutil.which("openclaw")


def check_openclaw() -> bool:
    print("\n=== OpenClaw ===")
    ok = True
    cli = _openclaw_cli()
    if not cli:
        _fail("openclaw CLI 없음 — npm install -g openclaw@latest")
        return False
    try:
        r = subprocess.run(
            [cli, "--version"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
        )
        ver = (r.stdout or r.stderr or "").strip().splitlines()[0] if r.returncode == 0 else ""
        if ver:
            _ok(ver)
        else:
            _fail("openclaw --version 실패")
            ok = False
    except Exception as e:
        _fail(str(e))
        ok = False

    if OPENCLAW_WS.is_dir():
        _ok(f"workspace: {OPENCLAW_WS}")
    else:
        _warn(f"workspace 없음 — run_openclaw.bat onboard")

    cfg = Path.home() / ".openclaw" / "openclaw.json"
    if cfg.is_file():
        _ok(f"config: {cfg}")
    else:
        _fail("~/.openclaw/openclaw.json 없음")
        ok = False

    try:
        req = urllib.request.Request(GATEWAY_URL, method="GET")
        with urllib.request.urlopen(req, timeout=5) as resp:
            if 200 <= resp.status < 500:
                _ok(f"Gateway 응답 ({GATEWAY_URL})")
            else:
                _warn(f"Gateway HTTP {resp.status}")
    except urllib.error.URLError:
        _fail(f"Gateway 미응답 ({GATEWAY_URL}) — run_openclaw.bat start")
        ok = False

    try:
        r = subprocess.run(
            [cli, "gateway", "status"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=45,
        )
        out = r.stdout or ""
        if "Connectivity probe: ok" in out or "Runtime: running" in out:
            _ok("gateway status: running")
        elif r.returncode == 0:
            _warn("gateway status: 확인 필요")
        else:
            _fail("gateway status 실패")
            ok = False
    except Exception as e:
        _warn(f"gateway status: {e}")

    return ok


def main(argv=None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--fable-only", action="store_true")
    p.add_argument("--openclaw-only", action="store_true")
    p.add_argument("--json", action="store_true")
    args = p.parse_args(argv)

    do_fable = not args.openclaw_only
    do_openclaw = not args.fable_only
    fable_ok = check_fable() if do_fable else True
    openclaw_ok = check_openclaw() if do_openclaw else True
    all_ok = fable_ok and openclaw_ok

    if args.json:
        print(
            json.dumps(
                {"fable_ok": fable_ok, "openclaw_ok": openclaw_ok, "ok": all_ok},
                ensure_ascii=False,
            )
        )
    else:
        print("\n" + ("전체 OK" if all_ok else "일부 항목 확인 필요"))
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
