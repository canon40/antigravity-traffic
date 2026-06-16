"""
rank_booster.py — 미노출 상품 순위 진입 집중 엔진
======================================================
목표: 999위(미노출) 상품들을 네이버 쇼핑 1~100위 내로 진입시키기

전략:
  1. 미노출 상품에 트래픽 90% 집중 (노출 상품은 유지만)
  2. 세션 간격 최소 8분 (기존 15분 → 단축해 하루 세션 수 증가)
  3. Qwen3/Hermes3(Ollama) 로 키워드·체류 전략 실시간 분석
  4. 진입 성공 상품은 자동으로 '유지 모드'로 전환
  5. 24시간 자동 보고서 + 슬랙/텔레그램 알림 (선택)

실행:
  python rank_booster.py            # 바로 시작 (연속 엔진)
  python rank_booster.py --check    # 현재 순위만 체크
  python rank_booster.py --once     # 1회 세션 테스트
"""

import sys
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8', line_buffering=True)
    sys.stderr.reconfigure(encoding='utf-8', line_buffering=True)

import asyncio
import random
import json
import re
import time
import csv
import os
from datetime import datetime
from urllib.parse import quote

import requests
from playwright.async_api import async_playwright

try:
    from playwright_stealth import Stealth
    STEALTH_OK = True
except ImportError:
    STEALTH_OK = False

try:
    import ollama
    OLLAMA_AVAILABLE = True
except ImportError:
    OLLAMA_AVAILABLE = False


# ══════════════════════════════════════════════════════════════
#  ① 집중 대상 상품 정의
#     status: 'boosting' = 미노출→순위 진입 집중
#             'maintain'  = 이미 노출 중 → 유지
#             'skip'      = 임시 제외
# ══════════════════════════════════════════════════════════════
BOOST_TARGETS = [
    # ── 🔴 미노출 집중 공략 ─────────────────────────────────
    {
        'product_id': '12808820913',
        'name': '나눔랩 코팅제 A',
        'url': 'https://smartstore.naver.com/nanumlab/products/12808820913',
        'status': 'boosting',
        'priority': 1,          # 낮을수록 먼저 처리
        'keywords': [
            '유리막코팅제',
        ],
        'primary_keyword': '유리막코팅제',
        'weight': 20,
    },
    {
        'product_id': '12809519826',
        'name': '나눔랩 코팅제 B',
        'url': 'https://smartstore.naver.com/nanumlab/products/12809519826',
        'status': 'boosting',
        'priority': 2,
        'keywords': [
            '유리막코팅제',
        ],
        'primary_keyword': '유리막코팅제',
        'weight': 20,
    },
    # {
    #     'product_id': '12809532969',
    #     'name': '나눔랩 코팅제 C',
    #     'url': 'https://smartstore.naver.com/nanumlab/products/12809532969',
    #     'status': 'boosting',
    #     'priority': 3,
    #     'keywords': [
    #         '자동차 유리막코팅',
    #         '자동차코팅 DIY',
    #         '차량 유리막코팅 셀프',
    #         '나눔랩 코팅제',
    #         '셀프 자동차코팅',
    #     ],
    #     'primary_keyword': '자동차 유리막코팅',
    #     'weight': 12,
    # },
    # {
    #     'product_id': '12809541448',
    #     'name': '나눔랩 코팅제 D',
    #     'url': 'https://smartstore.naver.com/nanumlab/products/12809541448',
    #     'status': 'boosting',
    #     'priority': 4,
    #     'keywords': [
    #         '셀프 유리막코팅제',
    #         '유리막코팅 DIY',
    #         '차 코팅 셀프',
    #         '나눔랩 코팅제',
    #         '자동차코팅제 셀프',
    #     ],
    #     'primary_keyword': '셀프 유리막코팅제',
    #     'weight': 12,
    # },
    # {
    #     'product_id': '12808787263',
    #     'name': '나눔랩 세정·관리제',
    #     'url': 'https://smartstore.naver.com/nanumlab/products/12808787263',
    #     'status': 'boosting',
    #     'priority': 5,
    #     'keywords': [
    #         '세차 관리제',
    #         '셀프세차 세정제',
    #         '나눔랩 세정제',
    #         '차량 세정제 추천',
    #         '세차용품 추천',
    #     ],
    #     'primary_keyword': '세차 관리제',
    #     'weight': 10,
    # },
    # ── 🟡 순위 미확인 상품 (실제 순위에 따라 자동 전환) ──────────
    {
        'product_id': '12639296730',
        'name': '퍼마코트 자동차 코팅제',
        'url': 'https://smartstore.naver.com/nanumlab/products/12639296730',
        'status': 'boosting',   # ⇒ 100위 이내 진입 시 자동으로 maintain 전환
        'priority': 6,
        'keywords': [
            '자동차코팅제',
        ],
        'primary_keyword': '자동차코팅제',
        'weight': 60,
    },
    # {
    #     'product_id': '12634187514',
    #     'name': '나눔랩 코팅 상품',
    #     'url': 'https://smartstore.naver.com/nanumlab/products/12634187514',
    #     'status': 'boosting',   # ⇒ 100위 이내 진입 시 자동으로 maintain 전환
    #     'priority': 7,
    #     'keywords': [
    #         '차량용 유리막코팅',
    #         '차량 코팅제',
    #         '나눔랩 코팅제',
    #         '자동차 코팅 나눔랩',
    #         '차량코팅제 저렴한',
    #     ],
    #     'primary_keyword': '차량용 유리막코팅',
    #     'weight': 10,
    # },
    # ── 🟢 안정 노출 유지 상품 ────────────────────────────────
    # {
    #     'product_id': '10713170202',
    #     'name': '듀라코트 리빙코트',
    #     'url': 'https://smartstore.naver.com/nanumlab/products/10713170202',
    #     'status': 'maintain',   # 현재 4위 유지 중 → 자동 갱신 시 순위 유지되면 maintain 그대로
    #     'priority': 99,
    #     'keywords': [
    #         '리빙코트',
    #         '듀라코트 리빙코트',
    #         '가구 코팅제',
    #     ],
    #     'primary_keyword': '리빙코트',
    #     'weight': 1,   # 유지 상품 — 최소 배분
    # },
]

