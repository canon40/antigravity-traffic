"""
rank_monitor_live.py
====================
나눔랩 네이버 쇼핑 순위 실시간 모니터 (독립 실행 가능)

사용법:
    python rank_monitor_live.py               # 1회 즉시 체크
    python rank_monitor_live.py --watch       # 60분마다 자동 반복
    python rank_monitor_live.py --watch --interval 30  # 30분마다 반복
    python rank_monitor_live.py --pages 5     # 탐색 페이지 수 지정 (기본 5 = 200위)

변경 이력:
    v2.0 - 5페이지(200위)까지 다중 탐색, 순위 변화량(▲▼) 표시,
           BOOST_TARGETS 동기화, 이전 로그 비교 하이라이트
"""

import sys
import os
import re
import csv
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
    print("❌ 필요 라이브러리 없음: pip install requests beautifulsoup4")
    sys.exit(1)

# ── 설정 ──────────────────────────────────────────────────────
STORE_NAME = "나눔랩"
LOG_FILE = "rank_live_log.csv"
LOG_HEADERS = ["날짜", "키워드", "순위", "상품ID", "페이지", "메모"]

MOBILE_UA = (
    "Mozilla/5.0 (Linux; Android 14; SM-S928N) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Mobile Safari/537.36"
)

# ── 탐색 기본값 ────────────────────────────────────────────────
DEFAULT_PAGES = 5          # 5페이지 = 200위까지 탐색
ALERT_CHANGE_THRESHOLD = 10  # 이 이상 순위 변화 시 콘솔 경보

# ── 체크할 키워드 목록 (rank_booster.py BOOST_TARGETS 동기화) ──
CHECK_KEYWORDS = [
    # ── 🔴 미노출 집중 공략 ─────────────────────────────────
    {
        "keyword": "유리막 코팅제",
        "product_ids": ["12808820913"],
        "label": "🔴 [부스팅]",
        "status": "boosting",
    },
    {
        "keyword": "유리막코팅제 추천",
        "product_ids": ["12809519826"],
        "label": "🔴 [부스팅]",
        "status": "boosting",
    },
    {
        "keyword": "자동차 유리막코팅",
        "product_ids": ["12809532969"],
        "label": "🔴 [부스팅]",
        "status": "boosting",
    },
    {
        "keyword": "셀프 유리막코팅제",
        "product_ids": ["12809541448"],
        "label": "🔴 [부스팅]",
        "status": "boosting",
    },
    {
        "keyword": "세차 관리제",
        "product_ids": ["12808787263"],
        "label": "🔴 [부스팅]",
        "status": "boosting",
    },
    # ── 🟢 유지 상품 ───────────────────────────────────────
    {
        "keyword": "퍼마코트 자동차 코팅제",
        "product_ids": ["12639296730"],
        "label": "🟢 [유지]",
        "status": "maintain",
    },
    {
        "keyword": "차량용 유리막코팅",
        "product_ids": ["12634187514"],
        "label": "🟢 [유지]",
        "status": "maintain",
    },
    {
        "keyword": "리빙코트",
        "product_ids": ["10713170202"],
        "label": "🟢 [유지]",
        "status": "maintain",
    },
    # ── 📊 비교 키워드 ─────────────────────────────────────
    {
        "keyword": "자동차코팅제",
        "product_ids": ["12639296730", "12809532969"],
        "label": "📊 [비교]",
        "status": "compare",
    },
    {
        "keyword": "유리막코팅제",
        "product_ids": ["12808820913", "12809519826"],
        "label": "📊 [비교]",
        "status": "compare",
    },
]

# 색상 코드 (Windows 터미널)
class C:
    RED    = "\033[91m"
    GREEN  = "\033[92m"
    YELLOW = "\033[93m"
    CYAN   = "\033[96m"
    BOLD   = "\033[1m"
    RESET  = "\033[0m"


def enable_ansi():
    """Windows에서 ANSI 색상 활성화"""
    if sys.platform == 'win32':
        os.system('color')
        try:
            import ctypes
            kernel32 = ctypes.windll.kernel32
            kernel32.SetConsoleMode(kernel32.GetStdHandle(-11), 7)
        except Exception:
            pass


