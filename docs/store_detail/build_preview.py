# -*- coding: utf-8 -*-
"""콘티(bike_detail_conti.json) → plan.html 검토 → 상세 HTML 생성."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PREVIEW = ROOT / "preview"
CONTI = ROOT / "bike_detail_conti.json"
MANIFEST = PREVIEW / "images_manifest.json"


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _flatten_product(p: dict) -> dict:
    meta = p.get("meta") or {}
    copy = p.get("copy") or {}
    kw = p.get("keywords") or {}
    return {
        **meta,
        "product_name_seo": kw.get("shopping_product_name", ""),
        "tags": kw.get("shopping_tags") or [],
        "opening": copy.get("opening", ""),
        "recommend": copy.get("recommend") or [],
        "section_before": copy.get("section_before", ""),
        "section_wax": copy.get("section_wax", ""),
        "section_parts": copy.get("section_parts", ""),
        "section_care": copy.get("section_care", ""),
        "spec_rows": p.get("spec_rows") or [],
        "faq": p.get("faq") or [],
        "slides": p.get("slides") or [],
        "concept": p.get("concept") or {},
        "keywords": kw,
    }


def _slide_caption(slides: list[dict], index: int, fallback: str = "") -> str:
    if index < len(slides):
        return slides[index].get("caption") or fallback
    return fallback


def _img_src(slot: dict) -> str:
    local = slot.get("local")
    if local:
        p = PREVIEW / local
        if p.exists():
            return local.replace("\\", "/")
    unsplash = slot.get("unsplash", "")
    if unsplash.startswith("photo-"):
        return f"https://images.unsplash.com/{unsplash}?w=860&auto=format&fit=crop&q=85"
    return unsplash


def _img_tag(slot: dict, caption: str = "") -> str:
    cap = (
        f'<p style="text-align:center;font-size:12px;color:#888;margin:-8px 0 20px;">{caption}</p>'
        if caption
        else ""
    )
    alt = slot.get("alt", "")
    return (
        f'<img src="{_img_src(slot)}" alt="{alt}" '
        f'style="width:100%;max-width:860px;display:block;margin:20px auto;border-radius:8px;'
        f'box-shadow:0 2px 12px rgba(0,0,0,.08);" loading="lazy" />'
        f"{cap}"
    )


def _spec_table(rows: list[list[str]], accent: str) -> str:
    trs = "".join(
        f'<tr><td style="border:1px solid #ddd;padding:10px;width:32%;">{k}</td>'
        f'<td style="border:1px solid #ddd;padding:10px;">{v}</td></tr>'
        for k, v in rows
    )
    return (
        f'<table style="width:100%;border-collapse:collapse;font-size:14px;margin:12px 0;">'
        f'<tr style="background:{accent};color:#fff;">'
        f'<th style="border:1px solid #ddd;padding:10px;text-align:left;">항목</th>'
        f'<th style="border:1px solid #ddd;padding:10px;text-align:left;">내용</th></tr>{trs}</table>'
    )


def _faq_table(faq: list[list[str]]) -> str:
    trs = "".join(
        f'<tr><td style="border:1px solid #ddd;padding:10px;width:35%;">{q}</td>'
        f'<td style="border:1px solid #ddd;padding:10px;">{a}</td></tr>'
        for q, a in faq
    )
    return (
        f'<table style="width:100%;border-collapse:collapse;font-size:14px;margin:12px 0;">'
        f'<tr style="background:#f3f4f6;">'
        f'<th style="border:1px solid #ddd;padding:10px;">질문</th>'
        f'<th style="border:1px solid #ddd;padding:10px;">답변</th></tr>{trs}</table>'
    )


def _seo_meta_block(meta: dict) -> str:
    tags = ", ".join(meta.get("tags") or [])
    pname = meta.get("product_name_seo", "")
    kw = meta.get("keywords") or {}
    primary = ", ".join(kw.get("body_primary") or [])
    secondary = ", ".join(kw.get("body_secondary") or [])
    return (
        f'<div style="font-size:12px;color:#64748b;background:#f8fafc;border:1px dashed #cbd5e1;'
        f'padding:12px 14px;border-radius:8px;margin-bottom:20px;">'
        f'<strong style="color:#475569;">[쇼핑검색 탭 — 본문 미포함]</strong><br/>'
        f'상품명: {pname}<br/>'
        f'태그: {tags}<br/>'
        f'<span style="color:#94a3b8;">본문 핵심키워드: {primary} · 보조: {secondary}</span>'
        f"</div>"
    )


def build_body(meta: dict, slots: list[dict], *, preview: bool) -> str:
    a = meta["accent"]
    s = slots
    slides = meta.get("slides") or []
    h2 = lambda t: (
        f'<h2 style="font-size:22px;font-weight:700;margin:32px 0 12px;border-left:4px solid {a};'
        f'padding-left:12px;">{t}</h2>'
    )

    rec_li = "".join(f"<li>{item}</li>" for item in meta.get("recommend") or [])

    before_after = (
        '<div style="display:flex;gap:8px;flex-wrap:wrap;max-width:860px;margin:0 auto;">'
        f'<div style="flex:1;min-width:280px;">{_img_tag(s[2], _slide_caption(slides, 2, "03 BEFORE"))}</div>'
        f'<div style="flex:1;min-width:280px;">{_img_tag(s[3], _slide_caption(slides, 3, "04 AFTER"))}</div>'
        + "</div>"
    )

    steps = "".join(
        f'<div style="margin-bottom:8px;">{_img_tag(s[i], _slide_caption(slides, i))}</div>'
        for i in range(8, 11)
    )

    seo_block = _seo_meta_block(meta) if preview else ""

    return f"""
{seo_block}
{_img_tag(s[0], _slide_caption(slides, 0, "01 히어로"))}
{h2(meta["headline"])}
<p style="font-size:16px;color:#444;text-align:center;margin-bottom:8px;">{meta["sub"]}</p>
<p>{meta["opening"]}</p>
<p style="font-size:13px;color:#666;">※ 효과는 시공 환경·관리 습관에 따라 달라질 수 있습니다.</p>

