"""
keyword_opportunity_finder.py
==============================
520위 밖 상품들의 10위권 진입을 위한 틈새 키워드 발굴기

전략:
  1. 상품별 롱테일 키워드 조합 생성
  2. 각 키워드의 경쟁도(1페이지 상품 수) 실시간 측정
  3. 기회 점수 계산 → 상위 키워드 추출
  4. config.json keywords 자동 업데이트

사용법:
    python keyword_opportunity_finder.py
    python keyword_opportunity_finder.py --product "나눔랩 코팅제 A"
    python keyword_opportunity_finder.py --apply   # config.json 자동 적용
"""

import sys
import os
import json
import re
import time
import argparse
from datetime import datetime
from urllib.parse import quote

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)
    sys.stderr.reconfigure(encoding="utf-8", line_buffering=True)

try:
    import requests
except ImportError:
    print("pip install requests")
    sys.exit(1)

# ── 경로 설정 ────────────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, "config.json")
REPORT_PATH = os.path.join(BASE_DIR, "keyword_opportunity_report.json")

MOBILE_UA = (
    "Mozilla/5.0 (Linux; Android 14; SM-S928N) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Mobile Safari/537.36"
)

# ── 상품별 키워드 시드 ───────────────────────────────────────────
PRODUCT_KEYWORD_SEEDS = {
    # 상품명 일부 → (핵심 카테고리, 속성 조합들)
    "퍼마코트": {
        "core": ["퍼마코트", "자동차코팅제", "유리막코팅"],
        "attributes": [
            "셀프", "DIY", "추천", "효과", "사용법", "후기",
            "지속력", "발수", "신차", "중고차", "가성비",
            "직접", "집에서", "쉬운", "초보", "입문",
        ],
        "long_tail_templates": [
            "{attr} {core}",
            "{core} {attr}",
            "{core} 시공 방법",
            "{core} 종류 비교",
            "차 {core} 직접 하는 법",
            "셀프 {core} 순서",
            "{core} 뭐가 좋을까",
            "{attr} 자동차 코팅제 추천",
        ],
    },
    "리빙코트": {
        "core": ["리빙코트", "실내코팅", "가구코팅"],
        "attributes": [
            "셀프", "DIY", "추천", "가성비", "후기",
            "나무 가구", "원목", "가죽 소파", "주방", "욕실",
            "집에서", "쉬운", "투명", "광택",
        ],
        "long_tail_templates": [
            "{attr} {core}",
            "{core} {attr}",
            "가구 {core} 방법",
            "{core} 추천 제품",
            "셀프 {core} 하는 법",
            "{core} 종류",
            "집에서 {core} 순서",
        ],
    },
    "코팅제": {
        "core": ["자동차코팅제", "유리막코팅제", "차량코팅제"],
        "attributes": [
            "셀프", "추천", "가성비", "효과 좋은", "후기",
            "초보", "쉬운", "입문", "직접", "DIY",
            "신차", "중고차", "검은색차", "흰색차",
            "장마철", "여름", "겨울", "비오는날",
            "지속력", "발수", "광택", "보호",
        ],
        "long_tail_templates": [
            "셀프 {core} 추천",
            "{attr} {core}",
            "{core} {attr}",
            "{core} 고르는 법",
            "차 {core} 직접 하기",
            "{attr} 차 코팅",
            "신차 {core} 순서",
            "{core} 뭐가 좋아요",
            "{core} 브랜드 비교",
            "유리막 {attr} 코팅",
        ],
    },
    "세정": {
        "core": ["세차용품", "차량세정제", "자동차세정제"],
        "attributes": [
            "추천", "가성비", "셀프세차", "셀프", "후기",
            "찌든때", "물때", "철분제거", "클리너",
            "실내", "외부", "유리", "타이어",
            "쉬운", "집에서", "초보",
        ],
        "long_tail_templates": [
            "셀프세차 {attr} {core}",
            "{core} {attr}",
            "{attr} {core} 추천",
            "셀프 {core} 방법",
            "차 {attr} 제거 방법",
            "{core} 종류 정리",
            "{attr} 자동차 세정 방법",
        ],
    },
}

# 공통 경쟁 낮은 접미어 (롱테일 확장용)
UNIVERSAL_LONGTAIL_SUFFIXES = [
    "가격 비교", "어떤거 살까", "어떤게 좋아요", "고르는 법",
    "사용 후기", "추천 제품", "처음 사용법", "직접 해봤어요",
    "전후 비교", "몇 번 써야해요", "지속 기간", "비추천 이유",
]


