# -*- coding: utf-8 -*-
"""키워드·제품 프로필로 쇼츠 콘티/스토리보드 JSON 생성."""

from __future__ import annotations

import asyncio
import json
import os
import re
from pathlib import Path
from typing import Any, Callable

_ROOT = Path(__file__).resolve().parent.parent
from shorts_factory.products_loader import load_products_data
from shorts_factory.image_locale import append_locale_to_prompt, locale_rules_for_llm

PRODUCTS_PATH = _ROOT / "data" / "shorts_factory" / "products.json"
SCENE_MIN = 3
SCENE_MAX = 8

LogFn = Callable[[str], None]


def _log_default(msg: str) -> None:
    print(msg, flush=True)


def load_products() -> dict[str, dict]:
    return load_products_data()


def _parse_keywords(raw: str | list[str]) -> list[str]:
    if isinstance(raw, list):
        parts = [str(x).strip() for x in raw if str(x).strip()]
    else:
        parts = [p.strip() for p in re.split(r"[,，\n]+", raw or "") if p.strip()]
    return parts


def _build_prompt(
    product: dict,
    keywords: list[str],
    *,
    scenes: int,
    hook: str,
    topic: str,
    shopping_shorts_mode: bool = False,
    niche_id: str | None = None,
) -> str:
    kw_line = ", ".join(keywords)
    variants = ", ".join(product.get("variants") or [])
    forbidden = ", ".join(product.get("forbidden") or [])
    settings = ", ".join(product.get("settings") or [])
    locale_block = locale_rules_for_llm(product) if product.get("image_locale") else ""

    shopping_block = ""
    if shopping_shorts_mode:
        shopping_block = """
【쇼핑쇼츠 모드 — 틱톡 제품 홍보형 (신개념 쇼핑쇼츠 워크플로)】
- 세로 9:16 · 제품 홍보·전후 비교 구조 (공익·운동법·맛집 정보만 있는 영상 톤 금지)
- 장면 흐름: (앞 1~2장) 키워드 고민·후킹 → (중반) 제품 사용·효과·클로즈업 → (마지막) CTA (프로필·스마트스토어 링크, 구매는 본인 선택)
- 후킹: 시청을 멈추게 하는 한 줄 (손해·놓침·아직도 ~만?)
- 나레이션·자막은 인기 쇼핑쇼츠 톤으로 패러프레이즈 (멘트 100% 동일 복붙 금지)
- 금지: 「댓글 달면 꿀팁」·DM 유도, 허위 후기, 제품명만 연속 반복
- style 값은 "shopping_shorts" 로 설정
- youtube_description 끝에 광고·제휴 표기 문구 포함
"""

    evolution_block = ""
    try:
        from shorts_factory.youtube_learner import evolution_prompt_block

        evolution_block = evolution_prompt_block(shopping=shopping_shorts_mode)
    except Exception:
        evolution_block = ""

    niche_block = ""
    try:
        from shorts_factory.niche_templates import niche_prompt_block

        niche_block = niche_prompt_block(niche_id)
    except Exception:
        niche_block = ""

    return f"""당신은 유튜브 쇼츠·인스타 릴스용 콘티·스토리보드 작가입니다.
Google FLOW(영상 생성)에 넣을 자연스러운 실사 B-roll 쇼츠를 기획합니다.
{shopping_block}{evolution_block}{niche_block}
{locale_block}
【제품 — 이 정보만 사용】
- 라인: {product.get("full_name")}
- 변형/SKU: {variants}
- 스펙: {product.get("truth")}
- 금지 언급: {forbidden}

【입력 키워드 — 장면·FLOW 프롬프트·검색어에 반영】
{kw_line}

【주제】{topic or product.get("label")}

【후킹 한 줄】{hook or "(키워드에서 자연스럽게 도출)"}

【제품명 노출 규칙 — 매우 중요】
1. 제품명({product.get("full_name")})은 광고처럼 반복하지 말고, 장면 흐름 속에 1~2회만 자연스럽게 등장.
2. 첫 장면은 고민·상황(키워드) 위주, 중간~후반에 제품 사용·효과, 마지막 장면에 제품명 또는 라인명을 부드럽게 언급.
3. 나레이션은 구어체, 1문장 15자 내외. 자막은 더 짧게.
4. visual_desc·conti는 한국어, flow_prompt·storyboard_image_prompt는 영어 실사 지시문.
5. 스튜디오 연출·CG·로고만 나오는 장면 금지. 실제 손·제품·현장 B-roll.

【장면 수】정확히 {scenes}개 (장면당 3~5초, 총 약 {max(15, scenes * 3)}~{scenes * 5}초). scenes 배열 길이는 반드시 {scenes}와 같아야 함.

반드시 아래 JSON만 출력. 다른 설명 금지.
{{
  "topic": "주제 한 줄",
  "product_id": "{product.get("id")}",
  "style": "{product.get("style")}",
  "master_prompt": "FLOW 전체 톤 (한국어 2~3문장)",
  "flow_master_prompt_en": "English master prompt for Google Flow, photorealistic lifestyle B-roll, no studio CGI",
  "video_title": "쇼츠 제목 (이모지 1개 허용)",
  "hook_line": "첫 1초 후킹",
  "youtube_description": "업로드 설명 2문장 + 해시태그",
  "youtube_tags": ["태그10개"],
  "input_keywords": {json.dumps(keywords, ensure_ascii=False)},
  "scenes": [
    {{
      "scene_no": 1,
      "duration_sec": 4.0,
      "conti": "연출 의도 (한국어)",
      "visual_desc": "화면 설명 (한국어)",
      "background_desc": "배경·촬영 (한국어)",
      "narration": "나레이션",
      "subtitle": "자막",
      "speaker": "host",
      "product_mention": "이 장면 제품 노출 방식 (없음/손에 제품/라벨 클로즈업/대사로 언급)",
      "flow_prompt": "English video generation prompt for this shot, photorealistic, natural light",
      "storyboard_image_prompt": "English still frame for storyboard",
      "search_keyword": "one of input keywords in English"
    }}
  ]
}}"""