_WEIGHT_TOTAL = sum(p['weight'] for p in BOOST_TARGETS)
_BOOSTING_TARGETS = [p for p in BOOST_TARGETS if p['status'] == 'boosting']

# ── 순위 임계치: 이 순위 이내면 유지, 초과 시 boosting 자동 전환 ──
RANK_THRESHOLD = 100

def _calc_boost_weight(rank: int, base_weight: int) -> int:
    """순위에 따라 적절한 부스팅 가중치 반환."""
    if rank >= 999:
        return max(base_weight, 18)   # 미노출: 최대 가중치
    elif rank > 300:
        return max(base_weight, 16)
    elif rank > 200:
        return max(base_weight, 14)
    elif rank > 100:
        return max(base_weight, 10)
    else:
        return 1                      # 100위 이내 → 유지

# ══════════════════════════════════════════════════════════════
#  ② 안전 설정 (기존보다 공격적)
# ══════════════════════════════════════════════════════════════
SAFETY = {
    'min_session_gap_sec': 8 * 60,       # 최소 8분 (기존 15분 → 단축)
    'danger_cooldown_sec': 30 * 60,      # 봇 감지 시 30분 쿨다운
    'max_sessions_per_hour': 6,          # 시간당 최대 6회 (기존 4회)
    'daily_cap': 120,                    # 하루 최대 120회
    'headless': True,                    # True = 백그라운드 실행 (CPU 절약)
}

BLOGS = [
    'https://blog.naver.com/hymini1',
    'https://blog.naver.com/selfcoat',
    'https://hymini1.tistory.com/',
]

USER_AGENTS = [
    "Mozilla/5.0 (Linux; Android 14; SM-S928N) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Mobile Safari/537.36",
    "Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Mobile Safari/537.36",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_5) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
]

LOG_FILE = 'boost_log.csv'
LOG_HEADERS = ['날짜', '상품명', '상품ID', '키워드', '시작순위', '종료순위', '체류시간', '결과', '비고']


# ══════════════════════════════════════════════════════════════
#  ③ 전역 세션 상태
# ══════════════════════════════════════════════════════════════
STATE = {
    'last_session_time': 0,
    'sessions_this_hour': 0,
    'hour_start': time.time(),
    'bot_detected_at': 0,
    'consecutive_fails': 0,
    'daily_count': 0,
    'success_count': 0,
    'current_date': datetime.now().strftime('%Y-%m-%d'),
    'rank_cache': {},   # {product_id: {'rank': int, 'checked_at': timestamp}}
    'refresh_count': 0, # 동적 상태 갱신 횟수
}


# ══════════════════════════════════════════════════════════════
#  ④ 유틸리티
# ══════════════════════════════════════════════════════════════
def log_result(product_name, product_id, keyword, start_rank, end_rank, dwell, result, note=''):
    row = {
        '날짜': datetime.now().strftime('%Y-%m-%d %H:%M'),
        '상품명': product_name,
        '상품ID': product_id,
        '키워드': keyword,
        '시작순위': start_rank,
        '종료순위': end_rank,
        '체류시간': dwell,
        '결과': result,
        '비고': note,
    }
    file_exists = os.path.exists(LOG_FILE)
    with open(LOG_FILE, 'a', newline='', encoding='utf-8-sig') as f:
        writer = csv.DictWriter(f, fieldnames=LOG_HEADERS)
        if not file_exists:
            writer.writeheader()
        writer.writerow(row)