def load_config():
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def save_config(config):
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)


def _shopping_url(keyword, start=1):
    return (
        f"https://m.search.naver.com/search.naver?"
        f"query={quote(keyword.strip())}&where=m_shop&start={start}"
    )


def _extract_pids(html):
    seen, ordered = set(), []
    for pid in re.findall(r"smartstore\.naver\.com/[^\s\"']+/products/(\d+)", html):
        if pid not in seen:
            seen.add(pid); ordered.append(pid)
    for pid in re.findall(r"/products/(\d+)", html):
        if pid not in seen:
            seen.add(pid); ordered.append(pid)
    return ordered


def measure_competition(keyword):
    """
    키워드의 경쟁 강도 측정.
    반환: {
        'product_count': 1페이지 상품 수,
        'ad_ratio': 광고 비율 추정,
        'score': 기회 점수 (높을수록 유리)
    }
    """
    headers = {"User-Agent": MOBILE_UA, "Accept-Language": "ko-KR,ko;q=0.9"}
    try:
        res = requests.get(_shopping_url(keyword), headers=headers, timeout=15)
        if res.status_code != 200:
            return None
        html = res.text
        pids = _extract_pids(html)
        count = len(pids)

        # 광고 태그 추정
        ad_count = len(re.findall(r'class="[^"]*_ad[^"]*"', html, re.I))
        ad_count = min(ad_count, count) if count else 0

        # 기회 점수 (낮은 경쟁 = 높은 점수)
        # 10개 미만: 90점 이상 (레드오션 탈피)
        # 10~20개: 70~85점
        # 20~40개: 50~70점
        # 40개 초과: 50점 이하
        if count == 0:
            score = 20  # 결과 없음 = 수요 없음
        elif count <= 10:
            score = 95 - count * 1
        elif count <= 20:
            score = 85 - (count - 10) * 1.5
        elif count <= 40:
            score = 70 - (count - 20) * 1
        else:
            score = max(10, 50 - (count - 40) * 0.5)

        return {
            "product_count": count,
            "ad_count": ad_count,
            "opportunity_score": round(score, 1),
            "competition_level": (
                "낮음" if score >= 75 else
                "보통" if score >= 55 else
                "높음" if score >= 35 else "매우 높음"
            ),
        }
    except Exception:
        return None


def generate_longtail_keywords(product_name, product_id):
    """상품명 기반 롱테일 키워드 후보 생성"""
    candidates = set()

    # 상품에 맞는 시드 찾기
    matched_seed = None
    for seed_key, seed_data in PRODUCT_KEYWORD_SEEDS.items():
        if seed_key in product_name:
            matched_seed = seed_data
            break

    if matched_seed is None:
        # 기본 코팅제 시드 사용
        matched_seed = PRODUCT_KEYWORD_SEEDS["코팅제"]

    cores = matched_seed["core"]
    attrs = matched_seed["attributes"]
    templates = matched_seed["long_tail_templates"]

    for core in cores:
        for attr in attrs:
            for tpl in templates:
                kw = tpl.replace("{core}", core).replace("{attr}", attr).strip()
                if 4 <= len(kw) <= 30:
                    candidates.add(kw)
        # 공통 롱테일 접미어
        for suffix in UNIVERSAL_LONGTAIL_SUFFIXES:
            candidates.add(f"{core} {suffix}")

    return list(candidates)


def analyze_product_opportunities(product, top_n=15):
    """
    한 상품에 대해 키워드 기회를 분석하고 상위 N개 반환.
    """
    pid = str(product.get("id", ""))
    name = product.get("name", pid)

    print(f"\n🔍 [{name}] 키워드 기회 분석 중...")
    candidates = generate_longtail_keywords(name, pid)
    print(f"   후보 키워드 {len(candidates)}개 생성됨")

    results = []
    for i, kw in enumerate(candidates):
        comp = measure_competition(kw)
        if comp is None:
            continue
        results.append({
            "keyword": kw,
            "product_id": pid,
            "product_name": name,
            **comp,
        })
        if i < len(candidates) - 1:
            time.sleep(0.4)
        if (i + 1) % 10 == 0:
            print(f"   {i + 1}/{len(candidates)} 완료...")

    # 기회 점수 순 정렬
    results.sort(key=lambda x: x["opportunity_score"], reverse=True)

    # 상품 수가 0인 (수요 없는) 키워드 제거
    results = [r for r in results if r["product_count"] > 0]

    top = results[:top_n]
    print(f"   ✅ TOP {top_n} 키워드 선정 완료")
    for r in top[:5]:
        lvl = r["competition_level"]
        cnt = r["product_count"]
        sc = r["opportunity_score"]
        print(f"      • {r['keyword']!r} — 경쟁 {lvl} ({cnt}개) | 점수 {sc}")

    return top


