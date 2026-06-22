# -*- coding: utf-8 -*-
"""허브 셀프힐링 — 오류 감지 시 config·SEO·상태·백그라운드 자동 복구."""

from __future__ import annotations

import json
import os
import time
import traceback
from datetime import datetime
from functools import wraps
from pathlib import Path
from typing import Any, Callable

Logger = Callable[[str], None] | None
_Root = Path(__file__).resolve().parent
_DEFAULTS = _Root / "config.defaults.json"

_supabase_paused_until: float = 0.0
_restart_services_fn: Callable[[], None] | None = None


def register_restart_services(fn: Callable[[], None]) -> None:
    global _restart_services_fn
    _restart_services_fn = fn


def supabase_paused() -> bool:
    return time.time() < _supabase_paused_until


def pause_supabase(minutes: int = 30, *, logger: Logger = None) -> None:
    global _supabase_paused_until
    _supabase_paused_until = time.time() + max(5, minutes) * 60
    if logger:
        logger(f"🩹 Supabase 일시 중지 ({minutes}분) — 로컬 폴백")


def classify_error(exc: BaseException, endpoint: str = "") -> str:
    msg = (str(exc) or repr(exc) or exc.__class__.__name__).lower()
    ep = (endpoint or "").lower()
    if any(x in msg for x in ("getaddrinfo", "urlopen error", "network_unreachable", "connection refused", "timed out")):
        return "supabase_network"
    if "429" in msg or "403" in msg or "차단" in msg:
        return "naver_blocked"
    if "json" in msg or "decode" in msg or "config" in msg:
        return "config_invalid"
    if "keyword" in msg and ep:
        return "keywords_missing"
    if ep in ("/api/status", "/api/history", "/api/config"):
        return "api_degraded"
    return "generic"


def _heal_supabase_network(logger: Logger) -> dict[str, Any]:
    pause_supabase(30, logger=logger)
    try:
        from rank_persistence import load_hub_state, save_hub_state

        state = load_hub_state()
        state["supabase_paused_until"] = datetime.fromtimestamp(_supabase_paused_until).isoformat(timespec="seconds")
        state["persistence_fallback"] = "local"
        save_hub_state(state)
    except Exception:
        pass
    return {"action": "supabase_network", "retry": True}


def _heal_seo_meta(logger: Logger) -> dict[str, Any]:
    from rank_tracker import load_config
    from seo_auto_fix import ensure_product_seo

    fixed = 0
    config = load_config()
    for product in config.get("products") or []:
        if not isinstance(product, dict):
            continue
        if len((product.get("meta_description") or "")) >= 50:
            continue
        pid = str(product.get("id") or "").strip()
        if not pid:
            continue
        r = ensure_product_seo(load_config(), pid, logger=logger)
        if r.get("ok"):
            fixed += 1
    return {"action": "seo_meta", "fixed": fixed, "retry": fixed > 0}


def _heal_config_defaults(logger: Logger) -> dict[str, Any]:
    from rank_tracker import load_config, save_config

    if not _DEFAULTS.is_file():
        return {"action": "config_defaults", "retry": False}
    try:
        defaults = json.loads(_DEFAULTS.read_text(encoding="utf-8"))
        cfg = load_config()
        for key in ("store_name", "brand", "products", "keywords", "priority_keywords", "product_urls", "blog_urls"):
            if not cfg.get(key) and defaults.get(key):
                cfg[key] = defaults[key]
        save_config(cfg)
        if logger:
            logger("🩹 config.json 빈 필드 — defaults 병합")
        return {"action": "config_defaults", "retry": True}
    except Exception as exc:
        return {"action": "config_defaults", "error": str(exc), "retry": False}


def _heal_sync_keywords(logger: Logger) -> dict[str, Any]:
    try:
        from hub_accounts import sync_accounts_keywords_to_config

        sync_accounts_keywords_to_config()
        if logger:
            logger("🩹 accounts → config 키워드 동기화")
        return {"action": "sync_keywords", "retry": True}
    except Exception as exc:
        return {"action": "sync_keywords", "error": str(exc), "retry": False}


