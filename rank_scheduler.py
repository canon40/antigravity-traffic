"""
rank_scheduler.py — 나눔랩 통합 순위 스케줄러
================================================
목표: 상품 상태(미노출/진입/안정)에 따라 체크 주기를 자동 조정하며
      순위를 정밀 추적.

주기 정책:
  - 미노출 (999위 이상)       → 15분마다 집중 체크
  - 진입 중 (101~200위)       → 30분마다 체크
  - 노출 중 (1~100위)         → 60분마다 체크

실행:
  python rank_scheduler.py              # 상태별 자동 주기
  python rank_scheduler.py --fast       # 전체 15분 고정
  python rank_scheduler.py --normal     # 전체 30분 고정
  python rank_scheduler.py --slow       # 전체 60분 고정
  python rank_scheduler.py --once       # 1회 체크 후 종료
  python rank_scheduler.py --pages 7   # 탐색 페이지 수 지정
"""

import sys
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8', line_buffering=True)
    sys.stderr.reconfigure(encoding='utf-8', line_buffering=True)

import argparse
import csv
import os
import re
import time
from datetime import datetime
from urllib.parse import quote

import requests

# ── 부스팅 대상 상품 정의 (rank_booster.py와 동기화) ──────────
BOOST_TARGETS = [
    # 미노출 집중 공략
    {
        'product_id': '12808820913',
        'name': '나눔랩 코팅제 A',
        'primary_keyword': '유리막 코팅제',
        'keywords': ['유리막 코팅제', '유리막코팅제 가성비', '나눔랩 코팅제',
                     '셀프 유리막코팅제', '유리막코팅제 추천'],
        'status': 'boosting',
    },
    {
        'product_id': '12809519826',
        'name': '나눔랩 코팅제 B',
        'primary_keyword': '유리막코팅제 추천',
        'keywords': ['유리막코팅제 추천', '자동차 유리막 코팅 추천',
                     '차량 코팅제 추천', '나눔랩 코팅제', '유리막코팅제'],
        'status': 'boosting',
    },
    {
        'product_id': '12809532969',
        'name': '나눔랩 코팅제 C',
        'primary_keyword': '자동차 유리막코팅',
        'keywords': ['자동차 유리막코팅', '자동차코팅 DIY',
                     '차량 유리막코팅 셀프', '나눔랩 코팅제', '셀프 자동차코팅'],
        'status': 'boosting',
    },
    {
        'product_id': '12809541448',
        'name': '나눔랩 코팅제 D',
        'primary_keyword': '셀프 유리막코팅제',
        'keywords': ['셀프 유리막코팅제', '유리막코팅 DIY',
                     '차 코팅 셀프', '나눔랩 코팅제', '자동차코팅제 셀프'],
        'status': 'boosting',
    },
    {
        'product_id': '12808787263',
        'name': '나눔랩 세정·관리제',
        'primary_keyword': '세차 관리제',
        'keywords': ['세차 관리제', '셀프세차 세정제', '나눔랩 세정제',
                     '차량 세정제 추천', '세차용품 추천'],
        'status': 'boosting',
    },
    # 유지 상품
    {
        'product_id': '12639296730',
        'name': '퍼마코트 자동차 코팅제',
        'primary_keyword': '퍼마코트 자동차 코팅제',
        'keywords': ['퍼마코트 자동차 코팅제', '자동차코팅제', '셀프 유리막 코팅'],
        'status': 'maintain',
    },
    {
        'product_id': '12634187514',
        'name': '나눔랩 코팅 상품',
        'primary_keyword': '차량용 유리막코팅',
        'keywords': ['차량용 유리막코팅', '차량 코팅제'],
        'status': 'maintain',
    },
    {
        'product_id': '10713170202',
        'name': '듀라코트 리빙코트',
        'primary_keyword': '리빙코트',
        'keywords': ['리빙코트', '듀라코트 리빙코트', '가구 코팅제'],
        'status': 'maintain',
    },
]

# ── 설정 ───────────────────────────────────────────────────────
MOBILE_UA = (
    "Mozilla/5.0 (Linux; Android 14; SM-S928N) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Mobile Safari/537.36"
)

# 상태별 체크 주기 (분)
INTERVAL_POLICY = {
    'unranked':  15,   # 999위 이상 (미노출)
    'entering':  30,   # 101~200위 (진입 중)
    'ranked':    60,   # 1~100위 (노출 안정)
    'maintain':  60,   # 유지 상품 고정
}

