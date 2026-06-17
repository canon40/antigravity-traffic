# -*- coding: utf-8 -*-
"""자율 루프 — 블로그 실패 → 진화 → 재발행 / 예약 키워드 발행."""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any, Callable

_ROOT = Path(__file__).resolve().parent.parent


def _resolve_guideline(path: str) -> str:
    p = (path or "").strip()
    if not p:
        return ""
    candidate = _ROOT / p if not Path(p).is_absolute() else Path(p)
    if candidate.is_file():
        return candidate.read_text(encoding="utf-8")
    return p


def run_blog_autonomous_phase(
    cfg: dict[str, Any],
    *,
    force: bool = False,
    on_log: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    from integrations.blog_evolution import (
        plan_autonomous_blog_action,
        run_blog_evolution_fix,
        save_blog_retry_state,
        load_blog_retry_state,
    )

    blog_cfg = cfg.get("blog_auto") if isinstance(cfg.get("blog_auto"), dict) else {}
    if not _blog_enabled(cfg):
        return {"ok": True, "skipped": "blog_auto disabled"}

    plan = plan_autonomous_blog_action(cfg)
    action = plan.get("action")
    if action == "skip" and not force:
        return {"ok": True, "skipped": plan.get("reason", "skip")}

    if action == "skip" and force:
        plan = plan_autonomous_blog_action({**cfg, "blog_auto": {**blog_cfg, "retry_on_failure": False}})
        if plan.get("action") == "skip":
            kw = (blog_cfg.get("default_keyword") or "").strip()
            if not kw:
                return {"ok": True, "skipped": "no_keyword"}
            plan = {"action": "new", "keyword": kw, "force": True, "publish": True, "guideline": ""}

    log = on_log or print
    os.chdir(_ROOT)
    if str(_ROOT) not in __import__("sys").path:
        __import__("sys").path.insert(0, str(_ROOT))

    result: dict[str, Any] = {"plan": plan, "action": plan.get("action")}

    if plan.get("action") == "retry":
        kw = plan.get("keyword") or ""
        keys = list(plan.get("platform_keys") or [])
        log(f"[자율 블로그] 재시도 #{plan.get('retry_count')} — {kw} ({', '.join(keys)})")

        if plan.get("evolve"):
            ev = run_blog_evolution_fix(lesson=str(plan.get("lesson") or ""), keyword=kw)
            result["evolution"] = ev
            log(f"[자율 블로그] 진화 반영 ok={ev.get('ok')}")

        from integrations.blog_auto_pipeline import run_blog_retry_publish

        r = run_blog_retry_publish(platform_keys=keys, on_status=log)
        result["blog"] = r
        result["ok"] = bool(r.get("ok"))

        st = load_blog_retry_state()
        st["retry_count"] = int(plan.get("retry_count") or 1)
        st["last_attempt"] = time.time()
        if r.get("ok"):
            st["retry_count"] = 0
        save_blog_retry_state(st)
        return result

    if plan.get("action") == "new":
        kw = str(plan.get("keyword") or "").strip()
        if not kw:
            return {"ok": True, "skipped": "empty keyword"}

        if plan.get("force"):
            os.environ["JARVIS_BLOG_SKIP_DUP"] = "1"

        g_path = (plan.get("guideline") or blog_cfg.get("guideline") or "").strip()
        g_text = _resolve_guideline(g_path) if g_path else ""

        log(f"[자율 블로그] 새 글 — {kw}")
        from integrations.blog_auto_pipeline import run_blog_auto

        platforms = plan.get("platforms")
        if isinstance(platforms, str):
            platforms = [x.strip() for x in platforms.split(",") if x.strip()]

        r = run_blog_auto(
            kw,
            platforms=platforms if isinstance(platforms, list) else None,
            publish=bool(plan.get("publish", True)),
            guideline=g_text,
            on_status=log,
        )
        result["blog"] = r
        result["ok"] = bool(r.get("ok"))

        from integrations.blog_evolution import load_blog_retry_state, save_blog_retry_state

        st = load_blog_retry_state()
        st["last_new_post"] = time.time()
        st["queue_index"] = int(plan.get("queue_index") or st.get("queue_index") or 0)
        if not r.get("ok"):
            from integrations.blog_evolution import failed_publish_keys

            st["retry_count"] = 0
            st["failed_keys"] = failed_publish_keys(r)
        save_blog_retry_state(st)
        return result

    return {"ok": True, "skipped": plan.get("reason", "unknown")}


def _blog_enabled(cfg: dict[str, Any]) -> bool:
    blog_cfg = cfg.get("blog_auto") if isinstance(cfg.get("blog_auto"), dict) else {}
    return bool(blog_cfg.get("enabled", cfg.get("blog_auto_enabled", False)))


def format_blog_autonomous_status() -> str:
    from integrations.blog_evolution import (
        load_blog_retry_state,
        load_last_blog_report,
        plan_autonomous_blog_action,
    )
    from integrations.jarvis_autonomous import load_autonomous_config

    cfg = load_autonomous_config()
    plan = plan_autonomous_blog_action(cfg)
    last = load_last_blog_report()
    st = load_blog_retry_state()
    lines = [
        "=== 자율 블로그 (실패→진화→재시도) ===",
        f"enabled: {_blog_enabled(cfg)}",
        f"다음 작업: {plan.get('action')} ({plan.get('reason', plan.get('keyword', ''))})",
        f"재시도 횟수: {st.get('retry_count', 0)}",
    ]
    if last:
        lines.append(f"마지막 키워드: {last.get('keyword')} ok={last.get('ok')}")
    return "\n".join(lines)