def _extract_json(text: str) -> dict:
    text = (text or "").strip()
    if text.startswith("{"):
        return json.loads(text)
    m = re.search(r"\{[\s\S]*\}", text)
    if not m:
        raise ValueError("LLM 응답에서 JSON을 찾을 수 없습니다.")
    return json.loads(m.group(0))


async def _generate_text(prompt: str, log: LogFn) -> str:
    from shorts_factory.ollama_text import (
        ollama_chat_once,
        ollama_ping_with_retry,
        ollama_read_timeout_for,
        resolve_ollama_models,
    )

    if await ollama_ping_with_retry(log, attempts=2):
        log("   로컬 Ollama로 콘티 생성...")
        preferred = os.environ.get("SHORTS_FACTORY_MODEL", "").strip()
        models = await resolve_ollama_models(log)
        if preferred:
            models = [preferred] + [m for m in models if m != preferred]
        # JSON 콘티 — 추론형(deepseek-r1) 제외, qwen/hermes/gemma 우선
        preferred_light = ("qwen3:4b", "hermes3:latest", "gemma2:2b", "qwen3:8b")
        light = next((m for m in models if m in preferred_light), None)
        if not light:
            light = next(
                (m for m in models if "deepseek-r1" not in m.lower() and "r1" not in m.lower()),
                models[0],
            )
        num_predict = 1500
        read_timeout = min(90, ollama_read_timeout_for(num_predict))
        max_tries = int(os.environ.get("SHORTS_OLLAMA_TRIES", "1"))
        candidates = [light] + [m for m in models if m != light][: max(0, max_tries - 1)]
        errors: list[str] = []
        for model in candidates:
            try:
                return await asyncio.wait_for(
                    ollama_chat_once(model, prompt, log, num_predict, read_timeout),
                    timeout=read_timeout + 15,
                )
            except Exception as e:
                errors.append(f"{model}: {str(e)[:80]}")
                log(f"   Ollama({model}) 실패 → 다음 모델 시도")
        raise RuntimeError("; ".join(errors) or "Ollama 콘티 생성 실패")

    api_key = os.environ.get("GEMINI_API_KEY", "").strip() or os.environ.get("GOOGLE_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("Ollama 미실행이고 GEMINI_API_KEY도 없습니다.")

    log("   Gemini로 콘티 생성...")
    try:
        from google import genai
    except ImportError:
        raise RuntimeError("pip install google-genai 후 GEMINI_API_KEY 설정")

    client = genai.Client(api_key=api_key)
    model = os.environ.get("SHORTS_FACTORY_MODEL", "gemini-2.0-flash")
    resp = client.models.generate_content(model=model, contents=prompt)
    return (resp.text or "").strip()


def _validate_plan(plan: dict, product: dict, keywords: list[str]) -> dict:
    plan.setdefault("input_keywords", keywords)
    plan.setdefault("product_id", product.get("id"))
    scenes = plan.get("scenes") or []
    for i, sc in enumerate(scenes, start=1):
        sc["scene_no"] = int(sc.get("scene_no") or i)
        if keywords:
            expected_kw = keywords[(i - 1) % len(keywords)]
            sk = str(sc.get("search_keyword") or "").strip()
            if not sk or _has_hangul(sk) or sk.lower() in {"scene", "lifestyle", "b-roll"}:
                sc["search_keyword"] = expected_kw
            sb = str(sc.get("storyboard_image_prompt") or "").strip()
            if not sb or expected_kw.lower() not in sb.lower():
                visual = str(sc.get("visual_desc") or sc.get("conti") or "")[:100]
                sc["storyboard_image_prompt"] = (
                    f"Photorealistic still frame, {expected_kw}, {visual}, "
                    "natural daylight, handheld lifestyle B-roll, 9:16 vertical, no text"
                )
            fp = str(sc.get("flow_prompt") or "").strip()
            if not fp or expected_kw.lower() not in fp.lower():
                sc["flow_prompt"] = (
                    f"Photorealistic handheld shot, {expected_kw}, "
                    f"{product.get('product_line', product.get('label'))} lifestyle scene, "
                    "natural light, 9:16 vertical, no studio CGI"
                )
            sc["storyboard_image_prompt"] = append_locale_to_prompt(
                str(sc.get("storyboard_image_prompt") or ""), product
            )
            sc["flow_prompt"] = append_locale_to_prompt(str(sc.get("flow_prompt") or ""), product, max_len=520)
        sc.setdefault("speaker", "host")
        sc.setdefault("duration_sec", 4.0)
    plan["scenes"] = scenes
    fmp = str(plan.get("flow_master_prompt_en") or "").strip()
    if fmp:
        plan["flow_master_prompt_en"] = append_locale_to_prompt(fmp, product, max_len=400)
    return plan


def _ensure_scene_count(
    plan: dict,
    product: dict,
    keywords: list[str],
    scene_n: int,
    *,
    topic: str = "",
    hook: str = "",
) -> dict:
    """요청 장면 수에 맞게 부족분을 템플릿으로 채움."""
    scenes = list(plan.get("scenes") or [])
    if len(scenes) >= scene_n:
        plan["scenes"] = scenes[:scene_n]
        return _validate_plan(plan, product, keywords)

    from shorts_factory.fallback import build_fallback_plan

    fb = build_fallback_plan(
        product, keywords, scenes=scene_n, topic=topic or plan.get("topic", ""), hook=hook or plan.get("hook_line", "")
    )
    merged = list(fb.get("scenes") or [])
    for i, sc in enumerate(scenes):
        if i < scene_n:
            merged[i] = sc
    plan["scenes"] = merged[:scene_n]
    return _validate_plan(plan, product, keywords)


def _has_hangul(text: str) -> bool:
    return bool(re.search(r"[\uac00-\ud7a3]", text or ""))


async def generate_shorts_plan(
    *,
    product_id: str,
    keywords: str | list[str],
    topic: str = "",
    hook: str = "",
    scenes: int = 4,
    use_llm: bool = True,
    use_fable_loop: bool | None = None,
    max_fable_iterations: int | None = None,
    shopping_shorts_mode: bool = False,
    niche_id: str | None = None,
    log: LogFn | None = None,
) -> dict[str, Any]:
    log = log or _log_default
    products = load_products()
    pid = (product_id or "living").strip().lower()
    product = products.get(pid)
    if not product:
        known = ", ".join(sorted(products.keys())[:12])
        raise ValueError(f"알 수 없는 product_id: {pid} (등록: {known})")

    kw = _parse_keywords(keywords)
    if not kw:
        raise ValueError("키워드 1개 이상 필요 (쉼표 구분)")

    scene_n = max(SCENE_MIN, min(SCENE_MAX, scenes))

    if niche_id:
        from shorts_factory.niche_templates import get_niche

        if not get_niche(niche_id):
            raise ValueError(f"알 수 없는 niche_id: {niche_id}")

    if not use_llm:
        from shorts_factory.fallback import build_fallback_plan

        plan = build_fallback_plan(product, kw, scenes=scene_n, topic=topic, hook=hook)
        plan = _ensure_scene_count(plan, product, kw, scene_n, topic=topic, hook=hook)
        log(f"   콘티 {len(plan.get('scenes') or [])}장 생성 완료 (빠른 모드)")
        if niche_id:
            plan["niche_id"] = niche_id
        return plan

    if use_fable_loop is None:
        use_fable_loop = os.environ.get("SHORTS_FABLE_LOOP", "1").strip().lower() not in (
            "0",
            "false",
            "no",
        )

    if use_fable_loop:
        from shorts_factory.fable_loop import generate_plan_fable_loop
        from shorts_factory.ollama_text import ollama_ping_with_retry

        if await ollama_ping_with_retry(log, attempts=2):
            try:
                plan = await generate_plan_fable_loop(
                    product=product,
                    keywords=kw,
                    scene_n=scene_n,
                    hook=hook,
                    topic=topic,
                    max_iterations=max_fable_iterations,
                    shopping_shorts_mode=shopping_shorts_mode,
                    niche_id=niche_id,
                    log=log,
                )
                plan = _ensure_scene_count(plan, product, kw, scene_n, topic=topic, hook=hook)
                loop_meta = plan.get("_fable_loop") or {}
                if shopping_shorts_mode:
                    plan["style"] = "shopping_shorts"
                    plan["shopping_shorts"] = True
                log(
                    f"   conti {len(plan.get('scenes') or [])} scenes "
                    f"(Fable local {loop_meta.get('iterations', '?')} rounds, "
                    f"{loop_meta.get('final_score', '?')} pts)"
                )
                if niche_id:
                    plan["niche_id"] = niche_id
                return plan
            except Exception as e:
                log(f"   Fable loop fail, fallback to single-shot: {e}")
        else:
            log("   Ollama offline, skip Fable loop, single-shot mode")

    try:
        prompt = _build_prompt(
            product,
            kw,
            scenes=scene_n,
            hook=hook,
            topic=topic,
            shopping_shorts_mode=shopping_shorts_mode,
            niche_id=niche_id,
        )
        raw = await _generate_text(prompt, log)
        plan = _validate_plan(_extract_json(raw), product, kw)
        if shopping_shorts_mode:
            plan["style"] = "shopping_shorts"
            plan["shopping_shorts"] = True
        plan = _ensure_scene_count(plan, product, kw, scene_n, topic=topic, hook=hook)
        log(f"   conti {len(plan.get('scenes') or [])} scenes (LLM single-shot)")
    except Exception as e:
        log(f"   LLM 실패 → 템플릿 폴백: {e}")
        from shorts_factory.fallback import build_fallback_plan

        plan = build_fallback_plan(
            product, kw, scenes=scene_n, topic=topic, hook=hook
        )
        plan = _ensure_scene_count(plan, product, kw, scene_n, topic=topic, hook=hook)
        log(f"   콘티 {len(plan.get('scenes') or [])}장 생성 완료 (폴백)")

    if niche_id:
        plan["niche_id"] = niche_id

    return plan