ALERT_THRESHOLD = 10     # ±10위 이상 변화 시 경보
DEFAULT_PAGES   = 5      # 기본 탐색 페이지 수 (5 × 40 = 200위)

LOG_FILE    = 'rank_master_log.csv'
LOG_HEADERS = ['날짜', '상품명', '상품ID', '키워드', '순위', '이전순위', '변동', '상태', '비고']

# ── 색상 ───────────────────────────────────────────────────────
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
            kernel32 = ctypes.windll.kernel32
            kernel32.SetConsoleMode(kernel32.GetStdHandle(-11), 7)
        except Exception:
            pass


# ── 로그 ───────────────────────────────────────────────────────
def ensure_log():
    if not os.path.exists(LOG_FILE):
        with open(LOG_FILE, 'w', encoding='utf-8-sig', newline='') as f:
            csv.writer(f).writerow(LOG_HEADERS)


def append_log(name, pid, keyword, rank, prev_rank, status, note=''):
    ensure_log()
    if prev_rank is None:
        change = '-'
    else:
        d = prev_rank - rank
        change = f'+{d}' if d > 0 else (f'{d}' if d < 0 else '0')

    with open(LOG_FILE, 'a', encoding='utf-8-sig', newline='') as f:
        csv.writer(f).writerow([
            datetime.now().strftime('%Y-%m-%d %H:%M'),
            name, pid, keyword,
            rank if rank < 999 else '미노출',
            prev_rank if prev_rank else '-',
            change, status, note,
        ])


def get_prev_rank(pid: str, keyword: str) -> int | None:
    """LOG_FILE에서 해당 상품+키워드의 직전 순위 반환. 없으면 None."""
    if not os.path.exists(LOG_FILE):
        return None
    prev = None
    try:
        with open(LOG_FILE, 'r', encoding='utf-8-sig') as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row.get('상품ID') == pid and row.get('키워드') == keyword:
                    raw = row.get('순위', '')
                    if raw and raw != '미노출':
                        try:
                            prev = int(raw)
                        except ValueError:
                            pass
    except Exception:
        pass
    return prev


# ── 순위 조회 ──────────────────────────────────────────────────
def extract_ordered_pids(html: str) -> list:
    ordered, seen = [], set()
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



def check_rank(keyword: str, product_id: str, max_pages: int = DEFAULT_PAGES) -> int:
    """
    네이버 모바일 쇼핑 검색에서 상품 순위 반환.
    max_pages × 40위까지 탐색. 미발견 시 999 반환.
    """
    headers = {
        'User-Agent': MOBILE_UA,
        'Accept-Language': 'ko-KR,ko;q=0.9',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    }
    pid = str(product_id).strip()
    cumulative = 0

    for page_num in range(1, max_pages + 1):
        start = (page_num - 1) * 40 + 1
        url = (f"https://m.search.naver.com/search.naver?"
               f"query={quote(keyword)}&where=m_shop&start={start}")
        try:
            res = requests.get(url, headers=headers, timeout=15)
            if res.status_code != 200:
                continue
            page_pids = extract_ordered_pids(res.text)
            if not page_pids:
                break
            if pid in page_pids:
                return cumulative + page_pids.index(pid) + 1
            cumulative += len(page_pids)
            if len(page_pids) < 35:
                break
            if page_num < max_pages:
                time.sleep(0.5)
        except Exception:
            continue

    return 999


# ── 상태 판정 ──────────────────────────────────────────────────
def rank_to_state(rank: int, product_status: str) -> str:
    """순위 → 체크 주기 상태 문자열 반환."""
    if product_status == 'maintain':
        return 'maintain'
    if rank >= 999:
        return 'unranked'
    if rank > 100:
        return 'entering'
    return 'ranked'


