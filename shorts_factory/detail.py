# -*- coding: utf-8 -*-
"""쇼츠 plan → 스마트스토어 상세페이지 HTML."""

from __future__ import annotations

import asyncio
import html
import json
import re
from pathlib import Path
from typing import Any, Callable
from urllib.parse import quote

from shorts_factory.generator import _extract_json, _generate_text, load_products
from shorts_factory.detail_analyzer import (
    analyze_detail_plan,
    apply_analysis_to_detail,
    load_analysis,
    save_analysis,
)

LogFn = Callable[[str], None]

ACCENT = {"living": "#0d9488", "bike": "#2563eb", "auto": "#b45309"}


def _esc(s: str) -> str:
    return html.escape(str(s or ""))


def _build_detail_prompt(product: dict, plan: dict) -> str:
    kws = plan.get("input_keywords") or []
    kw_line = ", ".join(kws) if isinstance(kws, list) else str(kws)
    scenes = plan.get("scenes") or []
    scene_summary = "\n".join(
        f"- 장면{sc.get('scene_no')}: {sc.get('conti','')} / {sc.get('narration','')}"
        for sc in scenes[:8]
    )
    variants = ", ".join(product.get("variants") or [])
    forbidden = ", ".join(product.get("forbidden") or [])

    return f"""당신은 네이버 스마트스토어 상품 상세페이지 카피라이터입니다.
과장·최저가·1위·완벽 보장 표현 금지. HTML <strong> 태그로 키워드 1~2회만 강조.

【제품】
- 라인: {product.get("full_name")}
- 변형: {variants}
- 스펙: {product.get("truth")}
- 금지: {forbidden}

【쇼츠 콘티 요약】
주제: {plan.get("topic") or plan.get("video_title")}
후킹: {plan.get("hook_line")}
키워드: {kw_line}
{scene_summary}

반드시 아래 JSON만 출력:
{{
  "meta": {{
    "title": "상세 제목 (짧게)",
    "headline": "메인 헤드라인",
    "sub": "서브 카피 한 줄"
  }},
  "keywords": {{
    "shopping_product_name": "쇼핑검색용 상품명 40~50자",
    "shopping_tags": ["태그10개"],
    "body_primary": ["본문 핵심키워드 3~4개"],
    "body_secondary": ["보조키워드 3~4개"]
  }},
  "copy": {{
    "opening": "오프닝 2~3문장 HTML",
    "recommend": ["추천 대상 bullet 4개 HTML"],
    "section_before": "시공/사용 전후 설명",
    "section_wax": "왁스·일반제 vs 유리막 차이",
    "section_parts": "적용 부위·대상",
    "section_care": "관리·FAQ 전 안내"
  }},
  "spec_rows": [["항목","내용"], ...],
  "faq": [["질문","답변 HTML"], ...]
}}"""