def check_rank_simple(keyword: str, product_id: str, pages: int = 3) -> int:
    """
    네이버 모바일 쇼핑 검색 결과에서 상품 순위를 반환.
    pages=3 → 최대 3페이지(약 120개)까지 탐색.
    미발견 시 999 반환.
    """
    headers = {
        'User-Agent': 'Mozilla/5.0 (Linux; Android 14; SM-S928N) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Mobile Safari/537.36',
        'Accept-Language': 'ko-KR,ko;q=0.9',
        'Referer': 'https://m.naver.com',
    }
    pid = str(product_id).strip()
    cumulative = 0

    for page_num in range(pages):
        start = 1 + page_num * 40
        url = f"https://m.search.naver.com/search.naver?query={quote(keyword)}&where=m_shop&start={start}"
        try:
            res = requests.get(url, headers=headers, timeout=15)
            if res.status_code != 200:
                continue
            # 상품 ID 파싱 (순서 유지)
            all_pids = []
            seen = set()
            def add(p):
                if p and p not in seen:
                    seen.add(p)
                    all_pids.append(p)
            # 1. smartstore URL matches (support both / and escaped \u002F)
            for p in re.findall(r'smartstore\.naver\.com(?:/|\\u002F)[^\s"\'\\/]+(?:/|\\u002F)products(?:/|\\u002F)(\d+)', res.text):
                add(p)
            # 2. Generic /products/ or \u002Fproducts\u002F matches
            for p in re.findall(r'(?:/|\\u002F)products(?:/|\\u002F)(\d+)', res.text):
                add(p)
            # 3. JSON channelProductId matches
            for p in re.findall(r'["\']channelProductId["\']?\s*:\s*["\']?(\d+)["\']?', res.text):
                add(p)
            # 4. nv_mid / nvMid fallback
            for p in re.findall(r'[?&]nv_mid=(\d+)', res.text):
                add(p)
            for p in re.findall(r'nvMid["\']?\s*:\s*["\']?(\d+)', res.text):
                add(p)

            if pid in all_pids:
                rank = cumulative + all_pids.index(pid) + 1
                return rank
            cumulative += len(all_pids)
            # 결과가 35개 미만이면 다음 페이지 없음
            if len(all_pids) < 35:
                break
        except Exception as e:
            print(f"⚠️ 순위 조회 오류: {e}")
            continue

    return 999


def pick_target():
    """가중치 룰렛으로 상품 선택."""
    if not _BOOSTING_TARGETS:
        # 모두 유지 상품이면 전체 중 랜덤
        return random.choice(BOOST_TARGETS)
    r = random.uniform(0, _WEIGHT_TOTAL)
    cum = 0
    for t in BOOST_TARGETS:
        cum += t['weight']
        if r <= cum:
            return t
    return BOOST_TARGETS[0]


# ════════════════════════════════════════════════════════════
#  ● 동적 상태 갱신 — 100위 초과 상품 자동 boosting 전환
# ════════════════════════════════════════════════════════════
def refresh_target_status(pages: int = 3) -> list:
    """
    모든 BOOST_TARGETS의 실제 순위를 체크해
    RANK_THRESHOLD(기본 100위) 기준으로 status/weight 자동 조정.
    - 순위 > RANK_THRESHOLD → boosting (가중치 확대)
    - 순위 ≤ RANK_THRESHOLD → maintain (가중치 1로 축소)
    전역 _WEIGHT_TOTAL, _BOOSTING_TARGETS 재계산.
    반환: [{'name', 'rank', 'old_status', 'new_status', 'changed'}]
    """
    global _WEIGHT_TOTAL, _BOOSTING_TARGETS

    print("\n" + "="*60)
    print("🔄 [자동 상태 갱신] 전체 상품 순위 체크 시작...")
    print(f"   탐색 범위: {pages}페이지 ({pages*40}위까지) | 임계적: {RANK_THRESHOLD}위")
    print("="*60)

    report = []
    changed_list = []

    for t in BOOST_TARGETS:
        kw  = t['primary_keyword']
        pid = t['product_id']
        old_status = t['status']
        old_weight = t['weight']

        print(f"  🔍 {t['name']} '{kw}' ...", end=' ', flush=True)
        rank = check_rank_simple(kw, pid, pages=pages)
        rank_str = f"{rank}위" if rank < 999 else "미노출"

        # 상태 판정
        if rank <= RANK_THRESHOLD:
            new_status = 'maintain'
            new_weight = 1
        else:
            new_status = 'boosting'
            new_weight = _calc_boost_weight(rank, old_weight)

        # 적용
        t['status'] = new_status
        t['weight'] = new_weight

        icon = '✅' if new_status == 'maintain' else '🔴'
        change_arrow = ''
        changed = old_status != new_status
        if changed:
            change_arrow = f" [{old_status} → {new_status}] ⚡"
            changed_list.append(f"{t['name']}: {old_status}→{new_status} ({rank_str})")

        print(f"{icon} {rank_str}{change_arrow}")

        report.append({
            'name': t['name'], 'rank': rank,
            'old_status': old_status, 'new_status': new_status,
            'changed': changed,
        })
        time.sleep(random.uniform(1.5, 3.0))  # 네이버 요청 간격

    # 전역 변수 재계산
    _WEIGHT_TOTAL = sum(p['weight'] for p in BOOST_TARGETS)
    _BOOSTING_TARGETS[:] = [p for p in BOOST_TARGETS if p['status'] == 'boosting']

    # 통계 요약
    boost_cnt    = len(_BOOSTING_TARGETS)
    maintain_cnt = len(BOOST_TARGETS) - boost_cnt
    entered_now  = [r for r in report if r['changed'] and r['new_status'] == 'maintain']
    dropped_now  = [r for r in report if r['changed'] and r['new_status'] == 'boosting']

    print(f"\n📊 갱신 결과: 부스팅 {boost_cnt}개 / 유지 {maintain_cnt}개")
    if entered_now:
        print(f"  🎉 새로 진입 성공! (maintain 전환): {[r['name'] for r in entered_now]}")
    if dropped_now:
        print(f"  ⚠️  순위 하락 감지 (boosting 복구): {[r['name'] for r in dropped_now]}")
    print(f"  부스팅 대상:")
    for t in sorted(_BOOSTING_TARGETS, key=lambda x: x['priority']):
        pct = round(t['weight'] / _WEIGHT_TOTAL * 100) if _WEIGHT_TOTAL else 0
        print(f"    [{pct:2d}%] {t['name']} — {t['primary_keyword']}")
    print("="*60 + "\n")
    STATE['refresh_count'] += 1
    return report