def _heal_restart_background(logger: Logger) -> dict[str, Any]:
    if _restart_services_fn is None:
        return {"action": "restart_background", "retry": False}
    try:
        _restart_services_fn()
        if logger:
            logger("🩹 백그라운드 순위·트래픽 루프 재기동")
        return {"action": "restart_background", "retry": True}
    except Exception as exc:
        return {"action": "restart_background", "error": str(exc), "retry": False}


def heal_for_error(
    exc: BaseException,
    endpoint: str = "",
    *,
    logger: Logger = None,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """오류 유형별 1회 복구 시도. retry=True면 호출자가 재시도 가능."""
    kind = classify_error(exc, endpoint)
    if logger:
        logger(f"🩹 셀프힐링 ({kind}): {exc.__class__.__name__} @ {endpoint or '?'}")

    actions: list[dict[str, Any]] = []
    if kind == "supabase_network":
        actions.append(_heal_supabase_network(logger))
    elif kind == "naver_blocked":
        actions.append(_heal_seo_meta(logger))
    elif kind == "config_invalid":
        actions.append(_heal_config_defaults(logger))
        actions.append(_heal_sync_keywords(logger))
    elif kind == "keywords_missing":
        actions.append(_heal_sync_keywords(logger))
    elif kind == "api_degraded":
        actions.append(_heal_supabase_network(logger))
        actions.append(_heal_config_defaults(logger))

    retry = any(a.get("retry") for a in actions)
    result = {
        "healed": bool(actions),
        "kind": kind,
        "actions": actions,
        "retry": retry,
        "at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    _record_heal(result, logger=logger)
    return result


def run_proactive_heal(*, logger: Logger = None) -> dict[str, Any]:
    """주기적 예방 점검 — 메타·키워드·백그라운드."""
    actions: list[dict[str, Any]] = []

    seo = _heal_seo_meta(logger)
    if seo.get("fixed"):
        actions.append(seo)

    config = None
    try:
        from rank_tracker import load_config

        config = load_config()
    except Exception:
        pass

    if config is not None:
        if not config.get("keywords"):
            actions.append(_heal_sync_keywords(logger))
        if not config.get("products"):
            actions.append(_heal_config_defaults(logger))

    actions.append(_heal_restart_background(logger))

    result = {
        "healed": any(a.get("retry") or a.get("fixed") for a in actions),
        "kind": "proactive",
        "actions": actions,
        "at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    if result["healed"]:
        _record_heal(result, logger=logger)
    return result


def _record_heal(result: dict[str, Any], *, logger: Logger = None) -> None:
    try:
        from rank_persistence import load_hub_state, save_hub_state

        state = load_hub_state()
        log = list(state.get("self_heal_log") or [])[-19:]
        log.append(result)
        state["self_heal_log"] = log
        state["self_heal_last"] = result
        save_hub_state(state)
    except Exception:
        pass


def self_healing_endpoint(endpoint: str):
    """Flask 라우트 — 예외 시 1회 셀프힐링 후 재시도."""

    def deco(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            try:
                return fn(*args, **kwargs)
            except Exception as exc:
                heal = heal_for_error(exc, endpoint, logger=kwargs.get("_heal_logger"))
                if heal.get("retry"):
                    try:
                        return fn(*args, **kwargs)
                    except Exception as exc2:
                        raise exc2
                raise exc

        return wrapper

    return deco


def start_self_heal_loop(*, interval_sec: int = 300, logger: Logger = None) -> None:
    import threading

    def _loop():
        while True:
            time.sleep(max(60, interval_sec))
            try:
                run_proactive_heal(logger=logger)
            except Exception:
                if logger:
                    logger(f"🩹 proactive heal skip: {traceback.format_exc()[-200:]}")

    threading.Thread(target=_loop, daemon=True, name="hub-self-heal").start()