def extract_product_ids_ordered(html: str) -> list:
    """HTML에서 상품 ID를 순서대로 추출 (중복 제거)"""
    ordered = []
    seen = set()
    def add(pid):
        if pid and pid not in seen:
            seen.add(pid)
            ordered.append(pid)
    # 1. smartstore URL matches (support both / and escaped \u002F)
    for pid in re.findall(r'smartstore\.naver\.com(?:/|\\u002F)[^\s"\'\\/]+(?:/|\\u002F)products(?:/|\\u002F)(\d+)', html):
        add(pid)
    # 2. Generic /products/ or \u002Fproducts\u002F matches
    for pid in re.findall(r'(?:/|\\u002F)products(?:/|\\u002F)(\d+)', html):
        add(pid)
    # 3. JSON channelProductId matches
    for pid in re.findall(r'["\']channelProductId["\']?\s*:\s*["\']?(\d+)["\']?', html):
        add(pid)
    # 4. nv_mid / nvMid fallback
    for pid in re.findall(r'[?&]nv_mid=(\d+)', html):
        add(pid)
    for pid in re.findall(r'nvMid["\']?\s*:\s*["\']?(\d+)', html):
        add(pid)
    return ordered



def check_keyword_rank(keyword: str, product_ids: list, max_pages: int = DEFAULT_PAGES) -> dict:
    """
    키워드로 네이버 쇼핑 검색 → 다중 페이지(최대 max_pages) 탐색하여 순위 반환.
    max_pages=5 → 200위까지 탐색.
    Returns: {"keyword": str, "ranks": {pid: rank}, "nanumlab_rank": int, "total_products": int}
    """
    headers = {
        "User-Agent": MOBILE_UA,
        "Accept-Language": "ko-KR,ko;q=0.9",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }
    result = {
        "keyword": keyword,
        "ranks": {},
        "nanumlab_rank": 999,
        "total_products": 0,
        "error": None,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M"),
    }

    remaining_pids = set(product_ids)  # 아직 못 찾은 상품
    cumulative_rank = 0

    try:
        for page_num in range(1, max_pages + 1):
            # 모든 지정 상품을 찾았으면 종료
            if product_ids and not remaining_pids:
                break

            start = (page_num - 1) * 40 + 1
            url = f"https://m.search.naver.com/search.naver?query={quote(keyword.strip())}&where=m_shop&start={start}"

            try:
                res = requests.get(url, headers=headers, timeout=15)
                if res.status_code != 200:
                    result["error"] = f"HTTP {res.status_code}"
                    break
            except requests.exceptions.Timeout:
                result["error"] = "타임아웃"
                break

            page_pids = extract_product_ids_ordered(res.text)
            if not page_pids:
                break  # 더 이상 결과 없음

            # 나눔랩 스토어 fallback (1페이지에서만)
            if page_num == 1 and result["nanumlab_rank"] == 999:
                soup = BeautifulSoup(res.text, 'html.parser')
                items = soup.select(".lst_item") or soup.select("div[class*='product_item']")
                for idx, item in enumerate(items, 1):
                    if STORE_NAME in item.text:
                        result["nanumlab_rank"] = idx
                        break

            # 각 상품 ID 순위 계산 (누적 순위 기준)
            for pid in page_pids:
                cumulative_rank += 1
                if pid in remaining_pids:
                    result["ranks"][pid] = cumulative_rank
                    remaining_pids.discard(pid)

            result["total_products"] = cumulative_rank

            # 결과가 35개 미만이면 마지막 페이지
            if len(page_pids) < 35:
                break

            # 다음 페이지 요청 전 잠시 대기 (네이버 요청 간격 준수)
            if page_num < max_pages:
                time.sleep(0.6)

    except Exception as e:
        result["error"] = str(e)[:80]

    return result