def run_full_analysis(target_products=None, apply_to_config=False):
    """
    모든 미노출 상품에 대해 키워드 기회 분석 실행.
    target_products: None이면 config의 모든 상품 대상.
    apply_to_config: True면 발굴된 키워드를 config.json에 추가.
    """
    config = load_config()
    products = config.get("products", [])

    if target_products:
        products = [p for p in products if p.get("name") in target_products]

    if not products:
        print("❌ 분석할 상품이 없습니다.")
        return {}

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"\n{'='*60}")
    print(f"🎯 나눔랩 키워드 기회 발굴기 — {now}")
    print(f"{'='*60}")
    print(f"대상 상품 {len(products)}개 분석 시작\n")

    all_results = {}
    new_keywords_for_config = []

    for product in products:
        pid = str(product.get("id", ""))
        name = product.get("name", pid)
        top_keywords = analyze_product_opportunities(product, top_n=15)
        all_results[pid] = {
            "product_name": name,
            "product_id": pid,
            "analyzed_at": now,
            "top_keywords": top_keywords,
        }

        # config.json에 추가할 키워드 (기회 점수 70+ 키워드만)
        store_name = config.get("store_name", "나눔랩")
        for kw_data in top_keywords:
            if kw_data["opportunity_score"] >= 70:
                entry = {
                    "keyword": kw_data["keyword"],
                    "store_name": store_name,
                    "product_id": pid,
                    "opportunity_score": kw_data["opportunity_score"],
                    "competition_level": kw_data["competition_level"],
                    "_discovered_by": "keyword_opportunity_finder",
                    "_discovered_at": now,
                }
                new_keywords_for_config.append(entry)

    # 리포트 저장
    report = {
        "generated_at": now,
        "total_products_analyzed": len(products),
        "results": all_results,
        "new_keyword_candidates": new_keywords_for_config,
    }
    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    print(f"\n{'='*60}")
    print(f"📋 발굴 요약")
    print(f"{'='*60}")
    print(f"발굴된 기회 키워드: {len(new_keywords_for_config)}개 (점수 70+)")

    # 상품별 베스트 키워드 출력
    for pid, data in all_results.items():
        name = data["product_name"]
        top = data["top_keywords"][:3]
        if top:
            print(f"\n  [{name}] 추천 키워드:")
            for kw in top:
                print(
                    f"    → '{kw['keyword']}' "
                    f"(경쟁 {kw['competition_level']}, "
                    f"점수 {kw['opportunity_score']})"
                )

    # config.json 업데이트
    if apply_to_config and new_keywords_for_config:
        existing_kws = config.get("keywords", [])
        existing_set = {
            (k.get("keyword"), k.get("product_id"))
            for k in existing_kws
        }
        added = 0
        for entry in new_keywords_for_config:
            key = (entry["keyword"], entry["product_id"])
            if key not in existing_set:
                existing_kws.append({
                    "keyword": entry["keyword"],
                    "store_name": entry["store_name"],
                    "product_id": entry["product_id"],
                })
                existing_set.add(key)
                added += 1
        config["keywords"] = existing_kws
        save_config(config)
        print(f"\n✅ config.json에 {added}개 키워드 추가됨")
    elif not apply_to_config:
        print(f"\n💡 config.json 적용을 원하면 --apply 옵션을 사용하세요.")

    print(f"\n💾 상세 리포트 저장: {REPORT_PATH}")
    print(f"{'='*60}\n")
    return report


def main():
    parser = argparse.ArgumentParser(description="나눔랩 틈새 키워드 발굴기")
    parser.add_argument(
        "--product", type=str, default="",
        help="특정 상품명만 분석 (기본: 전체)"
    )
    parser.add_argument(
        "--apply", action="store_true",
        help="발굴된 키워드를 config.json에 자동 추가"
    )
    args = parser.parse_args()

    target = [args.product] if args.product else None
    run_full_analysis(target_products=target, apply_to_config=args.apply)


if __name__ == "__main__":
    main()