def _fallback_detail(product: dict, plan: dict) -> dict:
    name = product.get("full_name") or product.get("label")
    line = product.get("product_line") or name
    hook = plan.get("hook_line") or plan.get("video_title") or name
    scenes = plan.get("scenes") or []
    narrs = [sc.get("narration") for sc in scenes if sc.get("narration")]
    kws = plan.get("input_keywords") or []
    if isinstance(kws, str):
        kws = [k.strip() for k in kws.split(",") if k.strip()]

    pid = product.get("id", "living")
    tags_map = {
        "living": ["리빙코트", "유리막코팅", "주방코팅", "욕실코팅", "발수코팅", "셀프코팅", "듀라코트", "나노코팅", "생활코팅", "홈케어"],
        "bike": ["바이크코팅", "오토바이코팅", "유리막", "발수코팅", "헬멧관리", "셀프코팅", "듀라코트", "퍼마코트", "도장면", "비딩"],
        "auto": ["자동차코팅", "유리막코팅", "발수코팅", "셀프디테일링", "차량관리", "듀라코트", "퍼마코트", "도장면", "비딩", "세차"],
    }
    primary_map = {
        "living": ["리빙코트", "유리막 코팅", "주방 코팅", "셀프 코팅"],
        "bike": ["바이크 코팅", "유리막 코팅", "셀프 코팅", "발수"],
        "auto": ["자동차 코팅", "유리막 코팅", "셀프 디테일링", "발수"],
    }

    opening = (
        f"{hook} <strong>{name}</strong>은(는) {line} 전용 <strong>유리막 코팅</strong>으로, "
        f"일상 공간에서 셀프 시공을 부담 없이 시작할 수 있도록 설계되었습니다."
    )
    recommend = narrs[:4] if narrs else [
        f"<strong>{primary_map.get(pid, ['코팅'])[0]}</strong>을 처음 써 보는 분",
        "발수·오염 관리가 번거로운 분",
        f"{line} 라인을 찾는 분",
        "소량·첫 시공으로 연습하려는 분",
    ]
    while len(recommend) < 4:
        recommend.append(recommend[-1])

    truth = product.get("truth") or "제품 안내 참조"
    spec_rows = [
        ["브랜드·라인", name],
        ["스펙", truth],
        ["용도", line],
        ["특징", "셀프 시공, 생활 밀착 실사 사용"],
    ]

    return {
        "meta": {
            "title": f"{product.get('label')} — 상세",
            "headline": hook.rstrip("!?.") or f"{line}, 이렇게 관리하세요",
            "sub": truth[:60] if truth else line,
        },
        "keywords": {
            "shopping_product_name": f"듀라코트 {line} {name} 유리막 코팅제 셀프",
            "shopping_tags": tags_map.get(pid, tags_map["living"])[:10],
            "body_primary": primary_map.get(pid, primary_map["living"]),
            "body_secondary": (kws[:4] if kws else ["발수", "비딩", "관리", "코팅"]),
        },
        "copy": {
            "opening": opening,
            "recommend": recommend[:4],
            "section_before": scenes[1].get("conti", "") if len(scenes) > 1 else "시공·사용 전후를 비교해 보세요.",
            "section_wax": "단기 광택용 왁스와 달리, <strong>유리막 코팅</strong>은 표면 위 피막으로 수분·오염 접촉을 줄이는 데 초점을 둡니다.",
            "section_parts": scenes[2].get("visual_desc", "") if len(scenes) > 2 else f"{line}에 맞는 부위에 소량 테스트 후 시공하세요.",
            "section_care": "시공 후에는 전용 관리 루틴을 권장합니다. 금지 성분·혼용 제품은 안내를 확인하세요.",
        },
        "spec_rows": spec_rows,
        "faq": [
            ["다른 라인과 같나요?", f"<strong>{line}</strong> 전용 제품이며, 금지 언급 제품과 혼용하지 않습니다."],
            ["셀프로 가능한가요?", "소량 테스트 후 <strong>셀프 시공</strong>이 가능합니다. 미경험 시 넓은 면적보다 작은 부위부터 권장합니다."],
            ["효과가 보장되나요?", "시공 환경·관리·사용 조건에 따라 달라질 수 있습니다."],
        ],
    }


async def generate_detail_content(
    plan: dict,
    *,
    use_llm: bool = False,
    log: LogFn | None = None,
) -> dict:
    log = log or (lambda m: None)
    products = load_products()
    pid = str(plan.get("product_id") or "living").lower()
    product = products.get(pid) or products.get("living") or {}

    if not use_llm:
        detail = _fallback_detail(product, plan)
        log("   상세페이지 카피 (템플릿)")
        return _enrich_detail(detail, product, plan)

    try:
        raw = await _generate_text(_build_detail_prompt(product, plan), log)
        detail = _extract_json(raw)
        detail = _normalize_detail(detail, product, plan)
        log("   상세페이지 카피 (LLM)")
    except Exception as e:
        log(f"   상세 LLM 실패 → 템플릿: {e}")
        detail = _fallback_detail(product, plan)

    return _enrich_detail(detail, product, plan)


def _normalize_detail(detail: dict, product: dict, plan: dict) -> dict:
    copy = detail.get("copy") or {}
    if not copy.get("opening"):
        return _fallback_detail(product, plan)
    detail.setdefault("meta", {})
    detail.setdefault("keywords", {})
    detail.setdefault("spec_rows", [])
    detail.setdefault("faq", [])
    return detail