def format_rank(rank: int, prev_rank: int = None) -> str:
    """순위를 색상 포함 문자열로 포맷. prev_rank가 있으면 변화량(▲▼) 추가."""
    # 변화량 계산
    delta_str = ""
    if prev_rank is not None and prev_rank != rank:
        delta = prev_rank - rank  # 양수 = 상승
        if delta > 0:
            marker = f"{C.GREEN}▲{delta}{C.RESET}"
        elif delta < 0:
            marker = f"{C.RED}▼{abs(delta)}{C.RESET}"
        else:
            marker = ""
        if marker:
            delta_str = f" {marker}"
        # 급변 경보
        if abs(delta) >= ALERT_CHANGE_THRESHOLD:
            delta_str += f" {C.BOLD}⚡급변!{C.RESET}"

    if rank >= 999:
        base = f"{C.RED}미노출{C.RESET}"
    elif rank <= 10:
        base = f"{C.GREEN}{rank}위 (1페이지 TOP10){C.RESET}"
    elif rank <= 40:
        page = (rank - 1) // 40 + 1
        pos = (rank - 1) % 40 + 1
        base = f"{C.GREEN}{rank}위 ({page}페이지 {pos}번째){C.RESET}"
    elif rank <= 80:
        page = (rank - 1) // 40 + 1
        pos = (rank - 1) % 40 + 1
        base = f"{C.YELLOW}{rank}위 ({page}페이지 {pos}번째){C.RESET}"
    elif rank <= 200:
        page = (rank - 1) // 40 + 1
        pos = (rank - 1) % 40 + 1
        base = f"{C.CYAN}{rank}위 ({page}페이지 {pos}번째){C.RESET}"
    else:
        page = (rank - 1) // 40 + 1
        base = f"{C.RED}{rank}위 ({page}페이지){C.RESET}"

    return base + delta_str


def ensure_log_file():
    if not os.path.exists(LOG_FILE):
        with open(LOG_FILE, 'w', encoding='utf-8-sig', newline='') as f:
            csv.writer(f).writerow(LOG_HEADERS)


def append_log(keyword, rank, product_id, page_num, memo=""):
    ensure_log_file()
    with open(LOG_FILE, 'a', encoding='utf-8-sig', newline='') as f:
        csv.writer(f).writerow([
            datetime.now().strftime("%Y-%m-%d %H:%M"),
            keyword, rank, product_id, page_num, memo
        ])


def get_prev_rank(keyword: str, product_id: str) -> int:
    """LOG_FILE에서 해당 키워드+상품ID의 직전 순위를 반환. 없으면 None."""
    if not os.path.exists(LOG_FILE):
        return None
    prev = None
    try:
        with open(LOG_FILE, 'r', encoding='utf-8-sig') as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row.get('키워드') == keyword and row.get('상품ID') == product_id:
                    try:
                        prev = int(row['순위'])
                    except (ValueError, TypeError):
                        prev = None
    except Exception:
        pass
    return prev