{_img_tag(s[1], _slide_caption(slides, 1, "02 라이더"))}
{h2("이런 라이더께 추천합니다")}
<ul style="padding-left:20px;">{rec_li}</ul>

{h2("시공 전후, 물방울이 말해줍니다")}
<p>{meta.get("section_before", "")}</p>
{before_after}

{_img_tag(s[4], _slide_caption(slides, 4, "05 비딩"))}
{h2("왁스가 아닌, 유리막 코팅")}
<p>{meta.get("section_wax", "")}</p>

{_img_tag(s[5], _slide_caption(slides, 5, "06 제품"))}
{h2("제품 스펙")}
{_spec_table(meta.get("spec_rows") or [], a)}
<p>듀라코트·퍼마코트는 <strong>영국 수출</strong> 실적이 있는 라인입니다.</p>

<div style="display:flex;gap:8px;flex-wrap:wrap;max-width:860px;margin:0 auto;">
<div style="flex:1;min-width:280px;">{_img_tag(s[6], _slide_caption(slides, 6, "07 도장면"))}</div>
<div style="flex:1;min-width:280px;">{_img_tag(s[7], _slide_caption(slides, 7, "08 헬멧"))}</div>
</div>
{h2("시공 가능 부위")}
<p>{meta.get("section_parts", "")}</p>
<ul style="padding-left:20px;">
  <li><strong>도장면</strong> — 탱크, 카울, 페어링</li>
  <li><strong>헬멧</strong> — 쉘·바이저 (재질별 테스트)</li>
  <li><strong>휠·트림</strong> — 소량 테스트 후 진행</li>
</ul>
<p style="font-size:13px;color:#856404;background:#fffbeb;padding:12px;border:1px solid #fcd34d;">
<strong>주의:</strong> 머플러·배기 등 <strong>고온부</strong>는 제품 안내 확인. 리빙코트 혼용 금지.</p>

{h2("셀프 시공 3단계")}
{steps}

