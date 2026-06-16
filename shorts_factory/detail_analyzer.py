# -*- coding: utf-8 -*-
"""API 없이 쇼츠 plan + 제품 데이터로 상세페이지 니즈·후킹·전략 분석."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from shorts_factory.generator import load_products

_ROOT = Path(__file__).resolve().parents[1]
_PLANNING_PATH = _ROOT / "data" / "shorts_factory" / "detail_planning.json"

_STRATEGY_KEYWORDS: dict[str, tuple[str, ...]] = {
    "target": ("타겟", "맞춤", "1인", "전문가", "페르소나", "라이더", "주부", "입문"),
    "fear": ("공포", "손해", "놓치", "불편", "걱정", "번거", "피로", "지저분", "때", "자국"),
    "benefit": ("변화", "후", "결과", "편해", "비딩", "발수", "체감", "간단", "쓱", "맺"),
    "data": ("수치", "%", "함량", "스펙", "14%", "28%", "원액", "폴리실라잔", "티탄", "레진"),
    "story": ("후기", "리뷰", "사연", "브랜드", "영국", "수출", "나눔랩"),
    "value": ("할인", "혜택", "증정", "한정", "가성비", "입문", "부담"),
}

_PILLAR_HINTS: list[tuple[int, str, tuple[str, ...]]] = [
    (1, "대표 이미지 한 줄 정의", ("히어로", "대표", "한줄", "headline", "hook")),
    (1, "문제 제기 (Pain Point)", ("pain", "고민", "불편", "문제", "번거", "지저분", "때")),
    (1, "비포 & 애프터 (B&A)", ("before", "after", "전후", "비포", "애프터", "b&a")),
    (2, "구체적 수치 성능 증명", ("%", "함량", "14", "28", "60", "수치", "스펙")),
    (2, "안전성 및 인증 증거", ("인증", "안전", "금지", "혼용", "전용")),
    (2, "독보적 차별화 요소", ("차별", "유리막", "왁스", "리빙", "바이크 전용", "자동차 전용")),
    (3, "직관적 구성품 안내", ("구성", "라인업", "퀵", "티탄", "레진", "variant")),
    (3, "단계별 시공 가이드", ("시공", "단계", "도포", "세척", "apply", "wash")),
    (3, "실패 방지 꿀팁", ("꿀팁", "테스트", "소량", "건조", "주의", "실패")),
    (4, "전략적 후기 배치", ("후기", "리뷰", "만족")),
    (4, "전문성 있는 브랜드 스토리", ("듀라코트", "브랜드", "영국", "수출", "나눔랩")),
    (4, "적극적 Q&A/AS 대응", ("faq", "질문", "답변", "as", "교환", "환불")),
    (5, "명확한 행동 촉구 (CTA)", ("cta", "구매", "지금", "스마트스토어", "smartstore")),
]


def _load_planning() -> dict:
    if _PLANNING_PATH.is_file():
        return json.loads(_PLANNING_PATH.read_text(encoding="utf-8"))
    return {"pillars": [], "strategies": [], "personas": {}}


def _norm(s: str) -> str:
    return re.sub(r"\s+", "", (s or "").lower())


def _plan_blob(plan: dict) -> str:
    parts = [
        plan.get("topic") or "",
        plan.get("hook_line") or "",
        plan.get("video_title") or "",
    ]
    for sc in plan.get("scenes") or []:
        parts.extend(
            [
                sc.get("narration") or "",
                sc.get("subtitle") or "",
                sc.get("conti") or "",
                sc.get("visual_desc") or "",
                sc.get("search_keyword") or "",
            ]
        )
    kws = plan.get("input_keywords") or []
    if isinstance(kws, list):
        parts.extend(str(k) for k in kws)
    return " ".join(parts)


def infer_strategy(text: str) -> str:
    t = text.lower()
    scores = {k: 0 for k in _STRATEGY_KEYWORDS}
    for sid, keys in _STRATEGY_KEYWORDS.items():
        for kw in keys:
            if kw.lower() in t:
                scores[sid] += 1
    best = "benefit"
    mx = -1
    for sid, sc in scores.items():
        if sc > mx:
            mx = sc
            best = sid
    return best


def _scene_flows(plan: dict) -> list[dict]:
    flows: list[dict] = []
    pillar_map = [1, 1, 1, 2, 2, 3, 3, 3, 4, 4, 5]
    checklist_defaults = [
        "문제 제기 (Pain Point)",
        "비포 & 애프터 (B&A)",
        "대표 이미지 한 줄 정의",
        "독보적 차별화 요소",
        "구체적 수치 성능 증명",
        "단계별 시공 가이드",
        "직관적 구성품 안내",
        "실패 방지 꿀팁",
        "전문성 있는 브랜드 스토리",
        "적극적 Q&A/AS 대응",
        "명확한 행동 촉구 (CTA)",
    ]
    for i, sc in enumerate(plan.get("scenes") or []):
        idx = min(i, len(pillar_map) - 1)
        flows.append(
            {
                "order": i + 1,
                "sectionTitle": sc.get("subtitle") or f"장면 {sc.get('scene_no', i+1)}",
                "copyDraft": sc.get("narration") or "",
                "visualDirection": sc.get("visual_desc") or sc.get("conti") or "",
                "planningPillar": pillar_map[idx],
                "checklistItem": checklist_defaults[idx] if i < len(checklist_defaults) else "",
                "topic": sc.get("search_keyword") or "",
            }
        )
    return flows


def audit_checklist(flows: list[dict], pillars: list[dict]) -> dict:
    covered: dict[int, list[str]] = {p["id"]: [] for p in pillars}
    flow_orders: dict[int, list[int]] = {p["id"]: [] for p in pillars}

    for flow in flows:
        pid = int(flow.get("planningPillar") or 0)
        if pid not in covered:
            continue
        if flow["order"] not in flow_orders[pid]:
            flow_orders[pid].append(flow["order"])
        item = (flow.get("checklistItem") or "").strip()
        if item and item not in covered[pid]:
            covered[pid].append(item)

    blob = _norm(" ".join(
        f"{f.get('checklistItem','')} {f.get('sectionTitle','')} {f.get('copyDraft','')}"
        for f in flows
    ))

    missing: list[dict] = []
    coverage: list[dict] = []
    for p in pillars:
        entry = {
            "pillarId": p["id"],
            "pillarTitle": p["title"],
            "coveredItems": covered.get(p["id"], []),
            "flowOrders": flow_orders.get(p["id"], []),
        }
        coverage.append(entry)
        for item in p.get("items") or []:
            hit = any(
                _norm(item[:4]) in _norm(c) or _norm(c[:4]) in _norm(item)
                for c in entry["coveredItems"]
            )
            if not hit:
                for _, label, hints in _PILLAR_HINTS:
                    if label == item and any(h in blob for h in hints):
                        hit = True
                        break
            if not hit:
                missing.append({"pillarTitle": p["title"], "item": item})

    return {
        "complete": len(missing) == 0,
        "missing": missing,
        "covered": coverage,
    }


def _hook_candidates(plan: dict, product: dict, persona: dict) -> list[str]:
    hooks: list[str] = []
    if plan.get("hook_line"):
        hooks.append(str(plan["hook_line"]).strip())
    for sc in (plan.get("scenes") or [])[:3]:
        n = (sc.get("narration") or sc.get("subtitle") or "").strip()
        if n and n not in hooks:
            hooks.append(n if n.endswith("?") else f"{n}?")
    for h in persona.get("hooks") or []:
        if h not in hooks:
            hooks.append(h)
    name = product.get("label") or product.get("full_name") or "제품"
    if len(hooks) < 5:
        hooks.append(f"{name}, 셀프로 시작하는 유리막 코팅")
    return hooks[:8]


def _merge_competitor_benchmark(
    report: dict[str, Any],
    benchmark: dict | None,
    extra_notes: str = "",
) -> dict[str, Any]:
    """타사 벤치마크 JSON을 분석 리포트에 병합."""
    if not benchmark:
        return report

    summary = benchmark.get("summary") or {}
    profiles = [p for p in (benchmark.get("profiles") or []) if p.get("ok")]
    common = summary.get("commonSections") or []
    gaps = summary.get("gapsToExploit") or []
    flow = summary.get("recommendedFlow") or ""

    blob = benchmark.get("competitorNotesBlob") or ""
    if extra_notes.strip():
        blob = (blob + "\n" + extra_notes.strip()).strip()

    patterns = flow
    if profiles:
        titles = " · ".join(p.get("title", "")[:40] for p in profiles[:3])
        patterns = f"벤치마크 {len(profiles)}건 ({titles}). 흐름: {flow}"

    own = benchmark.get("ownProductProfile") or {}
    report["competitorBenchmark"] = {
        "urls": benchmark.get("urls") or [],
        "ownProductUrl": benchmark.get("ownProductUrl"),
        "analyzed": summary.get("analyzed", len(profiles)),
        "commonSections": common,
        "gapsToExploit": gaps,
        "recommendedFlow": flow,
        "profiles": [
            {
                "domain": p.get("domain"),
                "title": p.get("title"),
                "sections": p.get("sectionLabels") or [],
                "url": p.get("url"),
            }
            for p in profiles
        ],
        "ownProduct": {
            "url": own.get("url"),
            "title": own.get("title"),
            "sections": own.get("sectionLabels") or [],
            "ok": own.get("ok"),
        }
        if own
        else None,
        "matrix": benchmark.get("benchmark") or [],
    }

    if own.get("ok") and own.get("sectionLabels"):
        gap_close = list(report.get("sellingPointsComparison", {}).get("gapToClose") or [])
        missing_own = [
            lbl
            for lbl in (benchmark.get("benchmark") or [])
            if lbl.get("recommended") and lbl.get("label") not in (own.get("sectionLabels") or [])
        ]
        for row in missing_own[:3]:
            label = row.get("label", "")
            if label and label not in gap_close:
                gap_close.append(f"우리 상세에 {label} 섹션 보강")
        if gap_close:
            report.setdefault("sellingPointsComparison", {})["gapToClose"] = gap_close[:5]

    if common:
        report.setdefault("sellingPointsComparison", {})["competitorCommon"] = common[:6]
    if gaps:
        unmet = list(report.get("needsComparison", {}).get("unmetByCompetitors") or [])
        for g in gaps[:3]:
            if g not in unmet:
                unmet.append(f"타사 대비 {g} 섹션 약함 → 우리가 강조")
        report.setdefault("needsComparison", {})["unmetByCompetitors"] = unmet[:5]

    deep = report.setdefault("hookingStrategyDeepDive", {})
    deep["competitorPatterns"] = patterns or deep.get("competitorPatterns", "")
    if common:
        deep["scrollTriggers"] = list(dict.fromkeys(
            (deep.get("scrollTriggers") or [])
            + [f"타사 공통: {c}" for c in common[:3]]
        ))[:6]

    win = report.get("winningStrategy") or ""
    if flow and flow not in win:
        report["winningStrategy"] = f"{win} · 레퍼런스 흐름: {flow}"

    base_summary = report.get("summary") or ""
    if summary.get("analyzed"):
        report["summary"] = (
            f"{base_summary} 타사 {summary['analyzed']}건 벤치마크 반영."
        ).strip()

    if blob:
        report["competitorNotesUsed"] = blob[:2000]
    return report


def analyze_detail_plan(
    plan: dict,
    *,
    strategy_override: str | None = None,
    competitor_notes: str = "",
    competitor_benchmark: dict | None = None,
    selected_hook: str | None = None,
) -> dict[str, Any]:
    """plan + products.json 기반 로컬 분석 (LLM/API 없음)."""
    planning = _load_planning()
    pillars = planning.get("pillars") or []
    strategies_meta = planning.get("strategies") or []

    products = load_products()
    pid = str(plan.get("product_id") or "living").lower()
    product = products.get(pid) or products.get("living") or {}
    persona = (planning.get("personas") or {}).get(pid) or {}

    blob = _plan_blob(plan)
    bench_blob = (competitor_benchmark or {}).get("competitorNotesBlob") or ""
    if bench_blob:
        blob += " " + bench_blob
    if competitor_notes.strip():
        blob += " " + competitor_notes.strip()

    recommended = strategy_override or infer_strategy(blob)
    if recommended not in _STRATEGY_KEYWORDS:
        recommended = "benefit"

    flows = _scene_flows(plan)
    checklist = audit_checklist(flows, pillars)

    pains = list(persona.get("pains") or [])
    for sc in (plan.get("scenes") or [])[:2]:
        t = sc.get("narration") or sc.get("conti") or ""
        if t and len(t) > 8 and t not in pains:
            pains.append(t[:80])

    needs = list(persona.get("needs") or [])
    truth = product.get("truth") or ""
    if truth and truth not in needs:
        needs.insert(0, truth)

    selling: list[str] = []
    if product.get("truth"):
        selling.append(product["truth"])
    selling.append(f"{product.get('product_line') or product.get('label')} 전용 라인")
    if product.get("variants"):
        selling.append("라인업: " + ", ".join(product["variants"][:4]))
    forbidden = product.get("forbidden") or []
    if forbidden:
        selling.append(f"혼용 금지: {', '.join(forbidden[:3])}")

    hooks = _hook_candidates(plan, product, persona)
    if selected_hook and selected_hook.strip():
        hook_main = selected_hook.strip()
        hooks = [hook_main] + [h for h in hooks if h != hook_main]
    first_scene = (plan.get("scenes") or [{}])[0]
    visual_hook = first_scene.get("visual_desc") or first_scene.get("conti") or persona.get("hooks", [""])[0]

    kws = plan.get("input_keywords") or []
    if isinstance(kws, str):
        kws = [k.strip() for k in kws.split(",") if k.strip()]

    strategy_name = next(
        (s["name"] for s in strategies_meta if s.get("id") == recommended),
        recommended,
    )

    check_status = "100%" if checklist["complete"] else f"{len(checklist['missing'])}항목 보완"
    report = {
        "source": "local_analyzer",
        "api_free": True,
        "product_id": pid,
        "product_name": product.get("full_name") or product.get("label"),
        "persona": {
            "label": persona.get("label") or product.get("label"),
            "pains": pains[:6],
            "needs": needs[:6],
        },
        "ourProduct": {
            "customerNeeds": " · ".join(needs[:4]),
            "sellingPoints": " · ".join(selling[:4]),
            "hookingStrategy": hooks[0] if hooks else plan.get("hook_line") or "",
            "differentiation": truth or f"{product.get('product_line')} 전용, 타 라인 혼용 금지",
        },
        "needsComparison": {
            "sharedNeeds": needs[:3],
            "unmetByCompetitors": [
                "제품 라인별 전용성(리빙/바이크/자동차 혼동 방지)",
                "쇼츠·상세 일관된 스토리라인",
            ],
            "ourAdvantage": f"{product.get('brand', '듀라코트')} {product.get('product_line')} 전용 + 셀프 시공 가이드",
        },
        "sellingPointsComparison": {
            "competitorCommon": ["발수", "코팅", "셀프", "세차"],
            "ourUnique": selling[:4],
            "gapToClose": checklist["missing"][:3] if checklist["missing"] else [],
        },
        "hookingStrategyDeepDive": {
            "competitorPatterns": competitor_notes.strip()
            or "일반 스마트스토어: 히어로 이미지 → Pain → 전후 → 스펙 → FAQ → CTA 순",
            "recommendedHook": hooks[0],
            "first3Seconds": hooks[0],
            "painAgitation": pains[0] if pains else "",
            "visualHook": visual_hook,
            "copyHooks": hooks,
            "scrollTriggers": [
                "전후 비교 이미지",
                "비딩·발수 클로즈업",
                "스펙 표",
            ],
            "psychologicalTriggers": ["공감(Pain)", "시각 증거(B&A)", "리스크 완화(FAQ)"],
        },
        "recommendedStrategyId": recommended,
        "recommendedStrategyName": strategy_name,
        "features": [p["title"] for p in pillars],
        "summary": (
            f"「{product.get('label')}」 — {strategy_name} 전략. "
            f"니즈 {len(needs)}건, 후킹 {len(hooks)}안, "
            f"기획 지침 {check_status}."
        ),
        "winningStrategy": (
            f"{hooks[0]} → {needs[0] if needs else '핵심 니즈'} 해소 → "
            f"{selling[0] if selling else 'USP'} → FAQ·CTA"
        ),
        "checklist": checklist,
        "flows": flows,
        "seoKeywords": kws[:10],
        "pillars": pillars,
        "strategies": strategies_meta,
    }
    return _merge_competitor_benchmark(report, competitor_benchmark, competitor_notes)


def save_analysis(slug_dir: Path, analysis: dict) -> Path:
    slug_dir.mkdir(parents=True, exist_ok=True)
    path = slug_dir / "detail_analysis.json"
    path.write_text(json.dumps(analysis, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def load_analysis(slug_dir: Path) -> dict | None:
    path = slug_dir / "detail_analysis.json"
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def apply_analysis_to_detail(detail: dict, analysis: dict) -> dict:
    """분석 결과를 detail.json 카피에 반영."""
    if not analysis:
        return detail
    hooks = analysis.get("hookingStrategyDeepDive") or {}
    our = analysis.get("ourProduct") or {}
    meta = detail.setdefault("meta", {})
    if hooks.get("recommendedHook"):
        meta["headline"] = hooks["recommendedHook"]
    if our.get("differentiation"):
        meta["sub"] = our["differentiation"][:80]
    kw = detail.setdefault("keywords", {})
    pname = detail.get("product_id") or analysis.get("product_id")
    if our.get("customerNeeds") and not kw.get("shopping_product_name"):
        line = analysis.get("product_name") or ""
        kw["shopping_product_name"] = f"듀라코트 {line} 유리막 코팅제 셀프"[:50]
    copy = detail.setdefault("copy", {})
    if hooks.get("recommendedHook") and not copy.get("opening"):
        copy["opening"] = hooks["recommendedHook"]
    elif hooks.get("recommendedHook"):
        hook = hooks["recommendedHook"]
        if hook not in (copy.get("opening") or ""):
            copy["opening"] = f"{hook} {copy.get('opening', '')}".strip()
    pains = (analysis.get("persona") or {}).get("pains") or []
    rec = copy.get("recommend") or []
    if pains and isinstance(rec, list):
        merged = []
        for i, p in enumerate(pains[:4]):
            merged.append(p if p.startswith("<") else f"<strong>{p[:40]}</strong>")
        while len(merged) < 4 and rec:
            merged.append(rec[len(merged) % len(rec)])
        copy["recommend"] = merged[:4]
    detail["analysis"] = {
        "strategy": analysis.get("recommendedStrategyId"),
        "strategyName": analysis.get("recommendedStrategyName"),
        "appliedHook": hooks.get("recommendedHook") or meta.get("headline"),
        "customerNeeds": our.get("customerNeeds"),
        "sellingPoints": our.get("sellingPoints"),
        "winningStrategy": analysis.get("winningStrategy"),
        "api_free": True,
    }
    if analysis.get("needsComparison", {}).get("ourAdvantage"):
        copy["section_before"] = (
            f"{copy.get('section_before', '')} "
            f"{analysis['needsComparison']['ourAdvantage']}"
        ).strip()
    return detail
