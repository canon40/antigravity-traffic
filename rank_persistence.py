# -*- coding: utf-8 -*-
"""순위 히스토리·허브 상태 — Supabase REST 또는 로컬 JSON/CSV 폴백."""

from __future__ import annotations

import csv
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any

from app_resources import get_storage_dir
from hub_runtime import is_vercel, uses_ephemeral_disk

_HISTORY_TABLE = os.environ.get("RANK_HISTORY_TABLE") or "rank_history"
_STATE_TABLE = os.environ.get("RANK_HUB_STATE_TABLE") or "rank_hub_state"
_STATE_ID = 1

_ROOT = Path(__file__).resolve().parent
_BUNDLED_STATE = _ROOT / "data" / "rank_hub_state.json"
_BUNDLED_SEED = _ROOT / "data" / "rank_history_seed.json"
_LOCAL_STATE = _ROOT / "data" / "rank_hub_state.json"

HISTORY_HEADERS = ["날짜", "키워드", "스토어명", "순위", "이전순위", "변동", "작업유형", "상세"]


def _env(key: str) -> str:
    return (os.environ.get(key) or "").strip()


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


def persistence_backend() -> str:
    if supabase_enabled():
        return "supabase"
    if is_vercel():
        return "vercel_tmp"
    if uses_ephemeral_disk():
        return "cloud_tmp"
    return "local"


def _headers(*, prefer_service: bool = False, merge: bool = False) -> dict[str, str]:
    key = _supabase_key(prefer_service=prefer_service)
    prefer = "return=representation"
    if merge:
        prefer = f"resolution=merge-duplicates,{prefer}"
    return {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "Prefer": prefer,
    }


def _request(
    table: str,
    method: str,
    query: str = "",
    body: Any = None,
    *,
    prefer_service: bool = False,
    merge: bool = False,
    timeout: float = 30.0,
) -> dict[str, Any]:
    base = _env("SUPABASE_URL").rstrip("/")
    if not supabase_enabled():
        return {"ok": False, "error": "SUPABASE 미설정"}

    url = f"{base}/rest/v1/{table}"
    if query:
        url = f"{url}?{query}"

    data = None
    if body is not None:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")

    req = urllib.request.Request(url, data=data, headers=_headers(prefer_service=prefer_service, merge=merge), method=method)
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


def _runtime_state_path() -> Path:
    if uses_ephemeral_disk():
        return Path("/tmp") / "rank_hub_state.json"
    return _LOCAL_STATE


def _runtime_history_path() -> Path:
    if uses_ephemeral_disk():
        return Path("/tmp") / "rank_history_rows.json"
    return _ROOT / "data" / "rank_history_rows.json"


def _read_json(path: Path) -> Any:
    if not path.exists():
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def default_hub_state() -> dict[str, Any]:
    return {
        "id": _STATE_ID,
        "auto_enabled": True,
        "last_cron_at": None,
        "last_traffic_at": None,
        "last_report": None,
        "logs": [],
        "updated_at": None,
    }


def load_hub_state() -> dict[str, Any]:
    """허브 상태: auto_enabled, last_report, logs, last_cron_at."""
    if supabase_enabled():
        res = _request(
            _STATE_TABLE,
            "GET",
            query=f"id=eq.{_STATE_ID}&limit=1",
        )
        if res.get("ok") and res.get("rows"):
            row = res["rows"][0]
            return {
                "auto_enabled": bool(row.get("auto_enabled", True)),
                "last_cron_at": row.get("last_cron_at"),
                "last_traffic_at": row.get("last_traffic_at"),
                "last_report": row.get("last_report"),
                "logs": row.get("logs") or [],
                "updated_at": row.get("updated_at"),
            }

    for path in (_runtime_state_path(), _BUNDLED_STATE):
        data = _read_json(path)
        if isinstance(data, dict) and data:
            merged = default_hub_state()
            merged.update(data)
            return merged

    return default_hub_state()


def save_hub_state(state: dict[str, Any]) -> dict[str, Any]:
    payload = {
        "id": _STATE_ID,
        "auto_enabled": bool(state.get("auto_enabled", True)),
        "last_cron_at": state.get("last_cron_at"),
        "last_traffic_at": state.get("last_traffic_at"),
        "last_report": state.get("last_report"),
        "logs": (state.get("logs") or [])[-150:],
        "updated_at": datetime.now().isoformat(timespec="seconds"),
    }

    if supabase_enabled():
        res = _request(
            _STATE_TABLE,
            "POST",
            query="on_conflict=id",
            body=payload,
            prefer_service=True,
            merge=True,
        )
        if res.get("ok"):
            return {"ok": True, "backend": "supabase"}
        return {"ok": False, "backend": "supabase", "error": res.get("error")}

    paths = [_runtime_state_path()]
    if not uses_ephemeral_disk():
        paths.append(_LOCAL_STATE)
    for path in paths:
        try:
            _write_json(path, payload)
        except OSError:
            continue
    return {"ok": True, "backend": persistence_backend()}


