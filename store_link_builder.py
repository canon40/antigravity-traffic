# -*- coding: utf-8 -*-
"""키워드·상품 ID → 스마트스토어 URL · 블로그 푸터 (반자동 발행용)."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
LISTINGS_PATH = ROOT / "data" / "smartstore_listings.json"
CONFIG_PATH = ROOT / "config.json"

DEFAULT_STORE_SLUG = "nanumlab"


def _load_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def get_store_slug() -> str:
    cfg = _load_json(CONFIG_PATH)
    return (cfg.get("store_slug") or DEFAULT_STORE_SLUG).strip() or DEFAULT_STORE_SLUG


def build_store_url(seller_id: str, *, store_slug: str | None = None) -> str:
    slug = (store_slug or get_store_slug()).strip()
    pid = str(seller_id or "").strip()
    if not pid:
        return f"https://smartstore.naver.com/{slug}"
    return f"https://smartstore.naver.com/{slug}/products/{pid}"


def _score_listing(keyword: str, listing: dict[str, Any]) -> int:
    kw = (keyword or "").strip().lower()
    if not kw:
        return 0
    score = 0
    title = str(listing.get("title") or "").lower()
    product_line = str(listing.get("product_line") or "").lower()
    category = str(listing.get("category") or "").lower()
    if kw in title or title in kw:
        score += 80
    if product_line and product_line in kw:
        score += 60
    if "퍼마코트 자동차" in kw and category == "car":
        score += 50
    if "퍼마코트 바이크" in kw and category == "bike":
        score += 50
    if "리빙" in kw or "듀라코트" in kw:
        if category == "living":
            score += 40
    for tag in listing.get("keywords") or []:
        t = str(tag).lower()
        if t == kw:
            score += 100
        elif t in kw or kw in t:
            score += 30
    return score


def resolve_listing(keyword: str, product_id: str | None = None) -> dict[str, Any]:
    """키워드 또는 판매자센터 ID로 listings 매칭."""
    doc = _load_json(LISTINGS_PATH)
    store = get_store_slug()
    listings = doc.get("listings") or []
    pid = str(product_id or "").strip()

    if pid:
        for row in listings:
            if str(row.get("seller_id")) == pid:
                return {
                    "seller_id": pid,
                    "title": row.get("title") or keyword,
                    "category": row.get("category") or "",
                    "product_line": row.get("product_line") or "",
                    "url": build_store_url(pid, store_slug=store),
                    "store_slug": store,
                }

    best: dict[str, Any] | None = None
    best_score = 0
    for row in listings:
        if not isinstance(row, dict):
            continue
        sc = _score_listing(keyword, row)
        if sc > best_score:
            best_score = sc
            best = row

    if best and best_score > 0:
        sid = str(best.get("seller_id") or "")
        return {
            "seller_id": sid,
            "title": best.get("title") or keyword,
            "category": best.get("category") or "",
            "product_line": best.get("product_line") or "",
            "url": build_store_url(sid, store_slug=store),
            "store_slug": store,
            "match_score": best_score,
        }

    # 폴백: config.json 대표 상품
    cfg = _load_json(CONFIG_PATH)
    fallback_id = ""
    kw_low = (keyword or "").lower()
    if "바이크" in kw_low or "오토바이" in kw_low:
        fallback_id = "12655391634"
    elif "자동차" in kw_low or "퍼마" in kw_low:
        fallback_id = "12577296206"
    elif "리빙" in kw_low or "듀라" in kw_low:
        fallback_id = "10713170202"
    else:
        products = cfg.get("products") or []
        if products and isinstance(products[0], dict):
            fallback_id = str(products[0].get("id") or "")

    return {
        "seller_id": fallback_id,
        "title": keyword,
        "category": "",
        "product_line": keyword,
        "url": build_store_url(fallback_id, store_slug=store) if fallback_id else f"https://smartstore.naver.com/{store}",
        "store_slug": store,
        "match_score": 0,
        "fallback": True,
    }


def store_footer_markdown(keyword: str, store_url: str, *, product_title: str = "") -> str:
    label = (product_title or keyword or "제품").strip()
    return (
        f"\n\n---\n\n"
        f"👇 **{label}** 제품 정보 및 구매 링크 👇\n\n"
        f"{store_url}\n\n"
        f"*영상과 함께 보시면 도포·효과 이해에 도움이 됩니다.*\n"
    )


def store_footer_html(keyword: str, store_url: str, *, product_title: str = "") -> str:
    label = (product_title or keyword or "제품").strip()
    return (
        f'<br><div style="text-align:center;margin:28px 0;padding:20px;background:#f8faf8;border-radius:12px;">'
        f'<p style="font-size:1.05em;margin:0 0 12px;font-weight:bold;">👇 {label} 공식 구매 링크 👇</p>'
        f'<a href="{store_url}" target="_blank" rel="noopener" '
        f'style="display:inline-block;background:linear-gradient(135deg,#03c75a,#00a060);'
        f'color:#fff;padding:14px 28px;text-decoration:none;border-radius:8px;font-weight:bold;">'
        f'스마트스토어에서 보기</a>'
        f'<p style="font-size:0.85em;color:#666;margin:12px 0 0;">{store_url}</p>'
        f"</div>"
    )


def append_store_footer_to_content(
    content: dict[str, Any],
    keyword: str,
    listing: dict[str, Any],
) -> dict[str, Any]:
    """블로그/상품 초안 dict에 스토어 링크 푸터 주입."""
    url = listing.get("url") or ""
    title = listing.get("title") or keyword
    md_footer = store_footer_markdown(keyword, url, product_title=title)
    html_footer = store_footer_html(keyword, url, product_title=title)

    if isinstance(content.get("body"), str) and content["body"].strip():
        if content["body"].lstrip().startswith("<"):
            content["body"] = content["body"].rstrip() + html_footer
        else:
            content["body"] = content["body"].rstrip() + md_footer
    if isinstance(content.get("body_html"), str) and content["body_html"].strip():
        content["body_html"] = content["body_html"].rstrip() + html_footer
    if isinstance(content.get("body_plain"), str) and content["body_plain"].strip():
        content["body_plain"] = content["body_plain"].rstrip() + md_footer.replace("**", "")

    for key in ("D_행동유도",):
        if isinstance(content.get("sections", {}).get(key), str):
            content["sections"][key] = (
                content["sections"][key].rstrip()
                + f"\n\n스마트스토어: {url}"
            )

    content["store_url"] = url
    content["store_footer_markdown"] = md_footer.strip()
    content["store_footer_html"] = html_footer
    return content


def format_blog_copy_paste(result: dict[str, Any]) -> str:
    """네이버 블로그에 붙여넣기용 plain/markdown 텍스트."""
    content = result.get("content") or {}
    lines = [
        f"# {content.get('title') or result.get('keyword') or '블로그 초안'}",
        "",
    ]
    body = content.get("body") or content.get("body_plain") or ""
    store_url = result.get("store_url") or content.get("store_url") or ""
    if body:
        lines.append(body.strip())
    elif content.get("sections"):
        for k, v in content["sections"].items():
            lines.append(f"## {k}")
            lines.append(str(v))
            lines.append("")

    footer = (content.get("store_footer_markdown") or "").strip()
    if footer and footer not in body and (not store_url or store_url not in body):
        lines.append("")
        lines.append(footer)
    elif store_url and store_url not in body:
        lines.append("")
        lines.append(
            store_footer_markdown(result.get("keyword", ""), store_url, product_title=result.get("listing_title", "")).strip()
        )

    tags = content.get("seo_tags") or content.get("tags") or []
    if tags:
        lines.append("")
        lines.append("태그: " + ", ".join(str(t) for t in tags[:15]))
    lines.append("")
    if store_url:
        lines.append(f"※ 스마트스토어: {store_url}")
    if result.get("video_path"):
        lines.append(f"※ 첨부 영상: {result['video_path']} (블로그 에디터에 드래그)")
    return "\n".join(lines).strip() + "\n"
