# -*- coding: utf-8 -*-
"""LLM 없이 키워드·제품 프로필로 콘티 JSON 생성 (폴백)."""

from __future__ import annotations

from typing import Any

from shorts_factory.image_locale import append_locale_to_prompt


def build_fallback_plan(
    product: dict,
    keywords: list[str],
    *,
    scenes: int = 4,
    topic: str = "",
    hook: str = "",
) -> dict[str, Any]:
    name = product.get("full_name") or product.get("label")
    line = product.get("product_line") or name
    kw = keywords[:scenes] if keywords else ["lifestyle closeup"]
    while len(kw) < scenes:
        kw.append(kw[-1])

    hooks = {
        "living": hook or "매일 쌓이는 물때, 이제 그만 고민하세요!",
        "bike": hook or "라이딩 후 세차, 이렇게 간단할 수 있을까요?",
        "auto": hook or "세차 후에도 금방 더러워지는 차, 답답하셨죠?",
    }
    hook_line = hooks.get(product.get("id", ""), hook or "일상 속 작은 불편, 해결해 볼까요?")

    narrations = _narration_templates(product.get("id", "living"), name, line)
    scene_list: list[dict] = []
    for i in range(scenes):
        k = kw[i]
        n = i + 1
        mention = "없음"
        if n == 2:
            mention = f"손에 {line} 스프레이, 라벨은 살짝만"
        elif n == scenes:
            mention = f"대사로 {name} 자연스럽게 언급"

        scene_list.append(
            {
                "scene_no": n,
                "duration_sec": 4.0 if n < scenes else 5.0,
                "conti": _conti_ko(product, n, k, mention),
                "visual_desc": _visual_ko(product, n, k),
                "background_desc": _bg_ko(product, n),
                "narration": narrations[min(i, len(narrations) - 1)],
                "subtitle": narrations[min(i, len(narrations) - 1)][:18],
                "speaker": "host" if n % 2 else "customer",
                "product_mention": mention,
                "flow_prompt": append_locale_to_prompt(_flow_en(product, k, n, name), product, max_len=520),
                "storyboard_image_prompt": append_locale_to_prompt(
                    f"Photorealistic still frame, {k}, natural daylight, handheld lifestyle B-roll, no CGI studio",
                    product,
                ),
                "search_keyword": k,
            }
        )

    tags = _tags(product)
    return {
        "topic": topic or f"{name} — {', '.join(keywords[:3])}",
        "product_id": product.get("id"),
        "style": product.get("style"),
        "master_prompt": (
            f"실제 생활 현장에서 {name}을(를) 사용하는 모습을 담은 실사 쇼츠 B-roll. "
            f"키워드: {', '.join(keywords)}. 스튜디오 연출·CG 금지."
        ),
        "flow_master_prompt_en": append_locale_to_prompt(
            (
                f"Photorealistic lifestyle short-form B-roll for {line}. "
                f"Natural light, real hands and surfaces, keywords: {', '.join(keywords)}. "
                "No studio CGI, no logos only shots."
            ),
            product,
            max_len=400,
        ),
        "video_title": f"✨{product.get('label')} — {keywords[0]}",
        "hook_line": hook_line,
        "youtube_description": (
            f"{hook_line} {name}으로 쉽게 관리해 보세요. "
            f"#{product.get('brand')} #{line.replace(' ', '')}"
        ),
        "youtube_tags": tags,
        "input_keywords": keywords,
        "scenes": scene_list,
        "_fallback": True,
    }


def _narration_templates(pid: str, full_name: str, line: str) -> list[str]:
    if pid == "bike":
        return [
            "라이딩 후 먼지·벌레 자국, 손이 많이 가죠?",
            "물만 뿌려도 때가 쓱— 빠져요.",
            "코팅 덕에 물방울이 맺혀요.",
            f"이게 바로 {full_name}이에요.",
        ]
    if pid == "auto":
        return [
            "세차해도 금방 더러워지죠?",
            "분사하고 닦기만 해도 달라져요.",
            "물방울이 둥둥— 유지가 쉬워요.",
            f"{line}, 한 번 써보세요.",
        ]
    return [
        "매번 물때·얼룩, 청소 힘드셨죠?",
        "뿌리기만 해도 물방울이 맺혀요.",
        "쓱 닦으면 끝, 정말 간단해요.",
        f"우리 집엔 {full_name}.",
    ]


def _conti_ko(product: dict, n: int, kw: str, mention: str) -> str:
    if n == 1:
        return f"키워드 '{kw}'에 맞는 고민·상황 장면. 제품은 아직 강조하지 않음."
    if mention.startswith("대사"):
        return "사용 후 만족·일상 회복. 제품명을 부드럽게 마무리."
    return f"'{kw}' 장면에서 {product.get('product_line')} 사용·효과를 자연스럽게 연출."


def _visual_ko(product: dict, n: int, kw: str) -> str:
    settings = product.get("settings") or ["실내"]
    place = settings[min(n - 1, len(settings) - 1)]
    return f"{place}에서 {kw} 관련 클로즈업. 실제 손·표면·한국 도심·주차·셀프세차 생활감."


def _bg_ko(product: dict, n: int) -> str:
    settings = product.get("settings") or ["실내"]
    return settings[min(n - 1, len(settings) - 1)]


def _flow_en(product: dict, kw: str, n: int, name: str) -> str:
    line = product.get("product_line", name)
    pid = product.get("id", "")
    place = "urban Korea apartment parking"
    if pid == "bike":
        place = "Korean urban motorcycle parking or coin self car wash"
    elif pid == "auto":
        place = "Korean apartment garage or coin car wash booth"
    if n == 1:
        return (
            f"Photorealistic handheld shot, {kw}, {place}, problem moment, natural daylight, "
            "no product logo focus, cinematic 9:16 vertical"
        )
    if n >= 4:
        return (
            f"Satisfied lifestyle moment after using {line}, {kw}, {place}, soft smile, "
            f"subtle product bottle nearby, photorealistic, 9:16"
        )
    return (
        f"Close-up hands using spray on surface, {kw}, {place}, water beading effect, "
        f"{line} lifestyle B-roll, photorealistic natural light, 9:16 vertical"
    )


def _tags(product: dict) -> list[str]:
    base = [product.get("brand", ""), product.get("product_line", ""), "쇼츠", "생활팁", "홈케어"]
    return [t for t in base if t][:10]