{_img_tag(s[11], _slide_caption(slides, 11, "12 마무리"))}
{h2("관리 & FAQ")}
<p>{meta.get("section_care", "")}</p>
{_faq_table(meta.get("faq") or [])}
<p style="margin-top:32px;font-size:13px;color:#666;text-align:center;">듀라코트 퍼마코트 · 바이크 유리막 코팅 · 나눔랩</p>
"""


def build_plan_section(sku: str, p: dict) -> str:
    concept = p.get("concept") or {}
    kw = p.get("keywords") or {}
    meta = p.get("meta") or {}
    accent = meta.get("accent", "#334155")

    slide_rows = "".join(
        f'<tr><td style="padding:8px;border:1px solid #e2e8f0;text-align:center;">{sl.get("no")}</td>'
        f'<td style="padding:8px;border:1px solid #e2e8f0;">{sl.get("caption","")}</td>'
        f'<td style="padding:8px;border:1px solid #e2e8f0;">{sl.get("visual","")}</td>'
        f'<td style="padding:8px;border:1px solid #e2e8f0;">{", ".join(sl.get("keywords") or [])}</td>'
        f'<td style="padding:8px;border:1px solid #e2e8f0;">{sl.get("section","")}</td></tr>'
        for sl in p.get("slides") or []
    )

    avoid = ", ".join(kw.get("avoid_in_body") or [])
    primary = ", ".join(kw.get("body_primary") or [])
    secondary = ", ".join(kw.get("body_secondary") or [])
    tags = ", ".join(kw.get("shopping_tags") or [])

    return f"""
<section id="{sku}" style="margin-bottom:48px;padding-bottom:32px;border-bottom:2px solid #e2e8f0;">
  <h2 style="color:{accent};font-size:20px;margin:0 0 8px;">{meta.get("title","")}</h2>
  <p style="margin:0 0 16px;color:#64748b;">SKU: <code>{sku}</code> · 
    <a href="{sku}.html" style="color:#2563eb;">상세 미리보기 →</a></p>

  <h3 style="font-size:16px;margin:24px 0 8px;">페이지 컨셉</h3>
  <table style="width:100%;border-collapse:collapse;font-size:14px;margin-bottom:16px;">
    <tr><td style="padding:8px;background:#f8fafc;width:120px;border:1px solid #e2e8f0;">컨셉명</td>
        <td style="padding:8px;border:1px solid #e2e8f0;"><strong>{concept.get("name","")}</strong></td></tr>
    <tr><td style="padding:8px;background:#f8fafc;border:1px solid #e2e8f0;">타깃</td>
        <td style="padding:8px;border:1px solid #e2e8f0;">{concept.get("persona","")}</td></tr>
    <tr><td style="padding:8px;background:#f8fafc;border:1px solid #e2e8f0;">약속</td>
        <td style="padding:8px;border:1px solid #e2e8f0;">{concept.get("promise","")}</td></tr>
    <tr><td style="padding:8px;background:#f8fafc;border:1px solid #e2e8f0;">톤</td>
        <td style="padding:8px;border:1px solid #e2e8f0;">{concept.get("tone","")}</td></tr>
    <tr><td style="padding:8px;background:#f8fafc;border:1px solid #e2e8f0;">구성 흐름</td>
        <td style="padding:8px;border:1px solid #e2e8f0;">{concept.get("flow","")}</td></tr>
  </table>

  <h3 style="font-size:16px;margin:24px 0 8px;">키워드 계획 (네이버 SEO)</h3>
  <table style="width:100%;border-collapse:collapse;font-size:13px;margin-bottom:16px;">
    <tr><td style="padding:8px;background:#fef3c7;width:140px;border:1px solid #e2e8f0;">쇼핑검색 상품명</td>
        <td style="padding:8px;border:1px solid #e2e8f0;">{kw.get("shopping_product_name","")}</td></tr>
    <tr><td style="padding:8px;background:#fef3c7;border:1px solid #e2e8f0;">쇼핑 태그</td>
        <td style="padding:8px;border:1px solid #e2e8f0;">{tags}</td></tr>
    <tr><td style="padding:8px;background:#dbeafe;border:1px solid #e2e8f0;">본문 핵심</td>
        <td style="padding:8px;border:1px solid #e2e8f0;">{primary}</td></tr>
    <tr><td style="padding:8px;background:#dbeafe;border:1px solid #e2e8f0;">본문 보조</td>
        <td style="padding:8px;border:1px solid #e2e8f0;">{secondary}</td></tr>
    <tr><td style="padding:8px;background:#fee2e2;border:1px solid #e2e8f0;">본문 금지</td>
        <td style="padding:8px;border:1px solid #e2e8f0;">{avoid}</td></tr>
  </table>

  <h3 style="font-size:16px;margin:24px 0 8px;">이미지 콘티 12장</h3>
  <table style="width:100%;border-collapse:collapse;font-size:13px;">
    <tr style="background:#0f172a;color:#fff;">
      <th style="padding:8px;width:40px;">#</th>
      <th style="padding:8px;">캡션</th>
      <th style="padding:8px;">촬영·소재 컨셉</th>
      <th style="padding:8px;">삽입 키워드</th>
      <th style="padding:8px;width:100px;">본문 구간</th>
    </tr>
    {slide_rows}
  </table>