def _row_to_dict(row: dict[str, Any]) -> dict[str, str]:
    """Supabase row → CSV-style dict."""
    if "날짜" in row:
        return {k: str(row.get(k, "")) for k in HISTORY_HEADERS}
    return {
        "날짜": str(row.get("recorded_at") or row.get("날짜") or ""),
        "키워드": str(row.get("keyword") or row.get("키워드") or ""),
        "스토어명": str(row.get("store_name") or row.get("스토어명") or ""),
        "순위": str(row.get("rank") if row.get("rank") is not None else row.get("순위", "")),
        "이전순위": str(row.get("prev_rank") if row.get("prev_rank") is not None else row.get("이전순위", "-")),
        "변동": str(row.get("change") or row.get("변동") or "-"),
        "작업유형": str(row.get("task_type") or row.get("작업유형") or ""),
        "상세": str(row.get("detail") or row.get("상세") or ""),
    }


def _dict_to_supabase_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "recorded_at": row.get("날짜") or datetime.now().strftime("%Y-%m-%d %H:%M"),
        "keyword": row.get("키워드", ""),
        "store_name": row.get("스토어명", ""),
        "rank": int(row.get("순위") or 999),
        "prev_rank": row.get("이전순위"),
        "change": row.get("변동", "-"),
        "task_type": row.get("작업유형", ""),
        "detail": row.get("상세", ""),
    }


def _load_local_history_rows() -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    csv_path = os.path.join(get_storage_dir(), "rank_history.csv")
    if os.path.exists(csv_path):
        try:
            with open(csv_path, "r", encoding="utf-8-sig") as f:
                for row in csv.DictReader(f):
                    rows.append({k: str(row.get(k, "")) for k in HISTORY_HEADERS})
        except Exception:
            pass

    runtime = _read_json(_runtime_history_path())
    if isinstance(runtime, list) and runtime:
        rows = [_row_to_dict(item) for item in runtime if isinstance(item, dict)]
    elif not rows:
        seed = _read_json(_BUNDLED_SEED)
        if isinstance(seed, list):
            rows = [_row_to_dict(item) for item in seed if isinstance(item, dict)]
    return rows


def _save_local_history_rows(rows: list[dict[str, str]]) -> None:
    trimmed = rows[-5000:]
    payload = [_row_to_dict(r) for r in trimmed]
    try:
        _write_json(_runtime_history_path(), payload)
    except OSError:
        pass
    if not uses_ephemeral_disk():
        csv_path = os.path.join(get_storage_dir(), "rank_history.csv")
        try:
            with open(csv_path, "w", encoding="utf-8-sig", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=HISTORY_HEADERS)
                writer.writeheader()
                writer.writerows(payload)
        except OSError:
            pass


def fetch_history(limit: int | None = None) -> list[dict[str, str]]:
    if supabase_enabled():
        q = "order=recorded_at.asc"
        if limit:
            q += f"&limit={max(1, min(limit, 5000))}"
        res = _request(_HISTORY_TABLE, "GET", query=q)
        if res.get("ok"):
            rows = [_row_to_dict(r) for r in (res.get("rows") or [])]
            if limit:
                return rows[-limit:]
            return rows

    rows = _load_local_history_rows()
    if limit:
        return rows[-limit:]
    return rows


def append_history_row(row: dict[str, Any]) -> dict[str, Any]:
    """한 줄 추가 (CSV 헤더 키 또는 Supabase 필드)."""
    normalized = _row_to_dict(row if "키워드" in row else {
        "날짜": row.get("recorded_at"),
        "키워드": row.get("keyword"),
        "스토어명": row.get("store_name"),
        "순위": row.get("rank"),
        "이전순위": row.get("prev_rank"),
        "변동": row.get("change"),
        "작업유형": row.get("task_type"),
        "상세": row.get("detail"),
    })

    if supabase_enabled():
        res = _request(
            _HISTORY_TABLE,
            "POST",
            body=_dict_to_supabase_row(normalized),
            prefer_service=True,
        )
        if res.get("ok"):
            return {"ok": True, "backend": "supabase"}

    rows = _load_local_history_rows()
    rows.append(normalized)
    _save_local_history_rows(rows)
    return {"ok": True, "backend": persistence_backend()}
