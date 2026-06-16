# -*- coding: utf-8 -*-
"""얼굴 없는 AI 유튜브 니치 템플릿 (영상 4번) → 콘티·FLOW 프롬프트."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parent.parent
NICHE_PATH = _ROOT / "data" / "shorts_factory" / "niche_templates.json"


def load_niche_data() -> dict[str, Any]:
    if not NICHE_PATH.is_file():
        return {"niches": [], "blocked_korea": []}
    return json.loads(NICHE_PATH.read_text(encoding="utf-8"))


def list_niches(*, shopping_only: bool = False) -> list[dict[str, Any]]:
    data = load_niche_data()
    items = list(data.get("niches") or [])
    if shopping_only:
        items = [n for n in items if n.get("shopping_adaptable")]
    return items


def get_niche(niche_id: str) -> dict[str, Any] | None:
    nid = (niche_id or "").strip()
    for n in load_niche_data().get("niches") or []:
        if n.get("id") == nid:
            return n
    return None


def niche_prompt_block(niche_id: str | None) -> str:
    """generator 프롬프트에 붙일 니치 블록."""
    if not niche_id:
        return ""
    n = get_niche(niche_id)
    if not n:
        return ""

    hooks = " | ".join(n.get("hook_templates") or [])[:400]
    flow = " → ".join(n.get("scene_flow") or [])
    hints = "\n".join(f"  - {h}" for h in (n.get("flow_scene_hints") or [])[:5])
    notes = n.get("korea_notes") or ""

    return f"""【AI 니치 템플릿 · {n.get('name_ko')} ({n.get('id')})】
- 장면 흐름: {flow}
- 후킹 참고: {hooks}
- FLOW 마스터 톤(영어): {n.get('flow_master_en', '')}
- 장면별 FLOW 힌트:
{hints}
- 한국 적용: {notes}
- 해외 수익 숫자 복붙 금지. 구조만 참고.
"""


def list_blocked_korea() -> list[dict[str, Any]]:
    return list(load_niche_data().get("blocked_korea") or [])