def _enrich_detail(detail: dict, product: dict, plan: dict) -> dict:
    meta = detail.setdefault("meta", {})
    meta.setdefault("accent", ACCENT.get(product.get("id", ""), "#2563eb"))
    meta.setdefault("title", product.get("label"))
    if product.get("smartstore"):
        detail["smartstore_url"] = product["smartstore"]
    detail["product_id"] = product.get("id")
    detail["source_plan_title"] = plan.get("video_title") or plan.get("topic")
    slides = []
    for i, sc in enumerate(plan.get("scenes") or [], start=1):
        slides.append(
            {
                "no": i,
                "caption": f"{i:02d} {sc.get('subtitle') or sc.get('narration', '')[:20]}",
                "visual": sc.get("visual_desc") or sc.get("conti", ""),
                "keywords": [sc.get("search_keyword")] if sc.get("search_keyword") else [],
            }
        )
    detail["slides"] = slides
    return detail


def collect_image_paths(plan: dict, out_dir: Path) -> list[str]:
    paths: list[str] = []
    for sc in plan.get("scenes") or []:
        rel = str(sc.get("image_file") or "").replace("\\", "/")
        if not rel:
            continue
        if (out_dir / rel).is_file():
            paths.append(rel)
    if not paths:
        return []
    target = max(8, min(12, len(paths) + 4))
    while len(paths) < target:
        paths.append(paths[len(paths) % len(paths)])
    return paths[:12]


def _img_tag(src: str, caption: str = "") -> str:
    cap = (
        f'<p style="text-align:center;font-size:12px;color:#888;margin:-8px 0 20px;">{_esc(caption)}</p>'
        if caption
        else ""
    )
    return (
        f'<img src="{_esc(src)}" alt="" '
        f'style="width:100%;max-width:860px;display:block;margin:20px auto;border-radius:8px;'
        f'box-shadow:0 2px 12px rgba(0,0,0,.08);" loading="lazy" />{cap}'
    )


def _spec_table(rows: list[list[str]], accent: str) -> str:
    trs = "".join(
        f'<tr><td style="border:1px solid #ddd;padding:10px;width:32%;">{_esc(k)}</td>'
        f'<td style="border:1px solid #ddd;padding:10px;">{v}</td></tr>'
        for k, v in (rows or [])
    )
    return (
        f'<table style="width:100%;border-collapse:collapse;font-size:14px;margin:12px 0;">'
        f'<tr style="background:{accent};color:#fff;">'
        f'<th style="border:1px solid #ddd;padding:10px;text-align:left;">항목</th>'
        f'<th style="border:1px solid #ddd;padding:10px;text-align:left;">내용</th></tr>{trs}</table>'
    )


def _faq_table(faq: list[list[str]]) -> str:
    trs = "".join(
        f'<tr><td style="border:1px solid #ddd;padding:10px;width:35%;">{_esc(q)}</td>'
        f'<td style="border:1px solid #ddd;padding:10px;">{a}</td></tr>'
        for q, a in (faq or [])
    )
    return (
        f'<table style="width:100%;border-collapse:collapse;font-size:14px;margin:12px 0;">'
        f'<tr style="background:#f3f4f6;">'
        f'<th style="border:1px solid #ddd;padding:10px;">질문</th>'
        f'<th style="border:1px solid #ddd;padding:10px;">답변</th></tr>{trs}</table>'
    )


def _seo_block(detail: dict) -> str:
    kw = detail.get("keywords") or {}
    tags = ", ".join(kw.get("shopping_tags") or [])
    pname = kw.get("shopping_product_name", "")
    primary = ", ".join(kw.get("body_primary") or [])
    return (
        f'<div style="font-size:12px;color:#64748b;background:#f8fafc;border:1px dashed #cbd5e1;'
        f'padding:12px 14px;border-radius:8px;margin-bottom:20px;">'
        f'<strong style="color:#475569;">[쇼핑검색 탭 — 본문 미포함]</strong><br/>'
        f'상품명: {_esc(pname)}<br/>'
        f'태그: {_esc(tags)}<br/>'
        f'<span style="color:#94a3b8;">본문 핵심키워드: {_esc(primary)}</span></div>'
    )