def format_rank(rank: int, prev: int = None) -> str:
    delta_str = ''
    if prev is not None:
        d = prev - rank
        if d > 0:
            delta_str = f' {C.GREEN}▲{d}{C.RESET}'
        elif d < 0:
            delta_str = f' {C.RED}▼{abs(d)}{C.RESET}'
        if abs(d) >= ALERT_THRESHOLD:
            delta_str += f' {C.BOLD}⚡급변!{C.RESET}'

    if rank >= 999:
        base = f'{C.RED}미노출{C.RESET}'
    elif rank <= 10:
        base = f'{C.GREEN}{rank}위 (TOP10){C.RESET}'
    elif rank <= 40:
        page = (rank - 1) // 40 + 1
        pos = (rank - 1) % 40 + 1
        base = f'{C.GREEN}{rank}위 ({page}p {pos}번){C.RESET}'
    elif rank <= 100:
        page = (rank - 1) // 40 + 1
        pos = (rank - 1) % 40 + 1
        base = f'{C.YELLOW}{rank}위 ({page}p {pos}번){C.RESET}'
    elif rank <= 200:
        page = (rank - 1) // 40 + 1
        pos = (rank - 1) % 40 + 1
        base = f'{C.CYAN}{rank}위 ({page}p {pos}번){C.RESET}'
    else:
        page = (rank - 1) // 40 + 1
        base = f'{C.RED}{rank}위 ({page}p){C.RESET}'

    return base + delta_str


# ── 1회 전체 체크 ──────────────────────────────────────────────
def run_once(max_pages: int = DEFAULT_PAGES) -> dict:
    """
    모든 BOOST_TARGETS를 체크하고 {product_id: {'rank': int, 'state': str}} 반환.
    """
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    print(f"\n{'═'*62}")
    print(f"{C.BOLD}📊 나눔랩 통합 순위 체크 — {now}{C.RESET}")
    print(f"   탐색 범위: 최대 {max_pages}페이지 ({max_pages * 40}위까지)")
    print(f"{'═'*62}")

    rank_map = {}   # {pid: {'rank': int, 'state': str, 'name': str, 'kw': str}}
    alerts   = []

    # ── 부스팅 상품 ─────────────────────────────────────────
    print(f"\n{C.BOLD}🔴 부스팅 대상 ({len([t for t in BOOST_TARGETS if t['status']=='boosting'])}개){C.RESET}")
    for t in (x for x in BOOST_TARGETS if x['status'] == 'boosting'):
        kw   = t['primary_keyword']
        pid  = t['product_id']
        name = t['name']
        prev = get_prev_rank(pid, kw)

        print(f"  🔍 {name} '{kw}'...", end=' ', flush=True)
        rank = check_rank(kw, pid, max_pages)
        state = rank_to_state(rank, t['status'])
        rank_str = format_rank(rank, prev)
        print(rank_str)

        # 급변 알림
        if prev is not None and abs(prev - rank) >= ALERT_THRESHOLD:
            alerts.append(f"  ⚡ {name} '{kw}': {prev}위 → {rank}위 (변화 {prev-rank:+d})")

        # 로그 기록
        append_log(name, pid, kw, rank, prev, state)
        rank_map[pid] = {'rank': rank, 'state': state, 'name': name, 'kw': kw}
        time.sleep(1.0)  # 요청 간격

    # ── 유지 상품 ─────────────────────────────────────────
    print(f"\n{C.BOLD}🟢 유지 상품 ({len([t for t in BOOST_TARGETS if t['status']=='maintain'])}개){C.RESET}")
    for t in (x for x in BOOST_TARGETS if x['status'] == 'maintain'):
        kw   = t['primary_keyword']
        pid  = t['product_id']
        name = t['name']
        prev = get_prev_rank(pid, kw)

        print(f"  🔍 {name} '{kw}'...", end=' ', flush=True)
        rank = check_rank(kw, pid, max_pages)
        state = rank_to_state(rank, t['status'])
        rank_str = format_rank(rank, prev)
        icon = '✅' if rank <= 100 else ('⚠️' if rank <= 200 else '🚨')
        print(f"{icon} {rank_str}")

        append_log(name, pid, kw, rank, prev, state)
        rank_map[pid] = {'rank': rank, 'state': state, 'name': name, 'kw': kw}
        time.sleep(1.0)

    # ── 요약 ──────────────────────────────────────────────
    print(f"\n{'─'*62}")
    print(f"{C.BOLD}📋 결과 요약{C.RESET}")

    boosting_results = [(v['name'], v['kw'], v['rank']) for k, v in rank_map.items()
                        if any(t['product_id'] == k and t['status'] == 'boosting'
                               for t in BOOST_TARGETS)]
    entered  = [(n, kw, r) for n, kw, r in boosting_results if r <= 100]
    entering = [(n, kw, r) for n, kw, r in boosting_results if 100 < r <= 200]
    unranked = [(n, kw, r) for n, kw, r in boosting_results if r > 200]

    print(f"  {C.GREEN}✅ 100위 이내 진입: {len(entered)}개{C.RESET}")
    for n, kw, r in entered:
        print(f"     • {n} '{kw}' → {r}위")
    print(f"  {C.YELLOW}🟡 101~200위 근접: {len(entering)}개{C.RESET}")
    for n, kw, r in entering:
        print(f"     • {n} '{kw}' → {r}위")
    print(f"  {C.RED}🔴 미노출/200위 밖: {len(unranked)}개{C.RESET}")
    for n, kw, r in unranked:
        r_str = f"{r}위" if r < 999 else "미노출"
        print(f"     • {n} '{kw}' → {r_str}")

    if alerts:
        print(f"\n{C.BOLD}{C.RED}⚡ 급변 알림{C.RESET}")
        for a in alerts:
            print(f"{C.RED}{a}{C.RESET}")

    print(f"\n💾 통합 로그: {LOG_FILE}")
    print(f"{'═'*62}\n")
    return rank_map


