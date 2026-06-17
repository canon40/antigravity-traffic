# -*- coding: utf-8 -*-
"""블로그 발행 실패·성공 → evolution_memory + 다음 글쓰기 지침."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

_LAST = Path.home() / ".jarvis" / "evolution" / "blog_last_lessons.json"
_RETRY_STATE = Path.home() / ".jarvis" / "evolution" / "blog_retry_state.json"
_LAST_REPORT = Path.home() / ".jarvis" / "learning" / "last_blog_auto.json"


def failed_publish_keys(report: dict[str, Any]) -> list[str]:
    pub = (report.get("steps") or {}).get("publish") or {}
    return [k for k, v in pub.items() if isinstance(v, dict) and not v.get("ok")]


def load_last_blog_report() -> dict[str, Any] | None:
    if not _LAST_REPORT.is_file():
        return None
    try:
        return json.loads(_LAST_REPORT.read_text(encoding="utf-8"))
    except Exception:
        return None


def load_blog_retry_state() -> dict[str, Any]:
    if _RETRY_STATE.is_file():
        try:
            return json.loads(_RETRY_STATE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def save_blog_retry_state(state: dict[str, Any]) -> None:
    _RETRY_STATE.parent.mkdir(parents=True, exist_ok=True)
    _RETRY_STATE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def run_blog_evolution_fix(*, lesson: str = "", keyword: str = "") -> dict[str, Any]:
    """발행 실패 교훈 → 짧은 진화 사이클(코드·프롬프트 반영 시도)."""
    topic = (
        "블로그 자동 발행 실패 수정: 네이버 태그30·본문·로그인·티스토리·Blogger. "
        f"키워드={keyword[:60]}. 교훈: {lesson[:400]}"
    )
    try:
        from agent.jarvis_evolution_engine import run_evolution_cycle

        return run_evolution_cycle(topic, speak=None, max_rounds=1)
    except Exception as e:
        return {"ok": False, "error": str(e)}


def plan_autonomous_blog_action(cfg: dict[str, Any]) -> dict[str, Any]:
    """
    자율 루프용 다음 블로그 작업.
    action: skip | retry | new
    """
    blog_cfg = cfg.get("blog_auto") if isinstance(cfg.get("blog_auto"), dict) else {}
    if not blog_cfg.get("enabled", cfg.get("blog_auto_enabled", False)):
        return {"action": "skip", "reason": "blog_auto disabled"}

    retry_on = bool(blog_cfg.get("retry_on_failure", True))
    max_retries = int(blog_cfg.get("max_retries", 2))
    cooldown_h = float(blog_cfg.get("retry_cooldown_hours", 3))
    interval_h = float(
        blog_cfg.get("interval_hours") or cfg.get("blog_auto_interval_hours") or 24
    )

    last = load_last_blog_report()
    rstate = load_blog_retry_state()
    failed = failed_publish_keys(last) if last else []
    kw_last = str((last or {}).get("keyword") or rstate.get("keyword") or "")

    if retry_on and failed and kw_last:
        count = int(rstate.get("retry_count") or 0)
        last_at = float(rstate.get("last_attempt") or 0)
        if count < max_retries and (time.time() - last_at) >= cooldown_h * 3600:
            lesson = ""
            if _LAST.is_file():
                try:
                    lesson = json.loads(_LAST.read_text(encoding="utf-8")).get("lesson") or ""
                except Exception:
                    pass
            return {
                "action": "retry",
                "keyword": kw_last,
                "platform_keys": failed,
                "retry_count": count + 1,
                "lesson": lesson,
                "evolve": bool(blog_cfg.get("evolve_before_retry", True)),
            }
        if count >= max_retries:
            return {"action": "skip", "reason": "max_retries_reached", "failed": failed}

    queue = list(blog_cfg.get("keyword_queue") or [])
    default_kw = (blog_cfg.get("default_keyword") or "").strip()
    idx = int(rstate.get("queue_index") or 0)
    keyword = ""
    if queue:
        keyword = str(queue[idx % len(queue)]).strip()
    elif default_kw:
        keyword = default_kw

    if not keyword:
        return {"action": "skip", "reason": "no_keyword"}

    last_new = float(rstate.get("last_new_post") or 0)
    if (time.time() - last_new) < interval_h * 3600:
        return {"action": "skip", "reason": "new_post_cooldown"}

    return {
        "action": "new",
        "keyword": keyword,
        "queue_index": (idx + 1) if queue else idx,
        "guideline": (blog_cfg.get("guideline") or "").strip(),
        "force": bool(blog_cfg.get("force", True)),
        "publish": bool(blog_cfg.get("publish", True)),
        "platforms": blog_cfg.get("platforms"),
    }


def record_blog_run(report: dict[str, Any]) -> None:
    """run_blog_auto 결과 전체를 진화 메모리에 기록."""
    from agent.evolution_memory import record_experience, record_success_path

    kw = str(report.get("keyword") or "")
    pub = (report.get("steps") or {}).get("publish") or {}
    ok_all = bool(report.get("ok"))
    failures: list[str] = []
    successes: list[str] = []

    for key, res in pub.items():
        if not isinstance(res, dict):
            continue
        if res.get("ok"):
            successes.append(key)
        else:
            err = res.get("error") or ""
            tags = res.get("tags_filled", 0)
            body = res.get("body_filled", False)
            failures.append(
                f"{key}: body={body} tags={tags} err={(err or '발행미완')[:120]}"
            )

    lesson_parts: list[str] = []
    if failures:
        lesson_parts.append("실패 플랫폼: " + "; ".join(failures))
    if any("태그" in f or "tags=0" in f for f in failures):
        lesson_parts.append("네이버: 발행 패널 연 뒤 해시태그 입력 후 최종 발행")
    if any("hymini11" in f or "login" in f.lower() for f in failures):
        lesson_parts.append("네이버2: 별도 브라우저 프로필 로그인 필요")
    if any("body=False" in f for f in failures):
        lesson_parts.append("본문: insertText·이미지 후 본문 순서 유지")

    lesson = " | ".join(lesson_parts) if lesson_parts else "전 플랫폼 발행 OK"
    record_experience(
        task=f"blog_auto:{kw[:80]}",
        success=ok_all,
        problem="; ".join(failures)[:900] if failures else "",
        solution="; ".join(successes)[:400] if successes else str(report.get("ok")),
        lesson=lesson[:500],
        agents_used=["blog_auto"],
        project_path=str((report.get("steps") or {}).get("media", {}).get("output_dir", "")),
    )

    if ok_all and successes:
        record_success_path(
            task=f"blog:{kw[:100]}",
            steps=["글생성", "이미지", "발행"] + successes,
            tools=["blog_auto"],
            artifact=kw,
            planner="blog_auto",
        )

    _LAST.parent.mkdir(parents=True, exist_ok=True)
    _LAST.write_text(
        json.dumps(
            {
                "ts": time.time(),
                "keyword": kw,
                "ok": ok_all,
                "failures": failures,
                "successes": successes,
                "lesson": lesson,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    rstate = load_blog_retry_state()
    rstate["keyword"] = kw
    rstate["last_lesson"] = lesson
    rstate["last_attempt"] = time.time()
    if ok_all:
        rstate["retry_count"] = 0
        rstate["failed_keys"] = []
    else:
        rstate["failed_keys"] = [f.split(":")[0] if ":" in f else f for f in failures]
        rstate.setdefault("retry_count", 0)
    save_blog_retry_state(rstate)


def blog_evolution_context_for_prompt(keyword: str = "") -> str:
    """다음 blog_auto 글 생성 시 Gemini 프롬프트에 붙일 블록."""
    from agent.evolution_memory import format_context_for_prompt, search_relevant

    parts: list[str] = []
    q = f"blog_auto {keyword}".strip()
    ctx = format_context_for_prompt(q or "blog_auto naver tistory")
    if ctx:
        parts.append(ctx)

    hits = search_relevant("blog naver tistory 발행 태그 본문", limit=8)
    blog_hits = [
        h
        for h in hits
        if "blog" in str(h.get("task", "")).lower()
        or "naver" in str(h.get("lesson", "")).lower()
    ]
    if blog_hits:
        parts.append("[최근 블로그 발행 교훈 — 반드시 참고]")
        for h in blog_hits[:5]:
            parts.append(
                f"- {'성공' if h.get('success') else '실패'}: {h.get('lesson', '')[:200]} "
                f"| {h.get('problem', '')[:150]}"
            )

    if _LAST.is_file():
        try:
            last = json.loads(_LAST.read_text(encoding="utf-8"))
            if last.get("lesson"):
                parts.append(f"[직전 실행] {last.get('lesson')}")
        except Exception:
            pass

    if not parts:
        return ""
    return "\n".join(parts) + "\n\n"