def build_detail_body(detail: dict, image_paths: list[str], *, preview: bool) -> str:
    meta = detail.get("meta") or {}
    copy = detail.get("copy") or {}
    a = meta.get("accent", "#2563eb")
    slides = detail.get("slides") or []

    def cap(i: int, fallback: str = "") -> str:
        if i < len(slides):
            return slides[i].get("caption") or fallback
        return fallback

    imgs = image_paths or []
    if not imgs:
        placeholder = (
            '<div style="background:linear-gradient(135deg,#e2e8f0,#cbd5e1);'
            'height:200px;border-radius:8px;margin:20px auto;max-width:860px;'
            'display:flex;align-items:center;justify-content:center;color:#64748b;">'
            "② 스토리보드 이미지 생성 후 자동 반영</div>"
        )
        imgs = [""] * 8
        img = lambda i: placeholder if not image_paths else _img_tag(imgs[min(i, len(imgs) - 1)], cap(i))
    else:
        img = lambda i: _img_tag(imgs[min(i, len(imgs) - 1)], cap(i))

    h2 = lambda t: (
        f'<h2 style="font-size:22px;font-weight:700;margin:32px 0 12px;border-left:4px solid {a};'
        f'padding-left:12px;">{t}</h2>'
    )
    rec_li = "".join(f"<li>{item}</li>" for item in copy.get("recommend") or [])

    before_after = ""
    if len(imgs) >= 4:
        before_after = (
            '<div style="display:flex;gap:8px;flex-wrap:wrap;max-width:860px;margin:0 auto;">'
            f'<div style="flex:1;min-width:280px;">{img(2)}</div>'
            f'<div style="flex:1;min-width:280px;">{img(3)}</div></div>'
        )

    steps = ""
    if len(imgs) >= 9:
        steps = "".join(f'<div style="margin-bottom:8px;">{img(i)}</div>' for i in range(6, min(9, len(imgs))))

    seo = _seo_block(detail) if preview else ""

    return f"""
{seo}
{img(0)}
{h2(meta.get("headline", ""))}
<p style="font-size:16px;color:#444;text-align:center;margin-bottom:8px;">{_esc(meta.get("sub", ""))}</p>
<p>{copy.get("opening", "")}</p>
<p style="font-size:13px;color:#666;">※ 효과는 시공 환경·관리 습관에 따라 달라질 수 있습니다.</p>

{img(1) if len(imgs) > 1 else ""}
{h2("이런 분께 추천합니다")}
<ul style="padding-left:20px;">{rec_li}</ul>

{h2("사용 전후, 차이를 확인하세요")}
<p>{copy.get("section_before", "")}</p>
{before_after}

{img(4) if len(imgs) > 4 else ""}
{h2("왁스가 아닌, 유리막 코팅")}
<p>{copy.get("section_wax", "")}</p>

{img(5) if len(imgs) > 5 else ""}
{h2("제품 스펙")}
{_spec_table(detail.get("spec_rows") or [], a)}
<p>듀라코트·퍼마코트는 <strong>영국 수출</strong> 실적이 있는 라인입니다.</p>

{h2("적용·시공 부위")}
<p>{copy.get("section_parts", "")}</p>

{h2("셀프 시공 단계") if steps else ""}
{steps}

{img(min(7, len(imgs) - 1)) if len(imgs) > 7 else ""}
{h2("관리 & FAQ")}
<p>{copy.get("section_care", "")}</p>
{_faq_table(detail.get("faq") or [])}
<p style="margin-top:32px;font-size:13px;color:#666;text-align:center;">듀라코트 · 나눔랩</p>
"""