def safety_wait() -> int:
    """현재 세션 간격/횟수 제한에 따른 대기 시간(초) 반환. 0이면 바로 진행."""
    now = time.time()

    # 봇 감지 쿨다운
    if STATE['bot_detected_at'] > 0:
        elapsed = now - STATE['bot_detected_at']
        if elapsed < SAFETY['danger_cooldown_sec']:
            return int(SAFETY['danger_cooldown_sec'] - elapsed)

    # 최소 세션 간격
    if STATE['last_session_time'] > 0:
        elapsed = now - STATE['last_session_time']
        if elapsed < SAFETY['min_session_gap_sec']:
            return int(SAFETY['min_session_gap_sec'] - elapsed)

    # 시간당 횟수
    if now - STATE['hour_start'] > 3600:
        STATE['hour_start'] = now
        STATE['sessions_this_hour'] = 0
    if STATE['sessions_this_hour'] >= SAFETY['max_sessions_per_hour']:
        return int(3600 - (now - STATE['hour_start']))

    return 0


async def ask_ai_strategy(product_name: str, keyword: str, current_rank: int) -> dict:
    """
    Ollama(Qwen3 or Hermes3)로 최적 체류 전략 질의.
    실패 시 안전 기본값 반환.
    """
    default = {'dwell_time': 90, 'scroll_speed': 3, 'mouse_jitter': 0.2, 'search_pattern': '직접검색'}
    if not OLLAMA_AVAILABLE:
        return default

    # 사용 가능한 모델 우선순위
    models_to_try = ['hermes3:latest', 'qwen3:8b', 'llama3:latest', 'gemma4:e2b']

    prompt = f"""
당신은 네이버 쇼핑 상위노출 전문 마케터입니다.
아래 상황에서 봇으로 탐지되지 않으면서 클릭신호를 최대화할 세션 전략을 JSON으로만 반환하세요.

상황:
- 상품: {product_name}
- 키워드: {keyword}
- 현재 순위: {current_rank}위 (999=미노출)
- 목표: 네이버 쇼핑 100위 이내 진입

규칙:
- 순위가 999(미노출)이면 dwell_time을 120초 이상으로 설정
- 순위가 50~100이면 dwell_time을 90~110초
- 순위가 50 이내면 dwell_time을 70~90초

반드시 아래 JSON만 출력 (마크다운 없이):
{{"dwell_time": (정수 60~150), "scroll_speed": (정수 1~5), "mouse_jitter": (실수 0.1~0.5), "search_pattern": "직접검색"}}
"""

    for model in models_to_try:
        try:
            response = await asyncio.wait_for(
                asyncio.to_thread(ollama.chat, model=model,
                                  messages=[{'role': 'user', 'content': prompt}]),
                timeout=20.0
            )
            content = response['message']['content']
            # JSON 추출
            m = re.search(r'\{[^{}]+\}', content, re.DOTALL)
            if m:
                data = json.loads(m.group())
                print(f"🧠 [{model}] 전략: 체류={data.get('dwell_time')}s | 스크롤={data.get('scroll_speed')} | 지터={data.get('mouse_jitter')}")
                return data
        except asyncio.TimeoutError:
            continue
        except Exception:
            continue

    print("⚠️ AI 전략 실패 → 기본값 사용")
    return default


