import json
import os
import re
from urllib.parse import quote

import requests

from app_resources import get_storage_dir
from rank_tracker import MOBILE_UA, _shopping_search_url, check_product_rank

CONFIG_PATH = "config.json"

SEED_KEYWORDS = [
    "퍼마코트", "자동차 코팅제", "셀프 유리막 코팅", "차량 코팅",
    "듀라코트", "리빙코트", "유리막 코팅제", "세차 코팅",
    "자동차 광택", "차량 관리", "셀프 세차", "코팅제 추천",
    "나눔랩", "외장 코팅", "실내 코팅", "발수 코팅",
]


def load_config():
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"products": [], "store_name": "나눔랩"}


def _fetch_shopping_html(keyword):
    res = requests.get(
        _shopping_search_url(keyword),
        headers={
            "User-Agent": MOBILE_UA,
            "Accept-Language": "ko-KR,ko;q=0.9",
        },
        timeout=20,
    )
    res.raise_for_status()
    return res.text


def _count_shopping_items(html):
    try:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "html.parser")
        items = soup.select(".lst_item") or soup.select("div[class*='product_item']")
        if items:
            return len(items)
    except Exception:
        pass
    links = re.findall(r'class="[^"]*product_link[^"]*"', html)
    return len(links) if links else 0


def _extract_related_keywords(html, base_keyword):
    related = set()
    for m in re.findall(r'query=([^&"]+)', html):
        try:
            from urllib.parse import unquote
            kw = unquote(m.replace("+", " "))
        except Exception:
            kw = m
        if len(kw) >= 2 and kw != base_keyword and not kw.startswith("http"):
            related.add(kw)
    return list(related)[:8]


def estimate_competition(item_count):
    if item_count <= 20:
        return "낮음", "좋음", 85
    if item_count <= 40:
        return "보통", "양호", 65
    if item_count <= 60:
        return "높음", "보통", 45
    return "매우 높음", "어려움", 25


def analyze_keyword(keyword, product_id=None):
    keyword = keyword.strip()
    if not keyword:
        return {"success": False, "error": "키워드를 입력하세요."}

    try:
        html = _fetch_shopping_html(keyword)
    except Exception as e:
        return {"success": False, "error": f"검색 조회 실패: {e}"}

    item_count = _count_shopping_items(html)
    competition, recommendation, score = estimate_competition(item_count)
    related = _extract_related_keywords(html, keyword)

    rank_info = None
    if product_id:
        rank = check_product_rank(keyword, product_id)
        if rank is not None:
            page = (rank - 1) // 40 + 1
            pos_in_page = ((rank - 1) % 40) + 1
            rank_info = {
                "rank": rank,
                "display": f"{page}페이지 {pos_in_page}위" if rank < 100 else "100위 밖",
                "rank_text": f"{rank}위" if rank < 100 else "100위 밖",
            }

    # 검색량은 공개 API 없이 추정치(1페이지 노출 밀도 기반)로 표시
    volume_estimate = max(500, item_count * 280)

    tips = []
    if score >= 70:
        tips.append("상품명·태그에 이 키워드를 포함하는 것을 권장합니다.")
    if len(keyword) <= 12:
        tips.append("세부 키워드(예: '셀프 유리막 코팅제 추천')로 롱테일 확장을 고려하세요.")
    tips.append("상세페이지 상단 300자 내에 키워드를 자연스럽게 배치하세요.")
    tips.append("실제 구매 전환율·리뷰가 순위 유지에 더 중요합니다.")

    return {
        "success": True,
        "keyword": keyword,
        "product_id": product_id,
        "item_count_page1": item_count,
        "competition": competition,
        "recommendation": recommendation,
        "opportunity_score": score,
        "estimated_monthly_searches": volume_estimate,
        "related_keywords": related,
        "rank_info": rank_info,
        "tips": tips,
    }


def suggest_keywords_for_product(product_name, category="코팅제"):
    base = product_name or "퍼마코트"
    candidates = []
    for seed in SEED_KEYWORDS:
        if seed in base or base in seed:
            candidates.append(seed)
        candidates.append(f"{base} {seed}" if seed != base else seed)
        candidates.append(f"{seed} 추천")
        candidates.append(f"셀프 {seed}")

    seen = set()
    unique = []
    for c in candidates:
        c = c.strip()
        if c and c not in seen and len(c) <= 25:
            seen.add(c)
            unique.append(c)

    results = []
    for kw in unique[:12]:
        analysis = analyze_keyword(kw)
        if analysis.get("success"):
            results.append({
                "keyword": kw,
                "opportunity_score": analysis["opportunity_score"],
                "competition": analysis["competition"],
                "recommendation": analysis["recommendation"],
            })

    results.sort(key=lambda x: x["opportunity_score"], reverse=True)
    return results[:8]


def analyze_all_products():
    config = load_config()
    products = config.get("products", [])
    if not products:
        for url in config.get("product_urls", []):
            pid = url.rstrip("/").split("/")[-1]
            products.append({"id": pid, "name": pid, "url": url})

    report = []
    for p in products:
        pid = str(p.get("id", ""))
        name = p.get("name", pid)
        keywords = p.get("target_keywords") or [name.split()[0] if name else "코팅제"]
        kw_results = []
        for kw in keywords[:3]:
            kw_results.append(analyze_keyword(kw, product_id=pid))
        report.append({"product": p, "analyses": kw_results})

    return report