def wrap_detail_preview(title: str, inner: str, slug: str | None = None) -> str:
    dl = ""
    if slug:
        enc = quote(slug, safe="")
        dl = (
            f'<span class="dl-actions" data-detail-download>'
            f'<a href="/api/detail/download?slug={enc}&amp;kind=zip">ZIP 다운로드</a>'
            f'<a href="/api/detail/download?slug={enc}&amp;kind=html">HTML 저장</a>'
            f"</span>"
        )
    return f"""<!DOCTYPE html>
<html lang="ko"><head><meta charset="utf-8"/><meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>{_esc(title)} — 상세페이지 미리보기</title>
<style>
body{{margin:0;background:#f1f5f9;font-family:'Malgun Gothic',sans-serif;}}
.nav{{background:#0f172a;color:#fff;padding:12px 20px;position:sticky;top:0;z-index:10;display:flex;align-items:center;flex-wrap:wrap;gap:8px 12px;}}
.nav a{{color:#93c5fd;text-decoration:none;font-size:14px;}}
.nav .dl-actions a{{margin-left:8px;padding:4px 10px;background:#1e40af;border-radius:6px;color:#fff;font-size:13px;}}
.nav .dl-actions a:hover{{background:#2563eb;}}
.wrap{{max-width:900px;margin:24px auto;background:#fff;padding:24px 20px 40px;
box-shadow:0 4px 24px rgba(0,0,0,.08);border-radius:12px;}}
.badge{{display:inline-block;background:#e0e7ff;color:#3730a3;font-size:12px;
padding:4px 10px;border-radius:99px;margin-bottom:16px;}}
</style></head>
<body>
<nav class="nav"><a href="../studio.html">← 스튜디오</a><strong>{_esc(title)}</strong>{dl}</nav>
<div class="wrap">
<span class="badge">스마트스토어 상세 · 860px · 쇼핑검색 메타는 미리보기에만 표시</span>
<div style="max-width:860px;margin:0 auto;color:#222;line-height:1.7;font-size:15px;">
{inner}
</div></div></body></html>"""


def wrap_smartstore(inner: str) -> str:
    return (
        '<div style="max-width:860px;margin:0 auto;font-family:\'Malgun Gothic\',sans-serif;'
        'color:#222;line-height:1.7;font-size:15px;">\n'
        + inner.strip()
        + "\n</div>"
    )


async def write_detail_outputs_async(
    plan: dict,
    slug: str,
    out_dir: Path,
    *,
    use_llm: bool = False,
    strategy: str | None = None,
    competitor_notes: str = "",
    selected_hook: str | None = None,
    log: LogFn | None = None,
) -> dict:
    log = log or (lambda m: None)
    out_dir.mkdir(parents=True, exist_ok=True)

    from shorts_factory.competitor_analyzer import load_competitor_benchmark

    benchmark = load_competitor_benchmark(out_dir)
    analysis = analyze_detail_plan(
        plan,
        strategy_override=strategy,
        competitor_notes=competitor_notes,
        competitor_benchmark=benchmark,
        selected_hook=selected_hook,
    )
    save_analysis(out_dir, analysis)
    log("   니즈·후킹 분석 (로컬, API 없음)")

    detail = await generate_detail_content(plan, use_llm=use_llm, log=log)
    detail = apply_analysis_to_detail(detail, analysis)
    images = collect_image_paths(plan, out_dir)
    body_preview = build_detail_body(detail, images, preview=True)
    body_store = build_detail_body(detail, images, preview=False)

    title = (detail.get("meta") or {}).get("title") or slug
    (out_dir / "detail.json").write_text(
        json.dumps(detail, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (out_dir / "detail_preview.html").write_text(
        wrap_detail_preview(title, body_preview, slug=slug), encoding="utf-8"
    )
    (out_dir / "detail_smartstore.html").write_text(
        wrap_smartstore(body_store), encoding="utf-8"
    )

    plan = dict(plan)
    plan["detail_analyzed"] = True
    plan["detail_ready"] = True
    plan["detail_file"] = "detail_preview.html"
    plan["detail_smartstore_file"] = "detail_smartstore.html"
    plan["detail_analysis_file"] = "detail_analysis.json"
    (out_dir / "plan.json").write_text(
        json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    log(f"   상세페이지 저장: detail_preview.html ({len(images)}장 이미지)")
    return {"ok": True, "plan": plan, "detail": detail, "images_used": len(images), "analysis": analysis}


def write_detail_outputs(
    plan: dict,
    slug: str,
    out_dir: Path,
    *,
    use_llm: bool = False,
    strategy: str | None = None,
    competitor_notes: str = "",
    selected_hook: str | None = None,
    log: LogFn | None = None,
) -> dict:
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(
            write_detail_outputs_async(
                plan,
                slug,
                out_dir,
                use_llm=use_llm,
                strategy=strategy,
                competitor_notes=competitor_notes,
                selected_hook=selected_hook,
                log=log,
            )
        )
    finally:
        loop.close()