# ══════════════════════════════════════════════════════════════
#  ⑤ 핵심 트래픽 세션
# ══════════════════════════════════════════════════════════════
async def run_boost_session(target: dict, keyword: str) -> dict:
    """
    1회 트래픽 세션 실행.
    반환: {'success': bool, 'start_rank': int, 'end_rank': int, 'dwell': int}
    """
    product_id = target['product_id']
    product_url = target['url']
    product_name = target['name']

    print(f"\n{'='*58}")
    print(f"[{datetime.now().strftime('%H:%M:%S')}] 🚀 세션 시작")
    print(f"  📦 상품: {product_name}  ({product_id})")
    print(f"  🔑 키워드: {keyword}")
    print(f"  🔴 상태: {target['status'].upper()}")
    print(f"{'='*58}")

    # 사전 순위 체크
    start_rank = await asyncio.to_thread(check_rank_simple, keyword, product_id)
    rank_str = f"{start_rank}위" if start_rank < 999 else "미노출"
    print(f"📊 현재 순위: {rank_str}")

    # AI 전략 수립
    strategy = await ask_ai_strategy(product_name, keyword, start_rank)
    dwell_time = strategy.get('dwell_time', 90)
    scroll_spd = strategy.get('scroll_speed', 3)
    jitter = strategy.get('mouse_jitter', 0.2)

    ua = random.choice(USER_AGENTS)
    is_mobile = 'Android' in ua or 'iPhone' in ua

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=SAFETY['headless'],
            args=[
                '--disable-blink-features=AutomationControlled',
                '--no-first-run',
                '--disable-infobars',
                '--lang=ko-KR',
            ]
        )
        ctx = await browser.new_context(
            viewport={
                'width': random.choice([375, 390, 412]) if is_mobile else random.randint(1366, 1920),
                'height': random.choice([812, 844, 915]) if is_mobile else random.randint(768, 1080),
            },
            user_agent=ua,
            is_mobile=is_mobile,
            locale='ko-KR',
            timezone_id='Asia/Seoul',
            geolocation={
                'latitude': 37.5665 + random.uniform(-0.08, 0.08),
                'longitude': 126.9780 + random.uniform(-0.08, 0.08),
            },
            permissions=['geolocation'],
        )

        page = await ctx.new_page()

        # 지문 방지 스크립트
        await page.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
            Object.defineProperty(navigator, 'plugins', {get: () => [1,2,3,4,5]});
            Object.defineProperty(navigator, 'languages', {get: () => ['ko-KR','ko','en-US','en']});
            window.chrome = {runtime: {}};
        """)

        if STEALTH_OK:
            await Stealth().apply_stealth_async(page)

        try:
            # ── Step 1: 네이버 쇼핑 검색으로 상품 클릭 ──
            naver_shop_url = f"https://m.search.naver.com/search.naver?query={quote(keyword)}&where=m_shop"
            print(f"🔍 네이버 쇼핑 검색 진입...")
            await page.goto("https://m.naver.com", wait_until="domcontentloaded")
            await asyncio.sleep(random.uniform(1.0, 2.5))

            # 검색창 타이핑
            try:
                await page.click('#MM_SEARCH_FAKE', timeout=2000)
                await asyncio.sleep(random.uniform(0.3, 0.8))
            except Exception:
                pass

            search_input = page.locator('#query')
            try:
                await search_input.focus(timeout=3000)
            except Exception:
                await page.goto(naver_shop_url, wait_until="domcontentloaded")
                await asyncio.sleep(2)
                # 상품 직접 방문으로 폴백
                await page.goto(product_url, wait_until="domcontentloaded")
                await _dwell_on_product(page, dwell_time, scroll_spd, jitter)
                end_rank = await asyncio.to_thread(check_rank_simple, keyword, product_id)
                await browser.close()
                return {'success': True, 'start_rank': start_rank, 'end_rank': end_rank, 'dwell': dwell_time}

            # 사람처럼 타이핑
            for char in keyword:
                await page.keyboard.type(char)
                await asyncio.sleep(random.uniform(jitter * 0.5, jitter * 2.0))

            # 가끔 오타 후 수정
            if random.random() < 0.12:
                await page.keyboard.type('ㅇ')
                await asyncio.sleep(random.uniform(0.4, 0.8))
                await page.keyboard.press('Backspace')
                await asyncio.sleep(random.uniform(0.2, 0.5))

            await search_input.press('Enter')
            await asyncio.sleep(random.uniform(2.0, 3.5))

            # 봇 감지 확인
            if await _is_bot_detected(page):
                print("🚨 봇 감지 — 세션 중단")
                STATE['bot_detected_at'] = time.time()
                await browser.close()
                return {'success': False, 'start_rank': start_rank, 'end_rank': start_rank, 'dwell': 0}

            # ── Step 2: 검색 결과에서 상품 탐색 후 클릭 ──
            print(f"🔎 검색 결과에서 상품 찾는 중...")
            # 쇼핑 탭 클릭 시도
            try:
                shop_tab = page.locator('a[href*="where=m_shop"], a:has-text("쇼핑")')
                if await shop_tab.count() > 0:
                    await shop_tab.first.click()
                    await asyncio.sleep(random.uniform(1.5, 2.5))
            except Exception:
                pass

            # 상품 링크 직접 탐색
            product_link = page.locator(f'a[href*="{product_id}"]')
            clicked_from_search = False
            if await product_link.count() > 0:
                print(f"✅ 검색 결과에서 상품 발견 → 클릭")
                await product_link.first.scroll_into_view_if_needed()
                await asyncio.sleep(random.uniform(0.5, 1.5))
                await product_link.first.click()
                clicked_from_search = True
                await asyncio.sleep(random.uniform(2.0, 4.0))
            else:
                # 검색 결과에서 못 찾으면 블로그 경유 후 직접 이동
                print(f"⚠️ 검색 결과 미발견 → 블로그 경유 진입")
                blog = random.choice(BLOGS)
                await page.goto(blog.replace('blog.naver.com', 'm.blog.naver.com'), wait_until="domcontentloaded")
                await asyncio.sleep(random.uniform(3.0, 6.0))
                await _human_scroll(page, scroll_spd, jitter)
                # 상품 페이지로 이동
                await page.evaluate(f"window.location.href = '{product_url}'")
                await asyncio.sleep(random.uniform(2.0, 4.0))

            if await _is_bot_detected(page):
                print("🚨 상품 이동 후 봇 감지 — 중단")
                STATE['bot_detected_at'] = time.time()
                await browser.close()
                return {'success': False, 'start_rank': start_rank, 'end_rank': start_rank, 'dwell': 0}

            # ── Step 3: 상품 페이지 체류 ──
            print(f"⏱️ 상품 페이지 체류 중 ({dwell_time}초)...")
            await _dwell_on_product(page, dwell_time, scroll_spd, jitter)

            # ── Step 4: 종료 후 순위 재확인 ──
            end_rank = await asyncio.to_thread(check_rank_simple, keyword, product_id)
            end_str = f"{end_rank}위" if end_rank < 999 else "미노출"
            delta = start_rank - end_rank
            delta_str = f"{'▲' if delta > 0 else ('▼' if delta < 0 else '─')} {abs(delta)}"
            print(f"📊 세션 결과: {rank_str} → {end_str} ({delta_str})")

            # 순위 캐시 업데이트
            STATE['rank_cache'][product_id] = {'rank': end_rank, 'checked_at': time.time()}

            await browser.close()
            return {'success': True, 'start_rank': start_rank, 'end_rank': end_rank, 'dwell': dwell_time}

        except Exception as e:
            print(f"❌ 세션 오류: {e}")
            try:
                await browser.close()
            except Exception:
                pass
            return {'success': False, 'start_rank': start_rank, 'end_rank': start_rank, 'dwell': 0}


async def _human_scroll(page, scroll_speed: int, jitter: float):
    """블로그 경유 등에서 인간의 스크롤을 시뮬레이션."""
    base_sleep = 15.0 / max(scroll_speed, 1)
    scroll_count = random.randint(5, 10)
    for i in range(scroll_count):
        delta = random.randint(300, 800)
        await page.mouse.wheel(0, delta)
        await asyncio.sleep(random.uniform(base_sleep * 0.4, base_sleep * 1.6))
        if random.random() < jitter:
            await page.mouse.move(
                random.randint(50, 350),
                random.randint(100, 650)
            )
        if i == scroll_count // 2:
            await asyncio.sleep(random.uniform(2.0, 5.0))


async def _dwell_on_product(page, dwell_time: int, scroll_speed: int, jitter: float):
    """상품 페이지에서 자연스럽게 체류."""
    base_sleep = 12.0 / max(scroll_speed, 1)
    scroll_count = random.randint(6, 14)
    elapsed = 0
    for i in range(scroll_count):
        delta = random.randint(250, 900)
        await page.mouse.wheel(0, delta)
        sleep_t = random.uniform(base_sleep * 0.4, base_sleep * 1.6)
        await asyncio.sleep(sleep_t)
        elapsed += sleep_t
        # 자연스러운 마우스 이동
        if random.random() < jitter:
            await page.mouse.move(
                random.randint(30, 380),
                random.randint(80, 700),
            )
        # 중간 멈춤
        if i == scroll_count // 3:
            pause = random.uniform(2.0, 5.0)
            await asyncio.sleep(pause)
            elapsed += pause
        # 가끔 위로 스크롤 (읽는 척)
        if random.random() < 0.2:
            await page.mouse.wheel(0, -random.randint(100, 400))
            await asyncio.sleep(random.uniform(1.0, 2.5))
            elapsed += 2

    # 남은 체류 시간 채우기
    remaining = dwell_time - elapsed
    if remaining > 0:
        await asyncio.sleep(remaining)


async def _is_bot_detected(page) -> bool:
    """봇 감지 여부 확인."""
    try:
        url = page.url.lower()
        for bad in ['captcha', 'sorry/index', 'nid.naver.com/login', 'robot']:
            if bad in url:
                return True
        content = await page.content()
        for bad in ['자동등록방지', '로봇이 아닙니다', '비정상적인 접근', '보안절차']:
            if bad in content:
                return True
    except Exception:
        pass
    return False


# ══════════════════════════════════════════════════════════════
#  ⑥ 순위 전체 체크 (진입 보고)
# ══════════════════════════════════════════════════════════════
def check_all_ranks():
    """모든 boosting 대상 상품의 현재 순위를 출력."""
    print("\n" + "="*60)
    print("📊 미노출 상품 순위 현황 체크")
    print("="*60)
    results = []
    for t in _BOOSTING_TARGETS:
        kw = t['primary_keyword']
        print(f"🔍 [{t['name']}] '{kw}' 검색 중...", end=' ', flush=True)
        rank = check_rank_simple(kw, t['product_id'], pages=5)
        status_icon = '🟢' if rank <= 100 else ('🟡' if rank <= 300 else '🔴')
        rank_str = f"{rank}위" if rank < 999 else "미노출"
        print(f"{status_icon} {rank_str}")
        results.append({'name': t['name'], 'keyword': kw, 'rank': rank})
        time.sleep(random.uniform(2.0, 4.0))  # 요청 간격

    print("\n📋 요약:")
    entered = [r for r in results if r['rank'] <= 100]
    near = [r for r in results if 100 < r['rank'] <= 300]
    unranked = [r for r in results if r['rank'] > 300]
    print(f"  🟢 100위 이내 진입: {len(entered)}개")
    for r in entered:
        print(f"       • {r['name']} — '{r['keyword']}' {r['rank']}위")
    print(f"  🟡 100~300위 근접: {len(near)}개")
    for r in near:
        print(f"       • {r['name']} — '{r['keyword']}' {r['rank']}위")
    print(f"  🔴 미노출/300위 밖: {len(unranked)}개")
    for r in unranked:
        rank_str = f"{r['rank']}위" if r['rank'] < 999 else "미노출"
        print(f"       • {r['name']} — '{r['keyword']}' {rank_str}")
    print("="*60)
    return results


# ══════════════════════════════════════════════════════════════
#  ⑦ 일일 보고서
# ══════════════════════════════════════════════════════════════
async def daily_report():
    """하루 성과 요약 + AI 분석."""
    print("\n" + "🌅"*20)
    print("📝 일일 성과 보고서")
    print("🌅"*20)

    # CSV 데이터 읽기
    try:
        import csv as _csv
        rows = []
        if os.path.exists(LOG_FILE):
            with open(LOG_FILE, 'r', encoding='utf-8-sig') as f:
                reader = _csv.DictReader(f)
                today = datetime.now().strftime('%Y-%m-%d')
                rows = [r for r in reader if r['날짜'].startswith(today)]
    except Exception:
        rows = []

    total = len(rows)
    success = sum(1 for r in rows if r.get('결과') == '성공')
    entered = [r for r in rows if int(r.get('종료순위', 999)) <= 100 and int(r.get('시작순위', 999)) > 100]

    print(f"  총 세션: {total}회 | 성공: {success}회 | 성공률: {round(success/total*100) if total else 0}%")
    print(f"  신규 순위 진입 성공: {len(entered)}건")
    for r in entered:
        print(f"    ✨ {r.get('상품명')} — '{r.get('키워드')}' → {r.get('종료순위')}위")

    # AI 분석
    if OLLAMA_AVAILABLE and rows:
        data_str = json.dumps(rows[-10:], ensure_ascii=False)
        prompt = f"""