# ── 다음 대기 시간 계산 ────────────────────────────────────────
def calc_next_interval(rank_map: dict, fixed_interval: int = None) -> int:
    """
    상태별 주기 정책에 따라 다음 체크까지 대기 시간(분) 반환.
    fixed_interval이 있으면 그 값을 우선 사용.
    """
    if fixed_interval is not None:
        return fixed_interval

    # 미노출 상품이 있으면 가장 짧은 주기 적용
    states = [v['state'] for v in rank_map.values()]
    if 'unranked' in states:
        interval = INTERVAL_POLICY['unranked']
        reason = f"미노출 상품 있음 → {interval}분 집중 모드"
    elif 'entering' in states:
        interval = INTERVAL_POLICY['entering']
        reason = f"진입 중 상품 있음 → {interval}분 모드"
    else:
        interval = INTERVAL_POLICY['ranked']
        reason = f"모두 노출 중 → {interval}분 안정 모드"

    print(f"⏱️  [{reason}]")
    return interval


# ── 메인 루프 ─────────────────────────────────────────────────
def main():
    enable_ansi()
    parser = argparse.ArgumentParser(description='나눔랩 통합 순위 스케줄러')
    grp = parser.add_mutually_exclusive_group()
    grp.add_argument('--fast',   action='store_true', help='전체 15분 고정')
    grp.add_argument('--normal', action='store_true', help='전체 30분 고정')
    grp.add_argument('--slow',   action='store_true', help='전체 60분 고정')
    grp.add_argument('--interval', type=int, metavar='분', help='커스텀 고정 간격(분)')
    parser.add_argument('--once',  action='store_true', help='1회 체크 후 종료')
    parser.add_argument('--pages', type=int, default=DEFAULT_PAGES,
                        help=f'탐색 페이지 수 (기본: {DEFAULT_PAGES} = {DEFAULT_PAGES*40}위)')
    args = parser.parse_args()

    # 고정 간격 결정
    fixed = None
    if args.fast:
        fixed = 15
    elif args.normal:
        fixed = 30
    elif args.slow:
        fixed = 60
    elif args.interval:
        fixed = args.interval

    print('\n' + '█' * 62)
    print('🚀 나눔랩 통합 순위 스케줄러 가동')
    if fixed:
        print(f'   모드: 고정 {fixed}분 간격')
    else:
        print(f'   모드: 상태별 자동 조정 '
              f'(미노출 {INTERVAL_POLICY["unranked"]}분 / '
              f'진입 {INTERVAL_POLICY["entering"]}분 / '
              f'안정 {INTERVAL_POLICY["ranked"]}분)')
    print(f'   탐색 페이지: {args.pages}페이지 ({args.pages * 40}위까지)')
    print('█' * 62 + '\n')

    if args.once:
        run_once(max_pages=args.pages)
        return

    round_num = 0
    while True:
        round_num += 1
        print(f"{'#'*28} Round {round_num} {'#'*28}")
        rank_map = run_once(max_pages=args.pages)

        interval = calc_next_interval(rank_map, fixed_interval=fixed)
        m, s = divmod(interval * 60, 60)
        print(f"😴 다음 체크까지 {m}분 대기 중... (Ctrl+C로 종료)")
        print('─' * 62)
        try:
            time.sleep(interval * 60)
        except KeyboardInterrupt:
            print('\n👋 스케줄러 종료')
            break


if __name__ == '__main__':
    main()