</section>
"""


def build_plan_html(conti: dict, skus: list[str]) -> str:
    products = conti.get("products") or {}
    sections = "".join(build_plan_section(sku, products[sku]) for sku in skus if sku in products)
    nav = "".join(
        f'<a href="#{sku}" style="color:#93c5fd;margin-right:12px;">{products[sku]["meta"]["title"]}</a>'
        for sku in skus
        if sku in products
    )
    return f"""<!DOCTYPE html>
<html lang="ko"><head><meta charset="utf-8"/><meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>상세페이지 콘티 · 키워드 · 컨셉</title>
<style>
body{{font-family:'Malgun Gothic',sans-serif;background:#f1f5f9;margin:0;padding:0;}}
.top{{background:#0f172a;color:#fff;padding:16px 24px;position:sticky;top:0;z-index:10;}}
.wrap{{max-width:960px;margin:0 auto;padding:24px;background:#fff;min-height:100vh;}}
h1{{font-size:22px;margin:0 0 8px;}}
</style></head>
<body>
<div class="top">
  <div style="max-width:960px;margin:0 auto;">
    <strong>STEP 1 · 콘티·키워드·컨셉</strong> → 
    <a href="index.html" style="color:#86efac;">STEP 2 · 상세 미리보기</a>
  </div>
  <div style="max-width:960px;margin:8px auto 0;font-size:13px;">{nav}</div>
</div>
<div class="wrap">
<h1>듀라코트 퍼마코트 바이크 — 상세페이지 기획서</h1>
<p style="color:#64748b;">{conti.get("naver_seo","")}</p>
<p style="color:#64748b;font-size:13px;">소스: bike_detail_conti.json · 수정 후 <code>build_preview.py</code> 재실행</p>
{sections}
</div>
</body></html>"""


def wrap_preview(meta: dict, inner: str, nav_links: str) -> str:
    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>{meta["title"]} — 상세페이지 미리보기</title>
<style>
  body {{ margin:0; background:#f1f5f9; font-family:'Malgun Gothic',sans-serif; }}
  .nav {{ background:#0f172a; color:#fff; padding:12px 20px; position:sticky; top:0; z-index:10;
    display:flex; flex-wrap:wrap; gap:10px; align-items:center; }}
  .nav a {{ color:#93c5fd; text-decoration:none; font-size:14px; }}
  .nav .here {{ color:#fff; font-weight:700; }}
  .wrap {{ max-width:900px; margin:24px auto; background:#fff; padding:24px 20px 40px;
    box-shadow:0 4px 24px rgba(0,0,0,.08); border-radius:12px; }}
  .badge {{ display:inline-block; background:#e0e7ff; color:#3730a3; font-size:12px;
    padding:4px 10px; border-radius:99px; margin-bottom:16px; }}
</style>
</head>
<body>
<nav class="nav"><a href="plan.html">콘티·키워드</a> · {nav_links}</nav>
<div class="wrap">
<span class="badge">STEP 2 · 콘티 반영 상세 · 이미지 12장 · 860px</span>
<div style="max-width:860px;margin:0 auto;color:#222;line-height:1.7;font-size:15px;">
{inner}
</div>
</div>
</body>
</html>"""


def wrap_smartstore(inner: str) -> str:
    return (
        '<div style="max-width:860px;margin:0 auto;font-family:\'Malgun Gothic\',sans-serif;'
        'color:#222;line-height:1.7;font-size:15px;">\n'
        + inner.strip()
        + "\n</div>"
    )


def _validate_unique_images(manifest: dict) -> list[str]:
    seen: dict[str, str] = {}
    dupes: list[str] = []
    for sku, pdata in manifest.get("products", {}).items():
        for slot in pdata.get("slots", []):
            key = slot.get("local") or slot.get("unsplash", "")
            if not key:
                continue
            if key in seen:
                dupes.append(f"{sku}/{slot.get('id')}: {key} (already in {seen[key]})")
            else:
                seen[key] = f"{sku}/{slot.get('id')}"
    return dupes


def main() -> None:
    conti = _load_json(CONTI)
    manifest = _load_json(MANIFEST)
    raw_products = conti.get("products") or {}
    img_products = manifest.get("products") or {}

    dupes = _validate_unique_images(manifest)
    if dupes:
        print("WARNING: duplicate images across SKUs:", file=sys.stderr)
        for d in dupes:
            print(f"  - {d}", file=sys.stderr)

    PREVIEW.mkdir(parents=True, exist_ok=True)
    pages: list[tuple[str, dict, str, str]] = []
    skus: list[str] = []

    for sku, pdata in raw_products.items():
        slots = img_products.get(sku, {}).get("slots")
        if not slots or len(slots) < 12:
            print(f"SKIP {sku}: need 12 image slots", file=sys.stderr)
            continue
        meta = _flatten_product(pdata)
        body_preview = build_body(meta, slots, preview=True)
        body_store = build_body(meta, slots, preview=False)
        pages.append((sku, meta, body_preview, body_store))
        skus.append(sku)

    (PREVIEW / "plan.html").write_text(build_plan_html(conti, skus), encoding="utf-8")

    for sku, meta, body_preview, body_store in pages:
        links = ['<a href="index.html">목록</a>']
        for s2, m2, _, _ in pages:
            label = m2["title"]
            if s2 == sku:
                links.append(f'<span class="here">{label}</span>')
            else:
                links.append(f'<a href="{s2}.html">{label}</a>')
        html = wrap_preview(meta, body_preview, " · ".join(links))
        (PREVIEW / f"{sku}.html").write_text(html, encoding="utf-8")
        out = meta.get("out_sm") or f"store_detail_{sku}.html"
        (ROOT / out).write_text(wrap_smartstore(body_store), encoding="utf-8")

    index_items = "".join(
        f'<a href="{k}.html" style="display:block;padding:16px 20px;background:#fff;border-radius:10px;'
        f'text-decoration:none;color:#1e293b;border:1px solid #e2e8f0;margin-bottom:12px;">'
        f'<strong style="color:{m["accent"]};">{m["title"]}</strong>'
        f'<span style="display:block;font-size:13px;color:#64748b;margin-top:4px;">'
        f'{m.get("concept", {}).get("name", "")} · 이미지 12장</span></a>'
        for k, m, _, _ in pages
    )
    index = f"""<!DOCTYPE html>
<html lang="ko"><head><meta charset="utf-8"/><meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>퍼마코트 바이크 상세페이지 미리보기</title>
<style>body{{font-family:'Malgun Gothic',sans-serif;background:#f1f5f9;margin:0;padding:24px;}}
h1{{font-size:22px;color:#0f172a;}} p{{color:#64748b;}} .grid{{max-width:520px;}}
.cta{{display:inline-block;background:#2563eb;color:#fff;padding:12px 20px;border-radius:8px;
text-decoration:none;margin-bottom:20px;}}</style></head>
<body>
<a class="cta" href="plan.html">← STEP 1: 콘티·키워드·컨셉 보기</a>
<h1>STEP 2 · 상세페이지 미리보기</h1>
<p>콘티 확정 후 생성된 스마트스토어 본문 (860px).</p>
<div class="grid">{index_items}</div>
</body></html>"""
    (PREVIEW / "index.html").write_text(index, encoding="utf-8")
    print(f"Generated plan.html + {len(pages)} preview pages + smartstore HTML in {ROOT}")
    if dupes:
        print(f"  ({len(dupes)} duplicate image warning(s) — see stderr)")


if __name__ == "__main__":
    main()
