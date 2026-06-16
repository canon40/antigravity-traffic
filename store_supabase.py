# -*- coding: utf-8 -*-
"""스마트스토어 키워드 저장 — Supabase REST 또는 로컬 JSON 폴백."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

import config as cfg

_TABLE = os.environ.get("STORE_KEYWORDS_TABLE") or getattr(cfg, "STORE_KEYWORDS_TABLE", "keywords")
_LOCAL_PATH = Path(__file__).resolve().parent / "data" / "store_keywords.json"


def _env(key: str) -> str:
    return (os.environ.get(key) or getattr(cfg, key, "") or "").strip()


def _supabase_key(*, prefer_service: bool = False) -> str:
    if prefer_service:
        return (
            _env("SUPABASE_SERVICE_KEY")
            or _env("SUPABASE_SECRET_KEY")
            or _env("SUPABASE_ANON_KEY")
            or _env("SUPABASE_KEY")
        )
    return (
        _env("SUPABASE_SERVICE_KEY")
        or _env("SUPABASE_SECRET_KEY")
        or _env("SUPABASE_ANON_KEY")
        or _env("SUPABASE_KEY")
    )


def supabase_enabled() -> bool:
    return bool(_env("SUPABASE_URL") and _supabase_key())


def _headers() -> dict[str, str]:
    key = _supabase_key()
    return {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "Prefer": "resolution=merge-duplicates,return=representation",
    }


def _request(method: str, query: str = "", body: Any = None, timeout: float = 30.0) -> dict[str, Any]:
    base = _env("SUPABASE_URL").rstrip("/")
    if not supabase_enabled():
        return {"ok": False, "error": "SUPABASE_URL / KEY 미설정"}

    url = f"{base}/rest/v1/{_TABLE}"
    if query:
        url = f"{url}?{query}"

    data = None
    if body is not None:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")

    req = urllib.request.Request(url, data=data, headers=_headers(), method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
            if not raw.strip():
                return {"ok": True, "rows": []}
            parsed = json.loads(raw)
            rows = parsed if isinstance(parsed, list) else [parsed]
            return {"ok": True, "rows": rows}
    except urllib.error.HTTPError as e:
        return {"ok": False, "error": e.read().decode("utf-8", errors="replace"), "status": e.code}


def _load_local() -> list[dict[str, Any]]:
    if not _LOCAL_PATH.exists():
        return []
    try:
        with open(_LOCAL_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except Exception:
        return []


def _save_local(rows: list[dict[str, Any]]) -> None:
    _LOCAL_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(_LOCAL_PATH, "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=2)


def upsert_keywords(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """키워드 목록 저장. Supabase 미설정 시 로컬 JSON에 upsert."""
    if not rows:
        return {"ok": True, "count": 0, "backend": "none"}

    if supabase_enabled():
        res = _request("POST", query="on_conflict=category,keyword", body=rows)
        if res.get("ok"):
            saved = res.get("rows") or rows
            return {"ok": True, "count": len(saved), "backend": "supabase", "rows": saved}
        return {"ok": False, "error": res.get("error"), "backend": "supabase"}

    existing = _load_local()
    index = {(r.get("category"), r.get("keyword")): r for r in existing}
    for row in rows:
        key = (row.get("category"), row.get("keyword"))
        index[key] = {**index.get(key, {}), **row}
    merged = list(index.values())
    _save_local(merged)
    return {"ok": True, "count": len(rows), "backend": "local", "path": str(_LOCAL_PATH)}


def fetch_keywords(category: str, *, limit: int = 10) -> list[dict[str, Any]]:
    """카테고리별 키워드 상위 조회."""
    cat = (category or "").strip()
    if not cat:
        return []

    if supabase_enabled():
        q = (
            f"category=eq.{urllib.parse.quote(cat)}"
            f"&order=monthly_search_volume.desc"
            f"&limit={max(1, min(limit, 50))}"
        )
        res = _request("GET", query=q)
        if res.get("ok"):
            return res.get("rows") or []
        return []

    rows = [r for r in _load_local() if r.get("category") == cat]
    rows.sort(key=lambda x: int(x.get("monthly_search_volume") or 0), reverse=True)
    return rows[:limit]
