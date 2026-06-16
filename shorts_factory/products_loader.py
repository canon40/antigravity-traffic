# -*- coding: utf-8 -*-
"""products.json + keyword_presets.json 병합 로드."""

from __future__ import annotations

import json
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
PRODUCTS_PATH = _ROOT / "data" / "shorts_factory" / "products.json"
PRESETS_PATH = _ROOT / "data" / "shorts_factory" / "keyword_presets.json"


def _merge_keyword_presets(data: dict) -> dict:
    if not PRESETS_PATH.is_file():
        return data
    try:
        presets = json.loads(PRESETS_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return data
    for pid, block in presets.items():
        if pid not in data or not isinstance(data[pid], dict):
            continue
        if isinstance(block, dict):
            en = block.get("en")
            ko = block.get("ko")
            if isinstance(en, list) and en:
                data[pid]["preset_keywords"] = [str(x).strip() for x in en if str(x).strip()]
            if isinstance(ko, list) and ko:
                data[pid]["preset_keywords_ko"] = [str(x).strip() for x in ko if str(x).strip()]
        elif isinstance(block, list) and block:
            data[pid]["preset_keywords"] = [str(x).strip() for x in block if str(x).strip()]
    return data


def load_products_data() -> dict:
    if not PRODUCTS_PATH.is_file():
        return {}
    data = json.loads(PRODUCTS_PATH.read_text(encoding="utf-8"))
    return _merge_keyword_presets(data)
