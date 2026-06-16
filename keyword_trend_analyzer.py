"""
keyword_trend_analyzer.py
===========================
자동차코팅제 vs 바이크코팅제 키워드 트렌드 비교 분석
- 네이버 쇼핑 실시간 순위 비교
- 경쟁 강도 분석 (1페이지 상품 수, 광고 비중)
- 추천 집중 키워드 도출
- 결과 저장: keyword_trend_report.json

사용법:
    python keyword_trend_analyzer.py
    python keyword_trend_analyzer.py --keywords "자동차코팅제,차량코팅제,유리막코팅"
"""

import sys
import os
import re
import json
import time
import argparse
from datetime import datetime
from urllib.parse import quote

if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8', line_buffering=True)
    sys.stderr.reconfigure(encoding='utf-8', line_buffering=True)

try:
    import requests
    from bs4 import BeautifulSoup
except ImportError:
    print("❌ 필요 라이브러리: pip install requests beautifulsoup4")
    sys.exit(1)

# ── 설정 ──────────────────────────────────────────────────────
REPORT_FILE = "keyword_trend_report.json"
STORE_NAME = "나눔랩"
TARGET_PRODUCT_IDS = [
    "12639296730", "12809532969", "12808820913",
    "12809519826", "12809541448", "10713170202",
]

MOBILE_UA = (
    "Mozilla/5.0 (Linux; Android 14; SM-S928N) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Mobile Safari/537.36"
)

# 분석할 키워드 세트
DEFAULT_KEYWORDS = [
    # 핵심 비교 키워드
    "자동차코팅제",
    "바이크코팅제",
    # 나눔랩 주요 키워드
    "퍼마코트",
    "셀프 유리막 코팅",
    "유리막코팅제",
    "차량코팅제",
    "차코팅제",
    "자동차 유리막코팅",
]

# 색상
class C:
    RED    = "\033[91m"
    GREEN  = "\033[92m"
    YELLOW = "\033[93m"
    CYAN   = "\033[96m"
    BOLD   = "\033[1m"
    RESET  = "\033[0m"

def enable_ansi():
    if sys.platform == 'win32':
        os.system('color')
        try:
            import ctypes
            ctypes.windll.kernel32.SetConsoleMode(
                ctypes.windll.kernel32.GetStdHandle(-11), 7)
        except Exception:
            pass


def extract_pids(html: str) -> list:
    seen, ordered = set(), []
    for pid in re.findall(r'smartstore\.naver\.com/[^\s"\']+/products/(\d+)', html):
        if pid not in seen:
            seen.add(pid); ordered.append(pid)
    for pid in re.findall(r'/products/(\d+)', html):
        if pid not in seen:
            seen.add(pid); ordered.append(pid)
    return ordered


def fetch_shopping_page(keyword: str) -> dict:
    """네이버 쇼핑 검색 결과 수집"""
    url = f"https://m.search.naver.com/search.naver?query={quote(keyword.strip())}&where=m_shop"
    headers = {
        "User-Agent": MOBILE_UA,
        "Accept-Language": "ko-KR,ko;q=0.9",
    }
    result = {
        "keyword": keyword,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "total_products_visible": 0,
        "ad_count": 0,
        "organic_count": 0,
        "nanumlab_ranks": {},       # {product_id: rank}
        "nanumlab_best_rank": 999,
        "competitor_count_top20": 0,
        "top5_products": [],
        "error": None,
    }

    try:
        res = requests.get(url, headers=headers, timeout=15)
        if res.status_code != 200:
            result["error"] = f"HTTP {res.status_code}"
            return result

        html = res.text
        soup = BeautifulSoup(html, 'html.parser')

        # 전체 상품 ID 순서 추출
        all_pids = extract_pids(html)
        result["total_products_visible"] = len(all_pids)
        result["top5_products"] = all_pids[:5]

        # 나눔랩 상품 순위
        for pid in TARGET_PRODUCT_IDS:
            if pid in all_pids:
                rank = all_pids.index(pid) + 1
                result["nanumlab_ranks"][pid] = rank
                if rank < result["nanumlab_best_rank"]:
                    result["nanumlab_best_rank"] = rank

        # 광고 수 추정 (네이버 쇼핑 광고 레이블 탐색)
        ad_labels = soup.select("[class*='ad_']") or soup.select("[class*='_ad']")
        result["ad_count"] = min(len(ad_labels), 5)  # 일반적으로 상단 최대 5개
        result["organic_count"] = result["total_products_visible"] - result["ad_count"]

        # 경쟁사 (상위 20개 중 나눔랩 아닌 상품) 수
        competitor_pids = [p for p in all_pids[:20] if p not in TARGET_PRODUCT_IDS]
        result["competitor_count_top20"] = len(competitor_pids)

    except requests.exceptions.Timeout:
        result["error"] = "타임아웃"
    except Exception as e:
        result["error"] = str(e)[:80]

    return result