def run_check(verbose=True, max_pages=DEFAULT_PAGES):
    """전체 키워드 순위 1회 체크 (다중 페이지 지원)"""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"\n{'='*64}")
    print(f"{C.BOLD}🔍 나눔랩 실시간 순위 체크 — {now}{C.RESET}")
    print(f"   탐색 범위: 최대 {max_pages}페이지 ({max_pages * 40}위까지)")
    print(f"{'='*64}")

    results = []
    summary_boosting = []   # 미노출 집중 공략 상품 결과
    summary_maintain = []   # 유지 상품 결과
    alert_lines = []        # 급변 알림 모음

    for item in CHECK_KEYWORDS:
        kw = item["keyword"]
        label = item["label"]
        pids = item["product_ids"]
        status = item.get("status", "")

        print(f"\n{label} '{kw}' 체크 중...", end=" ", flush=True)
        r = check_keyword_rank(kw, pids, max_pages=max_pages)

        if r["error"]:
            print(f"{C.RED}오류: {r['error']}{C.RESET}")
            results.append(r)
            continue

        page_cnt = (r['total_products'] - 1) // 40 + 1 if r['total_products'] > 0 else 0
        print(f"완료 (총 {r['total_products']}개 / {page_cnt}페이지 탐색)")

        # 상품 ID별 순위 출력
        if pids:
            for pid in pids:
                rank = r["ranks"].get(pid, 999)
                prev = get_prev_rank(kw, pid)
                page_num = (rank - 1) // 40 + 1 if rank < 999 else "-"
                rank_str = format_rank(rank, prev)
                print(f"  └── 상품 {pid}: {rank_str}")
                memo = ""
                if prev is not None:
                    delta = prev - rank
                    if abs(delta) >= ALERT_CHANGE_THRESHOLD:
                        alert_msg = f"  ⚡ [{kw}] 상품{pid}: {prev}위 → {rank}위 (변화 {delta:+d})"
                        alert_lines.append(alert_msg)
                    memo = f"이전:{prev}위"
                append_log(kw, rank if rank < 999 else 999, pid, page_num, memo)

                # 요약용 수집
                entry = {"keyword": kw, "pid": pid, "rank": rank, "prev": prev, "status": status}
                if status == "boosting":
                    summary_boosting.append(entry)
                elif status == "maintain":
                    summary_maintain.append(entry)
        elif r["nanumlab_rank"] < 999:
            rank = r["nanumlab_rank"]
            rank_str = format_rank(rank)
            print(f"  └── 나눔랩 스토어: {rank_str}")
            append_log(kw, rank, "store", (rank-1)//40+1, "스토어명 매칭")
        else:
            print(f"  └── {C.RED}미노출 ({max_pages}페이지 밖){C.RESET}")
            append_log(kw, 999, "-", "-", "미노출")

        results.append(r)
        time.sleep(0.5)  # 키워드 간 요청 간격

    # ── 요약 출력 ────────────────────────────────────────────
    print(f"\n{'='*64}")
    print(f"{C.BOLD}📊 [요약] 나눔랩 순위 현황{C.RESET}")
    print(f"{'='*64}")

    # 미노출 집중 공략 상품 요약
    if summary_boosting:
        print(f"\n{C.BOLD}🔴 부스팅 대상 (미노출→진입 집중){C.RESET}")
        entered = [e for e in summary_boosting if e['rank'] <= 100]
        near = [e for e in summary_boosting if 100 < e['rank'] <= 200]
        unranked = [e for e in summary_boosting if e['rank'] > 200]
        for e in entered:
            delta_str = f"  ({e['prev']}위→{e['rank']}위)" if e['prev'] else ""
            print(f"  {C.GREEN}✅ {e['keyword']} — {e['rank']}위{delta_str}{C.RESET}")
        for e in near:
            print(f"  {C.YELLOW}🟡 {e['keyword']} — {e['rank']}위 (200위권 근접){C.RESET}")
        for e in unranked:
            rank_txt = f"{e['rank']}위" if e['rank'] < 999 else "미노출"
            print(f"  {C.RED}🔴 {e['keyword']} — {rank_txt}{C.RESET}")
        print(f"  → 진입 성공 {len(entered)}개 / 근접 {len(near)}개 / 미노출 {len(unranked)}개")

    # 유지 상품 요약
    if summary_maintain:
        print(f"\n{C.BOLD}🟢 유지 상품{C.RESET}")
        for e in summary_maintain:
            rank_txt = f"{e['rank']}위" if e['rank'] < 999 else "미노출"
            prev_txt = f"  (이전:{e['prev']}위)" if e['prev'] else ""
            icon = "✅" if e['rank'] <= 100 else ("⚠️" if e['rank'] <= 200 else "🚨")
            print(f"  {icon} {e['keyword']} — {rank_txt}{prev_txt}")

    # 급변 경보
    if alert_lines:
        print(f"\n{C.BOLD}{C.RED}⚡ 급변 알림 (±{ALERT_CHANGE_THRESHOLD}위 이상 변화){C.RESET}")
        for line in alert_lines:
            print(f"{C.RED}{line}{C.RESET}")

    print(f"\n💾 로그 저장: {LOG_FILE}")
    print(f"{'='*64}\n")
    return results


def main():
    enable_ansi()
    parser = argparse.ArgumentParser(
        description="나눔랩 네이버 쇼핑 순위 실시간 모니터 v2.0"
    )
    parser.add_argument('--watch', action='store_true',
                        help='자동 반복 모드')
    parser.add_argument('--interval', type=int, default=60,
                        help='반복 간격 (분, 기본: 60)')
    parser.add_argument('--pages', type=int, default=DEFAULT_PAGES,
                        help=f'탐색 페이지 수 (기본: {DEFAULT_PAGES} = {DEFAULT_PAGES*40}위)')
    args = parser.parse_args()

    if args.watch:
        print(f"🔄 자동 반복 모드 — {args.interval}분마다 체크, {args.pages}페이지 탐색 (Ctrl+C로 종료)")
        round_num = 0
        while True:
            round_num += 1
            print(f"\n{'#'*30} Round {round_num} {'#'*30}")
            run_check(max_pages=args.pages)
            print(f"⏳ {args.interval}분 대기 중... (Ctrl+C로 종료)")
            try:
                time.sleep(args.interval * 60)
            except KeyboardInterrupt:
                print("\n👋 모니터 종료")
                break
    else:
        run_check(max_pages=args.pages)


if __name__ == "__main__":
    main()