너는 나눔랩 스마트스토어 마케팅 담당자야.
아래 오늘 트래픽 작업 로그를 분석해서 황영민 대표님께 보고할 간략한 성과 보고서를 한국어로 써줘.
(5줄 이내, 핵심만, 친근하게)
데이터: {data_str}
"""
        for model in ['hermes3:latest', 'qwen3:8b', 'llama3:latest']:
            try:
                resp = await asyncio.wait_for(
                    asyncio.to_thread(ollama.chat, model=model, messages=[{'role': 'user', 'content': prompt}]),
                    timeout=30
                )
                print(f"\n🤖 AI 분석:\n{resp['message']['content']}\n")
                break
            except Exception:
                continue


# ══════════════════════════════════════════════════════════════
#  ⑧ 메인 엔진 루프
# ══════════════════════════════════════════════════════════════
async def main_engine():
    global STATE

    print("\n" + "#"*62)
    print("🚀 나눔랩 순위 진입 엔진 가동 (동적 상태 관리 v2)")
    print(f"   전체 대상 상품: {len(BOOST_TARGETS)}개")
    print(f"   순위 임계치: {RANK_THRESHOLD}위 (충족 → maintain, 초과 → boosting 자동 전환)")
    print(f"   세션 간격: 최소 {SAFETY['min_session_gap_sec']//60}분")
    print(f"   시간당 최대: {SAFETY['max_sessions_per_hour']}회")
    print(f"   헤드리스: {'ON (백그라운드)' if SAFETY['headless'] else 'OFF (창 표시)'}")
    print("#"*62 + "\n")

    # ── 시작 전 동적 상태 갱신: 실제 순위에 따라 status/weight 재설정 ──
    print("🔄 엔진 가동 전 순위 자동 감지 & 상태 설정...")
    await asyncio.to_thread(refresh_target_status, 3)
    await asyncio.sleep(5)

    session_count = 0
    REFRESH_EVERY = 20  # N세션마다 상태 재검진

    while True:
        today = datetime.now().strftime('%Y-%m-%d')

        # 날짜 바뀌면 일일 보고 + 리셋
        if STATE['current_date'] != today:
            await daily_report()
            STATE['current_date'] = today
            STATE['daily_count'] = 0
            STATE['success_count'] = 0
            print(f"🌅 새 날짜({today}) — 카운터 초기화")

        # 하루 최대 세션 도달 시 대기
        if STATE['daily_count'] >= SAFETY['daily_cap']:
            print(f"🛑 오늘 최대 세션({SAFETY['daily_cap']}회) 도달 — 자정까지 대기")
            await asyncio.sleep(3600)
            continue

        # 안전 대기 확인
        wait = safety_wait()
        if wait > 0:
            m, s = divmod(wait, 60)
            print(f"⏳ {m}분 {s}초 대기 중...", end='\r')
            await asyncio.sleep(min(wait, 30))
            continue

        # 상품 + 키워드 선택
        target = pick_target()
        # boosting 상품은 키워드를 돌아가며 사용
        kw_idx = session_count % len(target['keywords'])
        keyword = target['keywords'][kw_idx]

        # 세션 실행
        result = await run_boost_session(target, keyword)
        session_count += 1
        STATE['daily_count'] += 1
        STATE['last_session_time'] = time.time()
        STATE['sessions_this_hour'] += 1

        if result['success']:
            STATE['success_count'] += 1
            STATE['consecutive_fails'] = 0
        else:
            STATE['consecutive_fails'] += 1
            if STATE['consecutive_fails'] >= 3:
                print(f"⚠️ 연속 {STATE['consecutive_fails']}회 실패 — 20분 추가 대기")
                await asyncio.sleep(20 * 60)
                STATE['consecutive_fails'] = 0

        # 로그 기록
        log_result(
            target['name'], target['product_id'], keyword,
            result['start_rank'], result['end_rank'],
            result['dwell'], '성공' if result['success'] else '실패'
        )

        # 진입 성공 감지 (999 → 100 이내)
        if result['start_rank'] > RANK_THRESHOLD and result['end_rank'] <= RANK_THRESHOLD:
            print(f"\n🎉🎉 신규 진입 성공! [{target['name']}] '{keyword}' {result['end_rank']}위 !\n")

        # ── N세션마다 동적 상태 갱신 ────────────────────────────
        if session_count % REFRESH_EVERY == 0:
            print(f"\n🔄 [{session_count}세션 완료] 순위 재체크 및 상태 갱신...")
            await asyncio.to_thread(refresh_target_status, 3)

        # 다음 세션 대기 (5~12분 랜덤)
        next_wait = random.randint(
            SAFETY['min_session_gap_sec'],
            SAFETY['min_session_gap_sec'] + 4 * 60
        )
        m, s = divmod(next_wait, 60)
        boost_cnt = len(_BOOSTING_TARGETS)
        maintain_cnt = len(BOOST_TARGETS) - boost_cnt
        print(f"😴 다음 세션까지 {m}분 {s}초 대기...")
        print(f"   [현황] 오늘 {STATE['daily_count']}회 | 성공 {STATE['success_count']}회 | 부스팅 {boost_cnt}개 | 유지 {maintain_cnt}개")
        print("-" * 58)
        await asyncio.sleep(next_wait)


# ══════════════════════════════════════════════════════════════
#  ⑨ 진입점
# ══════════════════════════════════════════════════════════════
if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='나눔랩 미노출 상품 순위 진입 엔진')
    parser.add_argument('--check', action='store_true', help='현재 순위만 체크 후 종료')
    parser.add_argument('--once', action='store_true', help='1회 세션 테스트')
    parser.add_argument('--headless', action='store_true', help='헤드리스 모드 강제 ON')
    parser.add_argument('--show', action='store_true', help='브라우저 창 표시 (headless=OFF)')
    args = parser.parse_args()

    if args.headless:
        SAFETY['headless'] = True
    if args.show:
        SAFETY['headless'] = False

    if args.check:
        check_all_ranks()

    elif args.once:
        async def _once():
            target = _BOOSTING_TARGETS[0]
            keyword = target['primary_keyword']
            print(f"🧪 1회 테스트: [{target['name']}] '{keyword}'")
            result = await run_boost_session(target, keyword)
            log_result(
                target['name'], target['product_id'], keyword,
                result['start_rank'], result['end_rank'],
                result['dwell'], '성공' if result['success'] else '실패'
            )
            print(f"\n✅ 테스트 완료: {'성공' if result['success'] else '실패'}")
            print(f"   순위 변화: {result['start_rank']} → {result['end_rank']}")
        asyncio.run(_once())

    else:
        asyncio.run(main_engine())
