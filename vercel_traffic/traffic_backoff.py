"""트래픽 429·403 시 간격 백오프 — hub state에 저장."""

from __future__ import annotations

import os
from typing import Any

BACKOFF_MULTIPLIER = 2
MAX_INTERVAL_SEC = 7200
MIN_INTERVAL_SEC = 300


def _is_cloud() -> bool:
    try:
        from hub_runtime import is_cloud_hub

        return is_cloud_hub()
    except ImportError:
        return bool(os.environ.get("CLOUDTYPE") or os.environ.get("VERCEL"))


def base_interval_sec() -> int:
    default = "3600" if _is_cloud() else "1200"
    return max(MIN_INTERVAL_SEC, int(os.environ.get("TRAFFIC_INTERVAL_SEC", default)))


def effective_interval_sec(state: dict[str, Any] | None) -> int:
    state = state or {}
    stored = int(state.get("traffic_interval_sec") or 0)
    base = base_interval_sec()
    if stored < base:
        return base
    return min(stored, MAX_INTERVAL_SEC)


def format_backoff_note(status_code: int | None) -> str:
    if status_code in (403, 418, 429):
        return " — 네이버 rate limit, 다음 간격 자동 연장"
    return ""


def apply_traffic_result(state: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
    """hub state에 traffic_interval_sec·backoff_streak 갱신."""
    status = int(result.get("status_code") or 0)
    current = effective_interval_sec(state)
    base = base_interval_sec()

    if status in (403, 418, 429) or not result.get("ok"):
        if status in (403, 418, 429):
            retry_after = result.get("retry_after_sec")
            if retry_after:
                new = min(max(int(retry_after), current), MAX_INTERVAL_SEC)
            else:
                new = min(max(current, base) * BACKOFF_MULTIPLIER, MAX_INTERVAL_SEC)
            state["traffic_interval_sec"] = new
            state["traffic_backoff_streak"] = int(state.get("traffic_backoff_streak") or 0) + 1
            state["traffic_last_error"] = status
    elif result.get("ok"):
        if current > base:
            state["traffic_interval_sec"] = max(base, current // 2)
        else:
            state.pop("traffic_interval_sec", None)
        state["traffic_backoff_streak"] = 0
        state.pop("traffic_last_error", None)

    return state
