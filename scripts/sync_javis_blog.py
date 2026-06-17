# -*- coding: utf-8 -*-
"""JARVIS 블로그 엔진 → login2/javis 번들 동기화 (Cloudtype·permacoat용)."""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SRC = Path(r"D:\@code\javis")
DEST = ROOT / "javis"

INTEGRATION_GLOBS = (
    "blog_*.py",
    "canon_autoblog_bridge.py",
)
CONFIG_FILES = (
    "config/blog_automation.json",
    "config/blog_writing_guideline.txt",
)


def sync(src: Path, *, dry_run: bool = False) -> int:
    if not src.is_dir():
        print(f"[ERR] JARVIS 소스 없음: {src}")
        return 1

    copied = 0
    integ_src = src / "integrations"
    integ_dest = DEST / "integrations"
    integ_dest.mkdir(parents=True, exist_ok=True)

    for pattern in INTEGRATION_GLOBS:
        for path in sorted(integ_src.glob(pattern)):
            target = integ_dest / path.name
            if dry_run:
                print(f"  would copy {path.name}")
            else:
                shutil.copy2(path, target)
            copied += 1

    for rel in CONFIG_FILES:
        sp = src / rel
        dp = DEST / rel
        if not sp.is_file():
            continue
        dp.parent.mkdir(parents=True, exist_ok=True)
        if dry_run:
            print(f"  would copy {rel}")
        else:
            shutil.copy2(sp, dp)
        copied += 1

    init_py = integ_dest / "__init__.py"
    if not dry_run and not init_py.is_file():
        init_py.write_text("", encoding="utf-8")

    cfg_init = DEST / "config" / "__init__.py"
    if not dry_run and not cfg_init.is_file():
        cfg_init.parent.mkdir(parents=True, exist_ok=True)
        cfg_init.write_text("", encoding="utf-8")

    print(f"[OK] sync_javis_blog: {copied} files → {DEST}")
    return 0


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--src", default=str(DEFAULT_SRC))
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()
    return sync(Path(args.src), dry_run=args.dry_run)


if __name__ == "__main__":
    raise SystemExit(main())
