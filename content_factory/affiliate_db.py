# -*- coding: utf-8 -*-
"""수동 큐레이션 제휴 상품 DB (쿠팡 파트너스 등)."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

_BASE = Path(__file__).resolve().parent.parent
_DEFAULT_DB = _BASE / "data" / "content_factory" / "affiliate_products.json"


def _db_path() -> Path:
    import os

    p = os.environ.get("CONTENT_FACTORY_AFFILIATE_DB", "").strip()
    return Path(p) if p else _DEFAULT_DB


def load_products() -> list[dict[str, Any]]:
    path = _db_path()
    if not path.is_file():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, list):
        return data
    return list(data.get("products") or [])


def save_products(products: list[dict[str, Any]]) -> None:
    path = _db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"products": products}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def upsert_product(product: dict[str, Any]) -> dict[str, Any]:
    products = load_products()
    pid = str(product.get("id") or "").strip()
    if not pid:
        raise ValueError("id 필수")
    replaced = False
    for i, p in enumerate(products):
        if str(p.get("id")) == pid:
            products[i] = {**p, **product}
            replaced = True
            break
    if not replaced:
        products.append(product)
    save_products(products)
    return product


def _tokenize(text: str) -> set[str]:
    text = (text or "").lower()
    parts = re.split(r"[\s,./|]+", text)
    return {p for p in parts if len(p) >= 2}


def search_by_topic(topic: str, *, limit: int = 5) -> list[dict[str, Any]]:
    """주제·태그 매칭으로 제휴 상품 검색."""
    topic_tokens = _tokenize(topic)
    scored: list[tuple[int, dict[str, Any]]] = []
    for p in load_products():
        tags = p.get("tags") or []
        name = str(p.get("name") or "")
        blob = " ".join([name] + [str(t) for t in tags])
        ptokens = _tokenize(blob)
        score = len(topic_tokens & ptokens)
        if score > 0:
            scored.append((score, p))
    scored.sort(key=lambda x: (-x[0], str(x[1].get("name", ""))))
    return [p for _, p in scored[:limit]]
