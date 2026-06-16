# -*- coding: utf-8 -*-
"""Fable5 스타일 로컬 루프 — Ollama(무료) + 루브릭 피드백 + 멈춤 조건.

Anthropic Claude Fable 5 API는 유료 클라우드 전용입니다.
이 모듈은 Notion 실습 가이드의 루프 3요소(목적지·피드백·멈춤)를
로컬 Ollama로 재현합니다.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
from pathlib import Path
from typing import Any, Callable

from shorts_factory.generator import _build_prompt, _extract_json, _validate_plan

_ROOT = Path(__file__).resolve().parent.parent
RUBRIC_PATH = _ROOT / "data" / "shorts_factory" / "fable_rubric.json"

LogFn = Callable[[str], None]


def _log_default(msg: str) -> None:
    print(msg, flush=True)


def load_rubric() -> dict:
    if RUBRIC_PATH.is_file():
        return json.loads(RUBRIC_PATH.read_text(encoding="utf-8"))
    return {
        "pass_score": 80,
        "max_iterations": 4,
        "criteria": [],
    }


def _has_hangul(text: str) -> bool:
    return bool(re.search(r"[\uac00-\ud7a3]", text or ""))


def _collect_text(plan: dict) -> str:
    parts: list[str] = []
    for key in ("hook_line", "video_title", "master_prompt"):
        parts.append(str(plan.get(key) or ""))
    for sc in plan.get("scenes") or []:
        for key in ("conti", "narration", "subtitle", "visual_desc", "product_mention"):
            parts.append(str(sc.get(key) or ""))
    return "\n".join(parts).lower()


def score_plan(
    plan: dict,
    product: dict,
    keywords: list[str],
    *,
    scene_n: int,
) -> dict[str, Any]:
    """루브릭 채점 — 결정론적(무료). 0~100점 + 항목별 이슈."""
    rubric = load_rubric()
    issues: list[str] = []
    scores: dict[str, int] = {}
    scenes = plan.get("scenes") or []
    forbidden = [str(x).lower() for x in (product.get("forbidden") or []) if str(x).strip()]
    blob = _collect_text(plan)

    # scene_count
    if len(scenes) >= scene_n:
        scores["scene_count"] = 10
    else:
        scores["scene_count"] = max(0, int(len(scenes) / max(scene_n, 1) * 10))
        issues.append(f"장면 수 부족: {len(scenes)}/{scene_n}")

    # hook
    hook = str(plan.get("hook_line") or "").strip()
    if len(hook) >= 8 and not hook.startswith("이 제품"):
        scores["hook"] = 10
    elif hook:
        scores["hook"] = 6
        issues.append("후킹이 약함 — 질문/장면으로 시작하는 8자+ 문장 필요")
    else:
        scores["hook"] = 0
        issues.append("hook_line 없음")

    # keywords
    kw_ok = 0
    for i, sc in enumerate(scenes):
        expected = keywords[i % len(keywords)] if keywords else ""
        sk = str(sc.get("search_keyword") or "").lower()
        fp = str(sc.get("flow_prompt") or "").lower()
        if expected and (expected.lower() in sk or expected.lower() in fp):
            kw_ok += 1
    if scenes and keywords:
        ratio = kw_ok / len(scenes)
        scores["keywords"] = int(ratio * 10)
        if ratio < 0.8:
            issues.append(f"키워드 미반영 장면 {len(scenes) - kw_ok}개")
    else:
        scores["keywords"] = 5

    # forbidden
    hits = [w for w in forbidden if w and w in blob]
    if not hits:
        scores["forbidden"] = 10
    else:
        scores["forbidden"] = max(0, 10 - len(hits) * 3)
        issues.append(f"금지 언급: {', '.join(hits[:3])}")

    # required fields
    field_miss = 0
    for sc in scenes:
        for key in ("conti", "narration", "subtitle", "flow_prompt"):
            if not str(sc.get(key) or "").strip():
                field_miss += 1
    if not field_miss:
        scores["fields"] = 10
    else:
        scores["fields"] = max(0, 10 - min(field_miss, 5) * 2)
        issues.append(f"필수 필드 누락 {field_miss}건")

    # flow english
    bad_flow = 0
    for sc in scenes:
        fp = str(sc.get("flow_prompt") or "").strip()
        if not fp or _has_hangul(fp) or len(fp) < 20:
            bad_flow += 1
    if not bad_flow:
        scores["flow_english"] = 10
    else:
        scores["flow_english"] = max(0, 10 - bad_flow * 2)
        issues.append(f"flow_prompt 영어/길이 부족 {bad_flow}장")

    weights = {c["id"]: c.get("weight", 10) for c in rubric.get("criteria") or []}
    total_w = sum(weights.get(k, 10) for k in scores) or 1
    weighted = sum(scores[k] * weights.get(k, 10) for k in scores) / total_w * 10
    total = int(round(weighted))

    return {
        "total": total,
        "pass_score": int(rubric.get("pass_score", 80)),
        "scores": scores,
        "issues": issues,
        "passed": (
            total >= int(rubric.get("pass_score", 80))
            and not hits
            and len(scenes) >= scene_n
        ),
    }


def _build_fix_prompt(
    base_prompt: str,
    plan: dict,
    score: dict[str, Any],
    *,
    iteration: int,
) -> str:
    issues = score.get("issues") or ["품질 미달"]
    plan_snip = json.dumps(plan, ensure_ascii=False, indent=2)
    if len(plan_snip) > 8000:
        plan_snip = plan_snip[:7500] + "\n..."

    return f"""{base_prompt}

