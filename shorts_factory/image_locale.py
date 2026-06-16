# -*- coding: utf-8 -*-
"""한국 시장용 이미지·B-roll 장면 힌트 (바이크·자동차)."""

from __future__ import annotations

import re

_DEFAULT_SUFFIX: dict[str, str] = {
    "bike": (
        "South Korea urban rider lifestyle, apartment underground parking or coin self car wash, "
        "city commute street, no mountains, no off-road, no dirt trail, no motocross, no desert adventure"
    ),
    "auto": (
        "South Korea urban car owner, apartment parking garage or coin self car wash booth, "
        "city sedan in driveway, no off-road mud, no mountain rally, no desert adventure highway"
    ),
}


def locale_prompt_suffix(product: dict | None) -> str:
    if not product:
        return ""
    loc = product.get("image_locale") or {}
    custom = str(loc.get("prompt_suffix_en") or "").strip()
    if custom:
        return custom
    return _DEFAULT_SUFFIX.get(str(product.get("id") or ""), "")


def locale_rules_for_llm(product: dict) -> str:
    loc = product.get("image_locale")
    if not loc:
        return ""
    lines = ["【한국 시장 이미지·장면 (필수)】"]
    market = loc.get("market")
    if market:
        lines.append(f"- 대상 시장: {market}")
    preferred = loc.get("preferred_scenes") or product.get("settings") or []
    if preferred:
        lines.append(f"- 배경·상황: {', '.join(preferred)}")
    forbidden = loc.get("forbidden_scenes") or []
    if forbidden:
        lines.append(f"- 금지(해외식 산악·오프로드·더트 연출): {', '.join(forbidden)}")
    suffix = locale_prompt_suffix(product)
    if suffix:
        lines.append(
            "- flow_prompt·storyboard_image_prompt 영어 문장에 위 배경을 구체적으로 넣고, "
            f"금지 장면은 절대 포함하지 말 것. 예: …, {suffix}"
        )
    return "\n".join(lines) + "\n"


def append_locale_to_prompt(prompt: str, product: dict | None, *, max_len: int = 480) -> str:
    text = re.sub(r"\s+", " ", (prompt or "").strip())
    suffix = locale_prompt_suffix(product)
    if not suffix or not text:
        return text[:max_len] if text else suffix[:max_len]
    key = suffix[:40].lower()
    if key and key in text.lower():
        return text[:max_len]
    combined = f"{text.rstrip('. ')}, {suffix}"
    return combined[:max_len]
