# -*- coding: utf-8
"""블로그 중복 콘텐츠 방지 — 해시·유사도·키워드 재발행 쿨다운."""

from __future__ import annotations

import hashlib
import json
import re
import time
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parent.parent


def _registry_path() -> Path:
    try:
        cfg = json.loads((_ROOT / "config" / "blog_automation.json").read_text(encoding="utf-8"))
        rel = cfg.get("registry_path") or ".jarvis/blog_published/registry.jsonl"
    except Exception:
        rel = ".jarvis/blog_published/registry.jsonl"
    p = _ROOT / rel if not str(rel).startswith("~") else Path.home() / str(rel).replace("~", "").lstrip("/\\")
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _load_cfg() -> dict[str, Any]:
    p = _ROOT / "config" / "blog_automation.json"
    if p.is_file():
        return json.loads(p.read_text(encoding="utf-8"))
    return {}


def normalize_text(text: str) -> str:
    t = re.sub(r"<[^>]+>", " ", text or "")
    t = re.sub(r"\s+", " ", t).strip().lower()
    t = re.sub(r"[^\w\s가-힣]", "", t)
    return t


def content_hash(text: str) -> str:
    return hashlib.sha256(normalize_text(text).encode("utf-8")).hexdigest()[:16]


def load_registry(limit: int = 500) -> list[dict[str, Any]]:
    path = _registry_path()
    if not path.is_file():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except Exception:
            continue
    return rows[-limit:]


def similarity(a: str, b: str) -> float:
    na, nb = normalize_text(a), normalize_text(b)
    if not na or not nb:
        return 0.0
    return SequenceMatcher(None, na, nb).ratio()


def check_duplicate(
    *,
    keyword: str,
    title: str,
    body: str,
) -> dict[str, Any]:
    """중복 여부 검사. ok=True면 발행 가능."""
    import os

    if os.environ.get("JARVIS_BLOG_SKIP_DUP", "").strip().lower() in ("1", "true", "yes"):
        return {"ok": True, "skipped": True, "content_hash": content_hash(body), "title_hash": content_hash(title)}

    cfg = _load_cfg().get("duplicate") or {}
    max_sim = float(cfg.get("max_similarity", 0.72))
    cooldown_h = int(cfg.get("forbid_same_keyword_repeat_hours", 168))
    h = content_hash(body)
    th = content_hash(title)
    now = time.time()
    rows = load_registry()

    for row in rows:
        if row.get("content_hash") == h:
            return {
                "ok": False,
                "reason": "identical_body_hash",
                "match": row,
            }
        if row.get("title_hash") == th:
            return {
                "ok": False,
                "reason": "identical_title_hash",
                "match": row,
            }
        sim = similarity(body, row.get("body_preview") or row.get("title") or "")
        if sim >= max_sim:
            return {
                "ok": False,
                "reason": "high_similarity",
                "similarity": round(sim, 3),
                "match": row,
            }

    kw = normalize_text(keyword)
    for row in rows:
        if normalize_text(row.get("keyword") or "") != kw:
            continue
        ts = float(row.get("published_at") or 0)
        if ts and (now - ts) < cooldown_h * 3600:
            return {
                "ok": False,
                "reason": "keyword_cooldown",
                "hours_left": round((cooldown_h * 3600 - (now - ts)) / 3600, 1),
                "match": row,
            }

    return {"ok": True, "content_hash": h, "title_hash": th}


def record_published(
    *,
    keyword: str,
    title: str,
    body: str,
    platforms: list[str],
    media_dir: str = "",
) -> dict[str, Any]:
    row = {
        "published_at": time.time(),
        "keyword": keyword,
        "title": title,
        "body_preview": normalize_text(body)[:400],
        "content_hash": content_hash(body),
        "title_hash": content_hash(title),
        "platforms": platforms,
        "media_dir": media_dir,
    }
    path = _registry_path()
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")
    return row