【Fable 루프 — 수정 회차 {iteration}】
아래 초안 JSON의 문제를 고쳐 **완전한 JSON 하나만** 다시 출력하세요.

【루브릭 점수】총 {score.get('total')} / 100 (통과 {score.get('pass_score')}+)
항목: {json.dumps(score.get('scores'), ensure_ascii=False)}

【수정할 문제】
{chr(10).join('- ' + x for x in issues)}

【현재 초안】
{plan_snip}

수정 규칙: JSON만 출력. 장면 수·키워드·금지어·영어 flow_prompt를 반드시 지키세요."""


async def generate_plan_fable_loop(
    *,
    product: dict,
    keywords: list[str],
    scene_n: int,
    hook: str,
    topic: str,
    log: LogFn | None = None,
    max_iterations: int | None = None,
    shopping_shorts_mode: bool = False,
    niche_id: str | None = None,
) -> dict[str, Any]:
    """Ollama로 콘티 생성 + 루브릭 피드백 루프 (로컬 무료)."""
    from shorts_factory.ollama_text import (
        ollama_chat_once,
        ollama_ping_with_retry,
        ollama_read_timeout_for,
        resolve_ollama_models,
    )

    log = log or _log_default
    rubric = load_rubric()
    max_iters = max_iterations or int(os.environ.get("SHORTS_FABLE_MAX_ITERS", rubric.get("max_iterations", 4)))

    if not await ollama_ping_with_retry(log, attempts=2):
        raise RuntimeError(
            "로컬 Fable 루프는 Ollama가 필요합니다. "
            "https://ollama.com 에서 설치 후 `ollama serve` 및 `ollama pull qwen3:4b`"
        )

    log("   [Fable local] Ollama loop start (free, replaces paid Fable5 API)")
    models = await resolve_ollama_models(log)
    preferred = os.environ.get("SHORTS_FACTORY_MODEL", "").strip()
    if preferred:
        models = [preferred] + [m for m in models if m != preferred]
    model = next(
        (m for m in models if "deepseek-r1" not in m.lower()),
        models[0],
    )

    base_prompt = _build_prompt(
        product,
        keywords,
        scenes=scene_n,
        hook=hook,
        topic=topic,
        shopping_shorts_mode=shopping_shorts_mode,
        niche_id=niche_id,
    )
    num_predict = int(os.environ.get("SHORTS_FABLE_NUM_PREDICT", "1200"))
    read_timeout = min(180, ollama_read_timeout_for(num_predict))

    plan: dict[str, Any] | None = None
    history: list[dict[str, Any]] = []
    prompt = base_prompt

    for iteration in range(1, max_iters + 1):
        log(f"   [Fable local] round {iteration}/{max_iters} generating...")
        raw = await asyncio.wait_for(
            ollama_chat_once(model, prompt, log, num_predict, read_timeout),
            timeout=read_timeout + 20,
        )
        try:
            plan = _validate_plan(_extract_json(raw), product, keywords)
        except Exception as e:
            history.append({"iteration": iteration, "error": str(e)[:120]})
            log(f"   [Fable local] JSON parse fail, retry ({e})")
            prompt = base_prompt + f"\n\n이전 응답이 잘못됐습니다: {e}. 유효한 JSON만 출력."
            continue

        score = score_plan(plan, product, keywords, scene_n=scene_n)
        history.append({"iteration": iteration, "total": score["total"], "scores": score["scores"]})
        log(
            f"   [Fable local] round {iteration} score {score['total']}/100 "
            f"({'pass' if score['passed'] else 'fail'})"
        )

        if score["passed"]:
            plan["_fable_loop"] = {
                "engine": "local_ollama",
                "model": model,
                "iterations": iteration,
                "final_score": score["total"],
                "history": history,
                "passed": True,
            }
            log(f"   [Fable local] goal reached at round {iteration}")
            return plan

        if iteration >= max_iters:
            break

        prompt = _build_fix_prompt(base_prompt, plan, score, iteration=iteration + 1)

    assert plan is not None
    final = score_plan(plan, product, keywords, scene_n=scene_n)
    plan["_fable_loop"] = {
        "engine": "local_ollama",
        "model": model,
        "iterations": max_iters,
        "final_score": final["total"],
        "history": history,
        "passed": final["passed"],
        "issues": final.get("issues"),
    }
    log(f"   [Fable local] max rounds reached, score {final['total']}/100")
    return plan


async def check_local_fable_ready(log: LogFn | None = None) -> dict[str, Any]:
    """UI/상태 API용 — Ollama 가용 여부."""
    from shorts_factory.ollama_text import ollama_ping, _list_installed_models

    log = log or _log_default
    ok = await ollama_ping()
    models: list[str] = []
    if ok:
        installed = await _list_installed_models()
        models = sorted(installed)[:8]
    return {
        "available": ok,
        "engine": "local_ollama",
        "note": "Claude Fable 5 API는 유료. 로컬 루프는 Ollama로 무료 동작.",
        "models": models,
        "url": os.environ.get("BLOG_OLLAMA_URL", "http://localhost:11434"),
    }


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="로컬 Fable 루프 콘티 테스트")
    parser.add_argument("--product", default="bike")
    parser.add_argument("--keywords", default="motorcycle wash, water beading tank")
    parser.add_argument("--scenes", type=int, default=4)
    args = parser.parse_args()

    from shorts_factory.generator import load_products, _parse_keywords

    products = load_products()
    product = products.get(args.product)
    if not product:
        print(f"unknown product: {args.product}")
        return 1

    kw = _parse_keywords(args.keywords)

    async def _run() -> dict:
        ready = await check_local_fable_ready()
        print(json.dumps(ready, ensure_ascii=False, indent=2))
        if not ready["available"]:
            return {}
        return await generate_plan_fable_loop(
            product=product,
            keywords=kw,
            scene_n=args.scenes,
            hook="",
            topic="",
        )

    plan = asyncio.run(_run())
    if not plan:
        return 1
    print(json.dumps(plan.get("_fable_loop"), ensure_ascii=False, indent=2))
    print(f"scenes: {len(plan.get('scenes') or [])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
