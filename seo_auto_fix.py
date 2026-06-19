# -*- coding: utf-8 -*-
"""SEO 감사·트래픽 후 config 메타·키워드 자동 보완 (네이버 차단 시 config 폴백용)."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Callable
from urllib.parse import urlparse

from hub_accounts import merge_keywords_into_config
from rank_tracker import load_config, save_config
from seo_content_builder import generate_content, save_content

Logger = Callable[[str], None] | None


def _norm_url(url: str) -> str:
    return (url or "").strip().rstrip("/")


def find_product(
    config: dict[str, Any],
    *,
    url: str | None = None,
    product_id: str | None = None,
) -> tuple[dict[str, Any], int] | None:
    products = config.get("products") or []
    for i, product in enumerate(products):
        if not isinstance(product, dict):
            continue
        if product_id and str(product.get("id") or "").strip() == str(product_id).strip():
            return product, i
        if url and _norm_url(str(product.get("url") or "")) == _norm_url(url):
            return product, i
    return None


def primary_keyword_for_product(config: dict[str, Any], product_id: str) -> str:
    pid = str(product_id).strip()
    for source in (config.get("priority_keywords") or [], config.get("keywords") or []):
        for item in source:
            if not isinstance(item, dict):
                continue
            if str(item.get("product_id") or "").strip() == pid:
                kw = (item.get("keyword") or "").strip()
                if kw:
                    return kw
    product = find_product(config, product_id=pid)
    if product:
        name = (product[0].get("name") or "").strip()
        if name:
            return name
    return config.get("brand") or "셀프 코팅"


def merge_keywords_for_product(
    config: dict[str, Any],
    product_id: str,
    keywords: list[str],
) -> int:
    """상품별 키워드를 config에 추가. 추가된 개수 반환."""
    pid = str(product_id).strip()
    store = (config.get("store_name") or "나눔랩").strip()
    existing = {
        str(x.get("keyword") or "").strip()
        for x in (config.get("keywords") or [])
        if isinstance(x, dict)
    }
    to_add: list[str] = []
    for kw in keywords:
        k = (kw or "").strip()
        if len(k) < 2 or k in existing:
            continue
        existing.add(k)
        to_add.append(k)
    if not to_add:
        return 0

    items = [{"keyword": k, "store_name": store, "product_id": pid} for k in to_add]
    merged_kw = list(config.get("keywords") or [])
    merged_pri = list(config.get("priority_keywords") or [])
    pri_set = {str(x.get("keyword") or "").strip() for x in merged_pri if isinstance(x, dict)}

    for item in items:
        merged_kw.append(item)
        if item["keyword"] not in pri_set:
            merged_pri.insert(0, item)
            pri_set.add(item["keyword"])

    config["keywords"] = merged_kw
    config["priority_keywords"] = merged_pri
    return len(to_add)


def _needs_product_seo(product: dict[str, Any]) -> bool:
    desc = (product.get("meta_description") or "").strip()
    title = (product.get("meta_title") or "").strip()
    tags = product.get("tags") or []
    if len(desc) < 50:
        return True
    if not title or len(title) < 10:
        return True
    if not tags:
        return True
    return False


def ensure_product_seo(
    config: dict[str, Any],
    product_id: str,
    *,
    logger: Logger = None,
) -> dict[str, Any]:
    hit = find_product(config, product_id=product_id)
    if not hit:
        return {"ok": False, "error": "product_not_found", "product_id": product_id}

    product, idx = hit
    if not _needs_product_seo(product):
        return {"ok": True, "product_id": product_id, "changed": [], "skipped": True}

    pid = str(product.get("id") or product_id)
    name = (product.get("name") or "상품").strip()
    brand = (config.get("brand") or config.get("store_name") or "나눔랩").strip()
    keyword = primary_keyword_for_product(config, pid)

    gen = generate_content("meta_tags", keyword, name, brand)
    if not gen.get("success"):
        return {"ok": False, "error": gen.get("error") or "generate_failed", "product_id": pid}

    content = gen.get("content") or {}
    meta_title = (content.get("product_title_suggestion") or f"{brand} {name} {keyword}")[:70]
    meta_desc = (content.get("meta_description") or "")[:160]
    tags = list(content.get("tags") or [])[:12]

    products = list(config.get("products") or [])
    products[idx] = {
        **product,
        "meta_title": meta_title,
        "meta_description": meta_desc,
        "tags": tags,
        "seo_updated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "seo_source": "auto_fix",
    }
    config["products"] = products

    save_content(gen, product_id=pid)
    added_kw = merge_keywords_for_product(config, pid, tags + [keyword])
    save_config(config)

    changed = ["meta_title", "meta_description", "tags"]
    if added_kw:
        changed.append(f"keywords+{added_kw}")

    msg = f"🔧 SEO 자동 보완: {name} — {', '.join(changed)}"
    if logger:
        logger(msg)

    return {
        "ok": True,
        "product_id": pid,
        "product_name": name,
        "changed": changed,
        "meta_title": meta_title,
        "meta_description": meta_desc,
        "tags": tags,
        "keywords_added": added_kw,
    }


def _blog_key(url: str) -> str:
    return _norm_url(url)


def ensure_blog_seo(
    config: dict[str, Any],
    blog_url: str,
    *,
    logger: Logger = None,
) -> dict[str, Any]:
    """블로그 메타 제안을 config.blog_seo에 저장 (네이버 발행은 수동·별도)."""
    blog_seo = dict(config.get("blog_seo") or {})
    key = _blog_key(blog_url)
    existing = blog_seo.get(key) or {}
    if len((existing.get("meta_description") or "").strip()) >= 50:
        return {"ok": True, "url": blog_url, "changed": [], "skipped": True}

    brand = (config.get("brand") or "나눔랩").strip()
    keywords = [
        str(x.get("keyword") or "").strip()
        for x in (config.get("priority_keywords") or [])[:5]
        if isinstance(x, dict) and x.get("keyword")
    ]
    keyword = keywords[0] if keywords else "셀프 유리막 코팅"
    host = urlparse(blog_url).netloc.lower()
    blog_name = "네이버 블로그" if "blog.naver" in host else ("티스토리" if "tistory" in host else "블로그")

    gen = generate_content("blog_review", keyword, blog_name, brand)
    if not gen.get("success"):
        return {"ok": False, "error": gen.get("error") or "generate_failed", "url": blog_url}

    content = gen.get("content") or {}
    body = (content.get("body") or "")[:300].replace("\n", " ")
    meta_desc = (
        f"{brand} {keyword} — {body}"
        if body
        else f"{brand} {keyword} 셀프 코팅·발수·광택 관리 가이드와 실사용 후기."
    )[:160]
    title = (content.get("title") or f"{keyword} | {brand} 블로그")[:70]

    blog_seo[key] = {
        "meta_title": title,
        "meta_description": meta_desc,
        "target_keywords": keywords[:8] or [keyword],
        "seo_updated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "seo_source": "auto_fix",
        "apply_hint": "블로그 관리 → 기본 설정 → 검색·메타 설명에 붙여넣기",
    }
    config["blog_seo"] = blog_seo
    merge_keywords_into_config(config, keywords[:3] if keywords else [keyword])
    save_config(config)
    save_content(gen, product_id="blog")

    changed = ["meta_title", "meta_description", "target_keywords"]
    msg = f"🔧 블로그 SEO 제안 저장: {blog_url[:50]}…"
    if logger:
        logger(msg)

    return {"ok": True, "url": blog_url, "changed": changed, "meta_description": meta_desc}


def remediate_after_traffic(target_url: str, *, logger: Logger = None) -> dict[str, Any]:
    """트래픽 1회 후 해당 상품 SEO·키워드 자동 보완."""
    config = load_config()
    hit = find_product(config, url=target_url)
    if not hit:
        return {"ok": False, "reason": "not_a_product_url", "url": target_url}
    product, _ = hit
    pid = str(product.get("id") or "")
    if not pid:
        return {"ok": False, "reason": "no_product_id", "url": target_url}
    return ensure_product_seo(config, pid, logger=logger)


def remediate_from_audit(audit: dict[str, Any], *, logger: Logger = None) -> list[dict[str, Any]]:
    """SEO 점검 결과 기반 — 차단·누락 항목 config 자동 보완."""
    config = load_config()
    results: list[dict[str, Any]] = []

    for page in audit.get("products") or []:
        url = (page.get("url") or "").strip()
        if not url:
            continue
        hit = find_product(config, url=url)
        if not hit:
            continue
        product, _ = hit
        pid = str(product.get("id") or "")
        needs = page.get("partial") or not page.get("success")
        if not needs:
            for check in page.get("checks") or []:
                if not check.get("passed") and check.get("name") in (
                    "메타 설명(description)",
                    "페이지 제목(title)",
                    "타겟 키워드 포함",
                ):
                    needs = True
                    break
        if needs and pid:
            config = load_config()
            results.append(ensure_product_seo(config, pid, logger=logger))

    for page in audit.get("blogs") or []:
        url = (page.get("url") or "").strip()
        if not url:
            continue
        needs = not page.get("success")
        if not needs:
            for check in page.get("checks") or []:
                if not check.get("passed") and check.get("name") in (
                    "메타 설명(description)",
                    "타겟 키워드 포함",
                ):
                    needs = True
                    break
        if needs:
            config = load_config()
            results.append(ensure_blog_seo(config, url, logger=logger))

    return results


def product_meta_for_audit(url: str, config: dict[str, Any] | None = None) -> dict[str, str] | None:
    """seo_checker 폴백용 — config에 저장된 메타 반환."""
    cfg = config or load_config()
    hit = find_product(cfg, url=url)
    if not hit:
        return None
    product, _ = hit
    name = (product.get("name") or "").strip()
    title = (product.get("meta_title") or name).strip()
    desc = (product.get("meta_description") or "").strip()
    if not title and not desc:
        if name:
            return {"title": name, "description": name}
        return None
    return {"title": title or name, "description": desc or title or name}


def blog_meta_for_audit(url: str, config: dict[str, Any] | None = None) -> dict[str, str] | None:
    cfg = config or load_config()
    entry = (cfg.get("blog_seo") or {}).get(_blog_key(url)) or {}
    title = (entry.get("meta_title") or "").strip()
    desc = (entry.get("meta_description") or "").strip()
    if not title and not desc:
        return None
    return {"title": title, "description": desc}
