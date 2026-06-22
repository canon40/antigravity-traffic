# -*- coding: utf-8 -*-
"""구글 검색 색인 — permacoat.shop 상품 랜딩·sitemap·JSON-LD."""

from __future__ import annotations

import html
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from urllib.parse import quote

from rank_tracker import load_config

Logger = Callable[[str], None] | None

_ROOT = Path(__file__).resolve().parent
_STATIC = _ROOT / "static"


def site_base_url() -> str:
    return (
        os.environ.get("SITE_BASE_URL")
        or os.environ.get("VERCEL_URL")
        or "https://permacoat.shop"
    ).rstrip("/").replace("http://", "https://")


def _esc(text: str) -> str:
    return html.escape(str(text or ""), quote=True)


def _product_page_data(product: dict[str, Any], config: dict[str, Any], base: str) -> dict[str, str]:
    pid = str(product.get("id") or "").strip()
    name = (product.get("name") or f"상품 {pid}").strip()
    brand = (config.get("brand") or config.get("store_name") or "나눔랩").strip()
    title = (product.get("meta_title") or f"{brand} {name}")[:70].strip()
    desc = (product.get("meta_description") or f"{brand} {name} — 셀프 유리막 코팅·발수·광택. 공식 스마트스토어에서 구매.")[:160]
    store_url = (product.get("url") or f"https://smartstore.naver.com/nanumlab/products/{pid}").strip()
    landing = f"{base}/p/{pid}"
    tags = product.get("tags") or []
    keywords = ", ".join(str(t) for t in tags[:8]) if tags else name
    return {
        "id": pid,
        "name": name,
        "brand": brand,
        "title": title,
        "description": desc,
        "store_url": store_url,
        "landing_url": landing,
        "keywords": keywords,
    }


