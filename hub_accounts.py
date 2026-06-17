# -*- coding: utf-8 -*-
"""accounts.json 키워드 ↔ SEO 허브 config.json 동기화."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
ACCOUNTS_PATH = ROOT / "accounts.json"
DEFAULT_PRODUCT_ID = "12809532969"


def _read_accounts() -> dict[str, Any]:
    if not ACCOUNTS_PATH.is_file():
        return {}
    try:
        return json.loads(ACCOUNTS_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _write_accounts(data: dict[str, Any]) -> None:
    ACCOUNTS_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def parse_keywords_text(text: str) -> list[str]:
    if not text:
        return []
    parts = re.split(r"[,，\n;]+", str(text))
    out: list[str] = []
    seen: set[str] = set()
    for p in parts:
        kw = p.strip()
        if not kw or kw in seen:
            continue
        seen.add(kw)
        out.append(kw)
    return out


def keywords_from_accounts() -> list[str]:
    data = _read_accounts()
    raw = data.get("keywords")
    if isinstance(raw, list):
        return parse_keywords_text(", ".join(str(x) for x in raw))
    if isinstance(raw, str):
        return parse_keywords_text(raw)
    return []


def save_accounts_keywords(keywords: list[str]) -> list[str]:
    cleaned = parse_keywords_text(", ".join(keywords))
    data = _read_accounts()
    data["keywords"] = ", ".join(cleaned)
    _write_accounts(data)
    return cleaned


def keywords_to_config_items(keywords: list[str], *, store_name: str = "나눔랩", product_id: str | None = None) -> list[dict[str, str]]:
    pid = (product_id or DEFAULT_PRODUCT_ID).strip()
    return [{"keyword": kw, "store_name": store_name, "product_id": pid} for kw in keywords if kw]


def merge_keywords_into_config(config: dict[str, Any], keywords: list[str]) -> dict[str, Any]:
    if not keywords:
        return config
    store = (config.get("store_name") or "나눔랩").strip()
    product_id = None
    products = config.get("products") or []
    if products and isinstance(products[0], dict):
        product_id = str(products[0].get("id") or DEFAULT_PRODUCT_ID)
    items = keywords_to_config_items(keywords, store_name=store, product_id=product_id)

    existing_kw = {str(x.get("keyword") or "").strip() for x in (config.get("keywords") or []) if isinstance(x, dict)}
    merged_keywords = list(config.get("keywords") or [])
    for item in items:
        if item["keyword"] not in existing_kw:
            merged_keywords.append(item)
            existing_kw.add(item["keyword"])

    existing_pri = {str(x.get("keyword") or "").strip() for x in (config.get("priority_keywords") or []) if isinstance(x, dict)}
    merged_pri = list(config.get("priority_keywords") or [])
    for item in items:
        if item["keyword"] not in existing_pri:
            merged_pri.insert(0, item)
            existing_pri.add(item["keyword"])

    config["keywords"] = merged_keywords
    config["priority_keywords"] = merged_pri[: max(len(merged_pri), len(items))]
    return config


def sync_accounts_keywords_to_config(config: dict[str, Any] | None = None) -> dict[str, Any]:
    from rank_tracker import load_config, save_config

    cfg = dict(config or load_config())
    user_kws = keywords_from_accounts()
    if not user_kws:
        return cfg
    cfg = merge_keywords_into_config(cfg, user_kws)
    save_config(cfg)
    return cfg
