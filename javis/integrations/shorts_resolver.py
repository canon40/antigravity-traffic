# -*- coding: utf-8
"""AI Factory 숏폼 MP4 탐색·생성."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Callable

_ROOT = Path(__file__).resolve().parent.parent
_MANIFEST = _ROOT.parent / "data" / "shorts_manifest.json"


def _ai_factory_root() -> Path:
    env = (os.environ.get("AI_FACTORY_ROOT") or "").strip()
    if env:
        return Path(env)
    try:
        cfg_path = _ROOT / "config" / "blog_automation.json"
        if cfg_path.is_file():
            media = json.loads(cfg_path.read_text(encoding="utf-8")).get("media") or {}
            p = (media.get("ai_factory_root") or "").strip()
            if p:
                return Path(p)
    except Exception:
        pass
    return Path(r"D:\@code\ai factory")


def _slug(keyword: str) -> str:
    s = re.sub(r"[^\w가-힣]+", "_", (keyword or "").strip())
    return s.strip("_") or "shorts"


def find_shorts_mp4(keyword: str) -> Path | None:
    """키워드에 해당하는 기존 *_shorts.mp4 검색."""
    kw = (keyword or "").strip()
    if not kw:
        return None
    root = _ai_factory_root()
    if not root.is_dir():
        return None

    slug = _slug(kw)
    candidates = [
        root / f"{slug}_shorts.mp4",
        root / f"{kw}_shorts.mp4",
        root / f"{kw.replace(' ', '_')}_shorts.mp4",
    ]
    for p in candidates:
        if p.is_file() and p.stat().st_size > 10_000:
            return p.resolve()

    best: Path | None = None
    kw_low = kw.lower()
    for p in root.glob("*_shorts.mp4"):
        if not p.is_file() or p.stat().st_size < 10_000:
            continue
        stem = p.stem.lower()
        if kw_low in stem or slug.lower() in stem:
            best = p.resolve()
            break
    return best


def create_shorts_mp4(
    keyword: str,
    *,
    duration: int = 30,
    test_mode: bool = False,
    on_status: Callable[[str], None] | None = None,
) -> Path | None:
    """AI Factory auto_shorts_creator.py 로 MP4 생성."""
    emit = on_status or print
    root = _ai_factory_root()
    script = root / "auto_shorts_creator.py"
    if not script.is_file():
        emit(f"[숏폼] auto_shorts_creator.py 없음: {script}")
        return None

    py = sys.executable
    cmd = [py, str(script), keyword, "-d", str(duration)]
    if test_mode:
        cmd.append("--test")
    emit(f"[숏폼] 생성 시작: {keyword}")
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(root),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=int(os.environ.get("SHORTS_CREATE_TIMEOUT", "3600")),
        )
        tail = ((proc.stdout or "") + (proc.stderr or "")).strip()
        for line in tail.splitlines()[-8:]:
            if line.strip():
                emit(f"  {line.strip()}")
        if proc.returncode != 0:
            emit(f"[숏폼] 생성 실패 (code={proc.returncode})")
            return None
    except subprocess.TimeoutExpired:
        emit("[숏폼] 생성 시간 초과")
        return None
    except Exception as exc:
        emit(f"[숏폼] 생성 오류: {exc}")
        return None

    found = find_shorts_mp4(keyword)
    if found:
        emit(f"[숏폼] 완료: {found}")
    return found


def ensure_shorts_mp4(
    keyword: str,
    *,
    create_if_missing: bool = True,
    duration: int = 30,
    test_mode: bool = False,
    on_status: Callable[[str], None] | None = None,
) -> Path | None:
    existing = find_shorts_mp4(keyword)
    if existing:
        return existing
    if not create_if_missing:
        return None
    return create_shorts_mp4(
        keyword,
        duration=duration,
        test_mode=test_mode,
        on_status=on_status,
    )


def load_manifest() -> dict[str, Any]:
    if not _MANIFEST.is_file():
        return {"entries": {}}
    try:
        return json.loads(_MANIFEST.read_text(encoding="utf-8"))
    except Exception:
        return {"entries": {}}


def save_manifest_entry(keyword: str, *, video_path: str = "", youtube_url: str = "", blog_ok: bool = False) -> None:
    data = load_manifest()
    entries = data.setdefault("entries", {})
    key = (keyword or "").strip()
    row = dict(entries.get(key) or {})
    row.update(
        {
            "keyword": key,
            "video_path": video_path or row.get("video_path", ""),
            "youtube_url": youtube_url or row.get("youtube_url", ""),
            "blog_ok": blog_ok or row.get("blog_ok", False),
            "updated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        }
    )
    entries[key] = row
    _MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    _MANIFEST.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def manifest_youtube_url(keyword: str) -> str:
    row = (load_manifest().get("entries") or {}).get((keyword or "").strip()) or {}
    return str(row.get("youtube_url") or "").strip()