def render_product_html(product: dict[str, Any], config: dict[str, Any] | None = None, *, base: str | None = None) -> str:
    cfg = config or load_config()
    base = (base or site_base_url()).rstrip("/")
    d = _product_page_data(product, cfg, base)
    schema = {
        "@context": "https://schema.org",
        "@type": "Product",
        "name": d["name"],
        "description": d["description"],
        "brand": {"@type": "Brand", "name": d["brand"]},
        "url": d["landing_url"],
        "sku": d["id"],
        "offers": {
            "@type": "Offer",
            "url": d["store_url"],
            "availability": "https://schema.org/InStock",
            "priceCurrency": "KRW",
        },
    }
    schema_json = json.dumps(schema, ensure_ascii=False)
    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>{_esc(d['title'])}</title>
  <meta name="description" content="{_esc(d['description'])}"/>
  <meta name="keywords" content="{_esc(d['keywords'])}"/>
  <meta name="robots" content="index,follow"/>
  <link rel="canonical" href="{_esc(d['landing_url'])}"/>
  <meta property="og:type" content="product"/>
  <meta property="og:title" content="{_esc(d['title'])}"/>
  <meta property="og:description" content="{_esc(d['description'])}"/>
  <meta property="og:url" content="{_esc(d['landing_url'])}"/>
  <meta property="product:brand" content="{_esc(d['brand'])}"/>
  <script type="application/ld+json">{schema_json}</script>
  <style>
    body{{font-family:system-ui,sans-serif;background:#0f172a;color:#e2e8f0;margin:0;padding:24px;line-height:1.6}}
    main{{max-width:720px;margin:0 auto}}
    a.btn{{display:inline-block;margin-top:16px;padding:14px 24px;background:#2563eb;color:#fff;text-decoration:none;border-radius:10px;font-weight:600}}
    .tags{{color:#94a3b8;font-size:0.9rem;margin-top:12px}}
  </style>
</head>
<body>
  <main>
    <p style="color:#94a3b8;font-size:0.85rem">{_esc(d['brand'])} 공식 안내</p>
    <h1>{_esc(d['name'])}</h1>
    <p>{_esc(d['description'])}</p>
    <p class="tags">키워드: {_esc(d['keywords'])}</p>
    <a class="btn" href="{_esc(d['store_url'])}" rel="noopener">네이버 스마트스토어에서 구매하기</a>
    <p style="margin-top:24px;font-size:0.78rem;color:#64748b">구글 검색용 공식 랜딩 · <a href="{_esc(base)}/products" style="color:#93c5fd">전체 상품</a></p>
  </main>
</body>
</html>"""


def render_products_index(products: list[dict[str, Any]], config: dict[str, Any], *, base: str | None = None) -> str:
    base = (base or site_base_url()).rstrip("/")
    brand = (config.get("brand") or "나눔랩").strip()
    items = []
    for p in products:
        if not isinstance(p, dict) or not p.get("id"):
            continue
        d = _product_page_data(p, config, base)
        items.append(
            f'<li><a href="{_esc(d["landing_url"])}" style="color:#93c5fd">{_esc(d["name"])}</a>'
            f' <span style="color:#64748b;font-size:0.85rem">— {_esc(d["description"][:80])}…</span></li>'
        )
    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>{_esc(brand)} 코팅제 상품 — 구글 검색</title>
  <meta name="description" content="{_esc(brand)} 유리막·셀프 코팅제 전체 상품. 구글에서 검색되는 공식 안내 페이지."/>
  <meta name="robots" content="index,follow"/>
  <link rel="canonical" href="{_esc(base)}/products"/>
</head>
<body style="font-family:system-ui,sans-serif;background:#0f172a;color:#e2e8f0;padding:24px">
  <main style="max-width:720px;margin:0 auto">
    <h1>{_esc(brand)} 상품 목록</h1>
    <p style="color:#94a3b8">구글 검색 색인용 공식 페이지입니다. 각 상품 페이지에서 스마트스토어로 연결됩니다.</p>
    <ul style="line-height:1.8">{''.join(items)}</ul>
  </main>
</body>
</html>"""


def build_sitemap_xml(urls: list[str]) -> str:
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    lines = ['<?xml version="1.0" encoding="UTF-8"?>', '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for u in urls:
        lines.append(f"  <url><loc>{html.escape(u)}</loc><lastmod>{today}</lastmod><changefreq>weekly</changefreq><priority>0.8</priority></url>")
    lines.append("</urlset>")
    return "\n".join(lines)


def build_robots_txt(base: str) -> str:
    return f"User-agent: *\nAllow: /\nAllow: /p/\nAllow: /products\nSitemap: {base}/sitemap.xml\n"


def build_google_seo(*, logger: Logger = None, base_url: str | None = None) -> dict[str, Any]:
    """config 상품 → static/p/*.html · sitemap · robots (Vercel·로컬 배포용)."""
    config = load_config()
    base = (base_url or site_base_url()).rstrip("/")
    products = [p for p in (config.get("products") or []) if isinstance(p, dict) and p.get("id")]

    try:
        from seo_auto_fix import ensure_product_seo

        for p in products:
            pid = str(p.get("id") or "")
            if pid:
                ensure_product_seo(config, pid, logger=logger)
        config = load_config()
        products = [p for p in (config.get("products") or []) if isinstance(p, dict) and p.get("id")]
    except Exception:
        pass

    p_dir = _STATIC / "p"
    p_dir.mkdir(parents=True, exist_ok=True)
    products_dir = _STATIC / "products"
    products_dir.mkdir(parents=True, exist_ok=True)

    landing_urls: list[str] = [f"{base}/", f"{base}/products"]
    written = 0
    for product in products:
        pid = str(product.get("id") or "").strip()
        if not pid:
            continue
        page_html = render_product_html(product, config, base=base)
        (p_dir / f"{pid}.html").write_text(page_html, encoding="utf-8")
        landing_urls.append(f"{base}/p/{pid}")
        written += 1

    (products_dir / "index.html").write_text(render_products_index(products, config, base=base), encoding="utf-8")
    (_STATIC / "sitemap.xml").write_text(build_sitemap_xml(landing_urls), encoding="utf-8")
    (_STATIC / "robots.txt").write_text(build_robots_txt(base), encoding="utf-8")

    msg = f"🌐 구글 SEO: 상품 {written}페이지 · sitemap {len(landing_urls)}URL"
    if logger:
        logger(msg)

    return {
        "ok": True,
        "pages": written,
        "sitemap_urls": len(landing_urls),
        "sitemap_url": f"{base}/sitemap.xml",
        "robots_url": f"{base}/robots.txt",
        "products_index": f"{base}/products",
        "search_console_hint": (
            "Google Search Console → Sitemaps → "
            + f"{base}/sitemap.xml 등록 · URL 검사로 /p/ 상품 페이지 색인 요청"
        ),
    }


def find_product_by_id(product_id: str) -> dict[str, Any] | None:
    pid = str(product_id or "").strip()
    for p in load_config().get("products") or []:
        if isinstance(p, dict) and str(p.get("id") or "") == pid:
            return p
    return None