def competition_score(data: dict) -> str:
    """경쟁 강도 평가"""
    ad = data.get("ad_count", 0)
    comp = data.get("competitor_count_top20", 20)
    if ad >= 4 and comp >= 18:
        return f"{C.RED}매우 높음 (진입 어려움){C.RESET}"
    elif ad >= 2 and comp >= 14:
        return f"{C.YELLOW}높음 (집중 필요){C.RESET}"
    elif ad >= 1 and comp >= 8:
        return f"{C.CYAN}보통{C.RESET}"
    else:
        return f"{C.GREEN}낮음 (진입 용이){C.RESET}"


def format_rank(rank: int) -> str:
    if rank == 999:
        return f"{C.RED}미노출{C.RESET}"
    elif rank <= 10:
        return f"{C.GREEN}{rank}위 (1P){C.RESET}"
    elif rank <= 40:
        return f"{C.YELLOW}{rank}위 ({(rank-1)//40+1}P){C.RESET}"
    else:
        return f"{C.RED}{rank}위 ({(rank-1)//40+1}P){C.RESET}"


def run_analysis(keywords: list) -> dict:
    enable_ansi()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"\n{'='*65}")
    print(f"{C.BOLD}🔬 나눔랩 키워드 트렌드 분석 — {now}{C.RESET}")
    print(f"{'='*65}\n")

    all_results = {}

    for i, kw in enumerate(keywords):
        print(f"[{i+1}/{len(keywords)}] '{kw}' 분석 중...", end=" ", flush=True)
        data = fetch_shopping_page(kw)
        all_results[kw] = data

        if data["error"]:
            print(f"{C.RED}오류: {data['error']}{C.RESET}")
        else:
            best_rank = data["nanumlab_best_rank"]
            rank_str = format_rank(best_rank)
            comp_str = competition_score(data)
            print(f"완료")
            print(f"  ├─ 나눔랩 최고 순위: {rank_str}")
            print(f"  ├─ 노출 상품 수: {data['total_products_visible']}개 | 광고: {data['ad_count']}개")
            print(f"  └─ 경쟁 강도: {comp_str}")

        if i < len(keywords) - 1:
            time.sleep(2.5)  # 과도한 요청 방지

    # ── 핵심 비교: 자동차코팅제 vs 바이크코팅제 ──
    car_data = all_results.get("자동차코팅제", {})
    bike_data = all_results.get("바이크코팅제", {})

    print(f"\n{'='*65}")
    print(f"{C.BOLD}📊 핵심 비교: 자동차코팅제 vs 바이크코팅제{C.RESET}")
    print(f"{'='*65}")

    if car_data and bike_data and not car_data.get("error") and not bike_data.get("error"):
        car_rank = car_data["nanumlab_best_rank"]
        bike_rank = bike_data["nanumlab_best_rank"]

        print(f"\n  {'키워드':<20} {'나눔랩 순위':<18} {'경쟁 강도'}")
        print(f"  {'-'*60}")
        print(f"  {'자동차코팅제':<18} {format_rank(car_rank):<28} {competition_score(car_data)}")
        print(f"  {'바이크코팅제':<18} {format_rank(bike_rank):<28} {competition_score(bike_data)}")

        print(f"\n{C.BOLD}💡 전략 제언:{C.RESET}")
        if bike_rank < car_rank:
            gap = car_rank - bike_rank if car_rank < 999 else "미진입"
            print(f"  ⚠️  {C.YELLOW}바이크코팅제({bike_rank}위)가 자동차코팅제보다 앞서있습니다.{C.RESET}")
            print(f"  📌 자동차코팅제 집중 트래픽 세션을 즉시 실행하세요.")
            print(f"  📌 run_traffic_focus.bat 실행 → 자동차코팅제 집중 모드 가동")
        elif car_rank < 999 and car_rank <= 40:
            print(f"  ✅ {C.GREEN}자동차코팅제 {car_rank}위 — 1페이지 진입 중!{C.RESET}")
            print(f"  📌 현재 상태 유지하며 꾸준히 트래픽 공급하세요.")
        elif car_rank < 999:
            print(f"  🚀 자동차코팅제 {car_rank}위 — 1페이지 진입까지 집중 필요")
        else:
            print(f"  🚨 {C.RED}자동차코팅제 미노출 — 집중 세션 최우선 실행 필요!{C.RESET}")

    # ── 전체 순위 요약 ──
    print(f"\n{'='*65}")
    print(f"{C.BOLD}📋 전체 키워드 순위 요약{C.RESET}")
    print(f"{'='*65}")
    print(f"  {'키워드':<25} {'나눔랩 순위'}")
    print(f"  {'-'*45}")

    # 순위 기준 정렬
    sorted_kws = sorted(
        all_results.items(),
        key=lambda x: x[1].get("nanumlab_best_rank", 999)
    )
    for kw, data in sorted_kws:
        if not data.get("error"):
            rank_str = format_rank(data["nanumlab_best_rank"])
            print(f"  {kw:<25} {rank_str}")

    # ── 추천 집중 키워드 ──
    print(f"\n{C.BOLD}🎯 추천 집중 키워드 (순위 빠른 상승 예상){C.RESET}")
    recommendations = []
    for kw, data in all_results.items():
        if data.get("error"):
            continue
        rank = data["nanumlab_best_rank"]
        ad_count = data.get("ad_count", 0)
        comp = data.get("competitor_count_top20", 20)
        # 점수: 순위 낮고(개선 여지 큼), 경쟁 약한 키워드 우선
        score = (rank if rank < 999 else 500) - (comp * 5) - (ad_count * 10)
        recommendations.append((kw, rank, score))

    recommendations.sort(key=lambda x: -x[2])  # 점수 높은 순
    for i, (kw, rank, score) in enumerate(recommendations[:5], 1):
        rank_str = format_rank(rank)
        print(f"  {i}. {C.BOLD}{kw}{C.RESET} — 현재 {rank_str}")

    # ── 결과 저장 ──
    report = {
        "generated_at": now,
        "keywords": all_results,
        "recommendations": [{"keyword": k, "current_rank": r, "score": s}
                             for k, r, s in recommendations],
    }
    # JSON 직렬화 안전 처리
    def default_serializer(obj):
        if isinstance(obj, (int, float, str, bool, list, dict, type(None))):
            return obj
        return str(obj)

    with open(REPORT_FILE, 'w', encoding='utf-8') as f:
        json.dump(report, f, ensure_ascii=False, indent=2, default=str)

    print(f"\n💾 분석 결과 저장: {REPORT_FILE}")
    print(f"{'='*65}\n")
    return report


def main():
    parser = argparse.ArgumentParser(description="나눔랩 키워드 트렌드 분석")
    parser.add_argument('--keywords', type=str, default='',
                        help='분석 키워드 (쉼표 구분, 기본: 설정된 키워드 사용)')
    args = parser.parse_args()

    if args.keywords:
        keywords = [k.strip() for k in args.keywords.split(',') if k.strip()]
    else:
        keywords = DEFAULT_KEYWORDS

    run_analysis(keywords)


if __name__ == "__main__":
    main()
