import sys
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8', line_buffering=True)
    sys.stderr.reconfigure(encoding='utf-8', line_buffering=True)

import asyncio
import random
import subprocess
import os
import time
import math
import json
import requests
import pandas as pd
from bs4 import BeautifulSoup
from datetime import datetime
from urllib.parse import quote
from playwright.async_api import async_playwright
from playwright_stealth import Stealth

try:
    import ollama
    OLLAMA_AVAILABLE = True
except ImportError:
    OLLAMA_AVAILABLE = False

# ============================================================
# [ 퍼마코트 마스터 설정 ]
# ============================================================
CONFIG = {
    'keyword': '자동차코팅제',
    'store_name': '나눔랩',
    'target_url': 'https://smartstore.naver.com/nanumlab',
    'blogs': [
        'https://blog.naver.com/hymini1',
        'https://blog.naver.com/selfcoat',
        'https://hymini1.tistory.com/'
    ],
    'base_daily_hits': 85,
    'growth_rate': 1.1,
    'start_date': datetime.now().strftime("%Y-%m-%d")
}

# ============================================================
# [ 다상품 가중치 트래픽 분산 설정 ]
# 각 상품별로 연동 키워드 + 가중치(weight) 지정
# weight 합계는 자동 정규화 — 높을수록 트래픽 더 많이 배분
# ============================================================
PRODUCT_TRAFFIC_MAP = [
    # ── 현재 노출 중 상품 (순위 유지 + 강화) ──────────────────
    {
        'product_id': '12639296730',
        'name': '퍼마코트 자동차 코팅제',
        'url': 'https://smartstore.naver.com/nanumlab/products/12639296730',
        'keywords': [
            '퍼마코트 자동차 코팅제',
            '자동차코팅제',
            '자동차코팅제 추천',
            '셀프 유리막 코팅',
            '차 코팅제 추천',
        ],
        'weight': 20,   # 현재 2위 — 유지하며 '셀프 유리막 코팅' 진입 병행
    },
    {
        'product_id': '10713170202',
        'name': '듀라코트 리빙코트',
        'url': 'https://smartstore.naver.com/nanumlab/products/10713170202',
        'keywords': [
            '리빙코트',
            '듀라코트 리빙코트',
            '실내 코팅제',
            '가구 코팅제',
            '셀프 가구 코팅',
        ],
        'weight': 15,   # 현재 3위 — 유지 + '듀라코트 리빙코트' 키워드 진입
    },
    # ── 520위 밖 미노출 상품 (집중 트래픽 투입) ────────────────
    {
        'product_id': '12808820913',
        'name': '나눔랩 코팅제 A',
        'url': 'https://smartstore.naver.com/nanumlab/products/12808820913',
        'keywords': [
            '나눔랩 코팅제',
            '유리막 코팅제',
            '셀프 유리막코팅제',
            '유리막코팅제 가성비',
        ],
        'weight': 12,
    },
    {
        'product_id': '12809519826',
        'name': '나눔랩 코팅제 B',
        'url': 'https://smartstore.naver.com/nanumlab/products/12809519826',
        'keywords': [
            '유리막코팅제 추천',
            '나눔랩 코팅제',
            '자동차 유리막 코팅 추천',
            '차량 코팅제 추천',
        ],
        'weight': 12,
    },
    {
        'product_id': '12809532969',
        'name': '나눔랩 코팅제 C',
        'url': 'https://smartstore.naver.com/nanumlab/products/12809532969',
        'keywords': [
            '자동차 유리막코팅',
            '나눔랩 코팅제',
            '자동차코팅 DIY',
            '차량 유리막코팅 셀프',
        ],
        'weight': 12,
    },
    {
        'product_id': '12809541448',
        'name': '나눔랩 코팅제 D',
        'url': 'https://smartstore.naver.com/nanumlab/products/12809541448',
        'keywords': [
            '셀프 유리막코팅제',
            '나눔랩 코팅제',
            '유리막코팅 DIY',
            '차 코팅 셀프',
        ],
        'weight': 12,
    },
    {
        'product_id': '12808787263',
        'name': '나눔랩 세정·관리제',
        'url': 'https://smartstore.naver.com/nanumlab/products/12808787263',
        'keywords': [
            '세차 관리제',
            '나눔랩 세정제',
            '차량 세정제 추천',
            '셀프세차 세정제',
        ],
        'weight': 10,
    },
    {
        'product_id': '12634187514',
        'name': '나눔랩 코팅 상품',
        'url': 'https://smartstore.naver.com/nanumlab/products/12634187514',
        'keywords': [
            '차량용 유리막코팅',
            '나눔랩 코팅제',
            '차량 코팅제',
            '자동차 코팅 추천',
        ],
        'weight': 7,
    },
]

# ── 가중치 누적합 (선택 시 사용) ─────────────────────────────
_WEIGHT_TOTAL = sum(p['weight'] for p in PRODUCT_TRAFFIC_MAP)

# ============================================================
# [ 안전 설정 ]
# ============================================================
FOCUS_MODE = {
    'enabled': True,
    'min_session_gap_sec': 15 * 60,      # 세션 간 최소 15분
    'danger_cooldown_sec': 45 * 60,      # 봇 감지 시 45분 강제 쿨다운
    'max_sessions_per_hour': 4,          # 시간당 최대 4회
    'daily_focus_cap': 80,               # 하루 최대 세션 수
}

# ============================================================
# [ 안전 유저 에이전트 풀 ]
# ============================================================
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_4_1) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_6) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_4 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (Linux; Android 14; SM-S928N) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Mobile Safari/537.36",
    "Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Mobile Safari/537.36",
]

# ============================================================
# [ 세션 상태 추적 (전역) ]
# ============================================================
SESSION_STATE = {
    'last_session_time': 0,
    'sessions_this_hour': 0,
    'hour_start': time.time(),
    'focus_count_today': 0,
    'bot_detected_at': 0,
    'consecutive_fails': 0,
}


class PermacoatAutonomousEngine:
    def __init__(self):
        self.config = CONFIG.copy()
        self.focus = FOCUS_MODE.copy()
        self.script_dir = "security_vault"
        if not os.path.exists(self.script_dir):
            os.makedirs(self.script_dir)
        self.daily_hits_count = 0
        self.fail_hits_count = 0
        self.current_date_str = datetime.now().strftime("%Y-%m-%d")
        self.run_keyword = self.config['keyword']
        self.config_data = {}

    # ── 설정 로드 ──────────────────────────────────────────
    def load_dynamic_config(self):
        try:
            with open("config.json", "r", encoding="utf-8") as f:
                config_data = json.load(f)
            products = config_data.get("products", [])
            product_urls = [p["url"] for p in products if "url" in p]
            if not product_urls:
                product_urls = config_data.get("product_urls", [])
            if product_urls:
                self.config['target_products'] = product_urls
            blogs = config_data.get("blog_urls", [])
            if blogs:
                self.config['blogs'] = blogs
            self.config['store_name'] = config_data.get("store_name", "나눔랩")
            self.config_data = config_data
            print("⚙️ config.json 동적 반영 완료")
        except Exception as e:
            print(f"⚠️ config.json 로드 실패: {e}. 기본 설정 사용")
            self.config_data = {}

    # ── 가중치 기반 상품 + 키워드 선택 ─────────────────────────
    def pick_keyword_and_product(self):
        """
        PRODUCT_TRAFFIC_MAP의 가중치(weight)에 비례하여 상품 선택 후,
        해당 상품의 키워드 중 하나를 랜덤 선택.
        """
        global SESSION_STATE

        # 가중치 룰렛 선택
        r = random.uniform(0, _WEIGHT_TOTAL)
        cumulative = 0
        chosen = PRODUCT_TRAFFIC_MAP[0]
        for entry in PRODUCT_TRAFFIC_MAP:
            cumulative += entry['weight']
            if r <= cumulative:
                chosen = entry
                break

        product_id = chosen['product_id']
        product_url = chosen['url']
        keyword = random.choice(chosen['keywords'])

        SESSION_STATE['focus_count_today'] += 1
        pct = round(chosen['weight'] / _WEIGHT_TOTAL * 100)
        print(f"🎯 [{chosen['name']} | {pct}% 배분] 키워드: '{keyword}'")

        self.run_keyword = keyword
        return keyword, product_url, product_id

    # ── 안전 딜레이 체크 ────────────────────────────────────
    def safety_check_delay(self):
        """세션 간격 및 시간당 횟수 제한 확인"""
        global SESSION_STATE
        now = time.time()

        # 봇 감지 쿨다운 확인
        if SESSION_STATE['bot_detected_at'] > 0:
            elapsed = now - SESSION_STATE['bot_detected_at']
            if elapsed < self.focus['danger_cooldown_sec']:
                wait = self.focus['danger_cooldown_sec'] - elapsed
                print(f"🛡️ [봇 감지 쿨다운] {int(wait//60)}분 {int(wait%60)}초 대기 중...")
                return int(wait)

        # 최소 세션 간격 확인
        if SESSION_STATE['last_session_time'] > 0:
            elapsed = now - SESSION_STATE['last_session_time']
            min_gap = self.focus['min_session_gap_sec']
            if elapsed < min_gap:
                wait = min_gap - elapsed
                print(f"⏳ [안전 간격] 최소 {int(min_gap//60)}분 간격 준수 — {int(wait//60)}분 {int(wait%60)}초 대기...")
                return int(wait)

        # 시간당 최대 횟수 확인
        if now - SESSION_STATE['hour_start'] > 3600:
            SESSION_STATE['hour_start'] = now
            SESSION_STATE['sessions_this_hour'] = 0

        if SESSION_STATE['sessions_this_hour'] >= self.focus['max_sessions_per_hour']:
            wait = 3600 - (now - SESSION_STATE['hour_start'])
            print(f"🚦 [시간당 제한] 이번 시간 {self.focus['max_sessions_per_hour']}회 완료 — {int(wait//60)}분 대기...")
            return int(wait)

        return 0

    # ── Llama 전략 수립 ─────────────────────────────────────
    async def ask_llama_strategy(self, success_log):
        if not OLLAMA_AVAILABLE:
            print("🤖 Ollama 미설치 — 기본 전략값으로 진행")
            return {"dwell_time": 85, "scroll_speed": 3, "mouse_jitter": 0.25, "search_pattern": "직접검색"}

        print("🧠 [Llama] 데이터 분석 및 전략 수립 중...")
        prompt = f"""
        당신은 네이버 쇼핑 상위 노출 전문가입니다.
        아래 로그를 분석해서 '걸릴 확률 0%'를 위한 다음 작업 값을 JSON으로만 반환하세요.
        로그: {success_log}

        반드시 아래 JSON 형식만 반환(마크다운 없이):
        {{
            "dwell_time": (60~120 사이 정수),
            "scroll_speed": (1~5 사이 정수),
            "mouse_jitter": (0.1~0.5 사이 실수),
            "search_pattern": "직접검색" 또는 "연관검색어"
        }}
        """
        try:
            response = await asyncio.wait_for(
                asyncio.to_thread(
                    ollama.chat,
                    model='llama3',
                    messages=[{'role': 'user', 'content': prompt}]
                ),
                timeout=30.0
            )
            content = response['message']['content']
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0].strip()
            elif "```" in content:
                content = content.split("```")[1].split("```")[0].strip()
            strategy = json.loads(content)
            print(f"✅ [Llama] 체류: {strategy.get('dwell_time')}초 | 스크롤: {strategy.get('scroll_speed')} | 지터: {strategy.get('mouse_jitter')}")
            return strategy
        except Exception as e:
            print(f"⚠️ Llama 분석 실패, 기본값 사용: {e}")
            return {"dwell_time": 85, "scroll_speed": 3, "mouse_jitter": 0.25, "search_pattern": "직접검색"}

    # ── 네이버 쇼핑 순위 확인 ───────────────────────────────
    async def check_naver_ranking(self, keyword=None, product_id=None):
        def _check():
            kw = keyword or getattr(self, 'run_keyword', self.config['keyword'])
            store_name = self.config['store_name']
            print(f"🔍 '{kw}' 순위 추적 중...")
            url = f"https://m.search.naver.com/search.naver?query={quote(kw)}&where=m_shop"
            headers = {
                "User-Agent": "Mozilla/5.0 (Linux; Android 14; SM-S928N) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Mobile Safari/537.36",
                "Accept-Language": "ko-KR,ko;q=0.9"
            }
            try:
                res = requests.get(url, headers=headers, timeout=15)
                res.raise_for_status()
                text = res.text

                # 상품 ID로 먼저 찾기
                if product_id:
                    pid_str = str(product_id).strip()
                    import re
                    all_pids = []
                    seen = set()
                    def add(p):
                        if p and p not in seen:
                            seen.add(p)
                            all_pids.append(p)
                    # 1. smartstore URL matches (support both / and escaped \u002F)
                    for p in re.findall(r'smartstore\.naver\.com(?:/|\\u002F)[^\s"\'\\/]+(?:/|\\u002F)products(?:/|\\u002F)(\d+)', text):
                        add(p)
                    # 2. Generic /products/ or \u002Fproducts\u002F matches
                    for p in re.findall(r'(?:/|\\u002F)products(?:/|\\u002F)(\d+)', text):
                        add(p)
                    # 3. JSON channelProductId matches
                    for p in re.findall(r'["\']channelProductId["\']?\s*:\s*["\']?(\d+)["\']?', text):
                        add(p)
                    # 4. nv_mid / nvMid fallback
                    for p in re.findall(r'[?&]nv_mid=(\d+)', text):
                        add(p)
                    for p in re.findall(r'nvMid["\']?\s*:\s*["\']?(\d+)', text):
                        add(p)

                    if pid_str in all_pids:
                        rank = all_pids.index(pid_str) + 1
                        print(f"🚩 현재 순위: {rank}위 (ID {pid_str} 발견)")
                        return rank

                # 스토어명으로 fallback
                soup = BeautifulSoup(text, 'html.parser')
                items = soup.select(".lst_item") or soup.select("div[class*='product_item']")
                if not items:
                    print("⚠️ 쇼핑 리스트 파싱 실패")
                    return 999
                for idx, item in enumerate(items, 1):
                    if store_name in item.text:
                        print(f"🚩 현재 순위: {idx}위 (나눔랩 발견)")
                        return idx
                print("❌ 1페이지 내 미노출 (999위 처리)")
                return 999
            except Exception as e:
                print(f"❌ 접속 오류: {e}")
                return 999
        return await asyncio.to_thread(_check)

    # ── 히스토리 로깅 ────────────────────────────────────────
    def log_activity(self, start_rank, end_rank, dwell_time, status="성공"):
        new_data = {
            "날짜": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "키워드": getattr(self, 'run_keyword', self.config['keyword']),
            "시작순위": start_rank,
            "종료순위": end_rank,
            "체류시간": dwell_time,
            "결과": status,
            "모드": "집중" if self.focus['enabled'] else "분산"
        }
        try:
            df = pd.read_csv('permcoat_history.csv')
            df = pd.concat([df, pd.DataFrame([new_data])], ignore_index=True)
        except Exception:
            df = pd.DataFrame([new_data])
        df.to_csv('permcoat_history.csv', index=False, encoding='utf-8-sig')
        print("💾 히스토리 기록 완료")

    # ── 봇 탐지 ─────────────────────────────────────────────
    async def check_bot_detection(self, page):
        global SESSION_STATE
        for retry in range(3):
            try:
                await page.wait_for_load_state("load", timeout=5000)
                url = page.url.lower()
                content = await page.content()
                captcha_urls = ["captcha", "sorry/index", "nid.naver.com/login", "robot"]
                for ind in captcha_urls:
                    if ind in url:
                        print(f"🚨 [봇 감지] URL 패턴: {ind}")
                        SESSION_STATE['bot_detected_at'] = time.time()
                        SESSION_STATE['consecutive_fails'] += 1
                        return True
                text_indicators = [
                    "자동등록방지", "로봇이 아닙니다", "bot detection", "unusual traffic",
                    "비정상적인 접근", "보안절차를 거쳐", "접속이 불가합니다", "시스템오류"
                ]
                for ind in text_indicators:
                    if ind in content:
                        print(f"🚨 [봇 감지] 본문 키워드: '{ind}'")
                        SESSION_STATE['bot_detected_at'] = time.time()
                        SESSION_STATE['consecutive_fails'] += 1
                        return True
                return False
            except Exception as e:
                print(f"⚠️ 봇 탐지 검사 오류 ({retry+1}/3): {e}")
                await asyncio.sleep(1)
        print("🚨 봇 탐지 검사 연속 실패 — 차단 상태로 간주")
        SESSION_STATE['bot_detected_at'] = time.time()
        return True

    # ── 라마 일일 보고서 ─────────────────────────────────────
    async def get_llama_report(self):
        def _get_report():
            try:
                df = pd.read_csv('permcoat_history.csv').tail(10)
                if not OLLAMA_AVAILABLE:
                    print("\n📊 [오늘의 성과 요약]")
                    print(df[['날짜', '키워드', '시작순위', '종료순위', '결과']].to_string())
                    return
                prompt = f"""
                너는 나눔랩 마케팅 분석가야. 아래 데이터로 황영민 이사님께 드릴
                '오늘의 퍼마코트 엔진 성과 보고서'를 친절한 한국어로 작성해줘.
                데이터: {df.to_string()}
                포함 내용: 총 작업 횟수, 성공률, 순위 변동, 향후 전략 제언
                """
                response = ollama.chat(model='llama3', messages=[{'role': 'user', 'content': prompt}])
                print(f"\n💌 [Llama 일일 보고서]\n{response['message']['content']}\n")
            except Exception as e:
                print(f"⚠️ 보고서 생성 실패: {e}")
        await asyncio.to_thread(_get_report)

    # ── 시간대별 딜레이 계산 ─────────────────────────────────
    def calculate_current_delay(self):
        now = datetime.now()
        try:
            start_dt = datetime.strptime(self.config['start_date'], "%Y-%m-%d")
            days_passed = (now - start_dt).days
        except Exception:
            days_passed = 0
        daily_target = self.config['base_daily_hits'] * (self.config['growth_rate'] ** days_passed)
        hour_weight = (math.sin((now.hour - 8) * math.pi / 12) + 1.2) / 2
        hourly_target = (daily_target / 24) * hour_weight
        if hourly_target < 1:
            return int(daily_target), random.randint(1800, 3600)
        # 최소 15분(900초) 보장
        raw_delay = int(3600 / hourly_target)
        return int(daily_target), max(raw_delay, self.focus['min_session_gap_sec'])

    # ── IP 환경 리셋 (ADB) ──────────────────────────────────
    async def reset_env(self):
        print(f"🔄 [{datetime.now().strftime('%H:%M')}] IP/환경 재설정 시도...")
        try:
            proc1 = await asyncio.create_subprocess_exec(
                "adb", "shell", "settings", "put", "global", "airplane_mode_on", "1"
            )
            await proc1.wait()
            proc_b1 = await asyncio.create_subprocess_exec(
                "adb", "shell", "am", "broadcast", "-a", "android.intent.action.AIRPLANE_MODE", "--ez", "state", "true"
            )
            await proc_b1.wait()
            await asyncio.sleep(3)
            proc2 = await asyncio.create_subprocess_exec(
                "adb", "shell", "settings", "put", "global", "airplane_mode_on", "0"
            )
            await proc2.wait()
            proc_b2 = await asyncio.create_subprocess_exec(
                "adb", "shell", "am", "broadcast", "-a", "android.intent.action.AIRPLANE_MODE", "--ez", "state", "false"
            )
            await proc_b2.wait()
            print("⏳ 네트워크 안정화 대기 (15초)...")
            await asyncio.sleep(15)
            print("✅ IP 재설정 완료")
        except Exception as e:
            print(f"⚠️ ADB 없음/실패: {e} — IP 없이 계속 진행 (랜덤 딜레이 추가)")
            await asyncio.sleep(random.uniform(5, 15))

    # ── 보안 인터셉터 ────────────────────────────────────────
    async def interceptor(self, route):
        url = route.request.url
        if any(x in url for x in ["sensor.js", "wlog", "analytics", "tracking"]):
            try:
                response = await route.fetch()
                ct = response.headers.get("content-type", "")
                if "text" in ct or "json" in ct or "javascript" in ct:
                    body = await response.text()
                    modified = body.replace("navigator.webdriver", "undefined").replace("isBot=true", "isBot=false")
                    await route.fulfill(response=response, body=modified)
                else:
                    await route.fulfill(response=response)
            except Exception:
                await route.continue_()
        else:
            await route.continue_()

    # ── 인간 행동 모사 ───────────────────────────────────────
    async def human_action(self, page, strategy=None):
        if strategy is None:
            strategy = {"scroll_speed": 3, "mouse_jitter": 0.25}
        base_sleep = 15.0 / max(strategy.get('scroll_speed', 3), 1)
        jitter_prob = strategy.get('mouse_jitter', 0.25)
        scroll_count = random.randint(5, 10)
        for i in range(scroll_count):
            delta = random.randint(300, 800)
            await page.mouse.wheel(0, delta)
            await asyncio.sleep(random.uniform(base_sleep * 0.4, base_sleep * 1.6))
            # 랜덤 마우스 이동
            if random.random() < jitter_prob:
                await page.mouse.move(
                    random.randint(50, 350),
                    random.randint(100, 650)
                )
            # 중간에 잠깐 멈추는 자연스러운 행동
            if i == scroll_count // 2:
                await asyncio.sleep(random.uniform(2.0, 5.0))

    # ── 핵심: 1회 트래픽 세션 실행 ──────────────────────────
    async def run_task(self):
        global SESSION_STATE
        self.load_dynamic_config()

        keyword, target_product, product_id = self.pick_keyword_and_product()

        # 순위 체크
        start_rank = await self.check_naver_ranking(keyword=keyword, product_id=product_id)

        # IP 환경 리셋 (ADB)
        await self.reset_env()

        async with async_playwright() as p:
            # 브라우저 설정
            chosen_ua = random.choice(USER_AGENTS)
            is_mobile = "iPhone" in chosen_ua or "Android" in chosen_ua

            browser = await p.chromium.launch(
                headless=False,
                args=[
                    '--disable-blink-features=AutomationControlled',
                    '--no-first-run',
                    '--disable-infobars',
                ]
            )

            context = await browser.new_context(
                viewport={
                    'width': random.choice([375, 390, 412]) if is_mobile else random.randint(1366, 1920),
                    'height': random.choice([812, 844, 915]) if is_mobile else random.randint(768, 1080)
                },
                user_agent=chosen_ua,
                is_mobile=is_mobile,
                locale='ko-KR',
                timezone_id='Asia/Seoul',
                geolocation={'latitude': 37.5665 + random.uniform(-0.05, 0.05),
                             'longitude': 126.9780 + random.uniform(-0.05, 0.05)},
                permissions=['geolocation'],
            )

            page = await context.new_page()

            # 핑거프린팅 방지 스크립트 주입
            await page.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
                Object.defineProperty(navigator, 'plugins', {get: () => [1,2,3,4,5]});
                Object.defineProperty(navigator, 'languages', {get: () => ['ko-KR','ko','en-US','en']});
                const getParameter = WebGLRenderingContext.prototype.getParameter;
                WebGLRenderingContext.prototype.getParameter = function(parameter) {
                    if (parameter === 37445) return 'Intel Inc.';
                    if (parameter === 37446) return 'Intel(R) Iris(TM) Plus Graphics';
                    return getParameter.apply(this, arguments);
                };
                window.chrome = {runtime: {}};
            """)

            await Stealth().apply_stealth_async(page)
            await page.route("**/*", self.interceptor)

            try:
                # 전략 수립
                try:
                    df = pd.read_csv('permcoat_history.csv').tail(3)
                    db_log = df.to_string()
                except Exception:
                    db_log = "이전 데이터 없음"
                current_log = f"오늘 성공: {self.daily_hits_count}건, 실패: {self.fail_hits_count}건\n최근 로그:\n{db_log}"
                strategy = await self.ask_llama_strategy(current_log)

                print("\n" + "=" * 55)
                print(f"[{datetime.now().strftime('%H:%M:%S')}] 🎬 트래픽 세션 시작")
                print(f"🎯 키워드: {keyword} | 상품: {product_id}")
                print("=" * 55)

                # ── 유입 경로 결정: 네이버 80% / 구글 20% ──
                path = random.random()

                if path < 0.80:
                    # ── 네이버 모바일 검색 경유 ──
                    print(f"➡️ [네이버 경유] 검색어: {keyword}")
                    await page.goto("https://m.naver.com", wait_until="domcontentloaded")
                    await asyncio.sleep(random.uniform(1.5, 3.0))

                    if await self.check_bot_detection(page):
                        print("🚨 네이버 진입 봇 감지 — 세션 중단")
                        await browser.close()
                        return

                    # 검색창 클릭 및 타이핑
                    try:
                        search_fake = page.locator("#MM_SEARCH_FAKE")
                        if await search_fake.is_visible(timeout=2000):
                            await search_fake.click()
                            await asyncio.sleep(random.uniform(0.5, 1.2))
                    except Exception:
                        pass

                    search_input = page.locator('#query')
                    try:
                        await search_input.focus(timeout=3000)
                    except Exception:
                        try:
                            await search_input.click(force=True, timeout=2000)
                        except Exception:
                            await page.evaluate("document.getElementById('query') && document.getElementById('query').focus()")

                    # 사람처럼 타이핑
                    jitter = strategy.get('mouse_jitter', 0.25)
                    for char in keyword:
                        await page.keyboard.type(char)
                        await asyncio.sleep(random.uniform(jitter * 0.4, jitter * 1.8))

                    # 가끔 오타 후 수정 (인간 행동 모사)
                    if random.random() < 0.15:
                        await page.keyboard.type("ㅁ")
                        await asyncio.sleep(random.uniform(0.3, 0.7))
                        await page.keyboard.press("Backspace")
                        await asyncio.sleep(random.uniform(0.2, 0.5))

                    await search_input.press("Enter")
                    await asyncio.sleep(2.0)

                    if await self.check_bot_detection(page):
                        print("🚨 검색 결과 봇 감지 — 세션 중단")
                        await browser.close()
                        return

                    # 블로그 경유 진입
                    await asyncio.sleep(random.uniform(1.0, 2.0))
                    target_blog = random.choice(self.config['blogs']).rstrip('/')
                    post_id = target_blog.split('/')[-1]
                    print(f"🔍 블로그({post_id}) 검색 결과 탐색 중...")

                    found_post = page.locator(f'a[href*="{post_id}"]')
                    if await found_post.count() > 0:
                        print("✅ 검색 결과에서 블로그 발견 — 딥 링크 진입")
                        href = await found_post.first.get_attribute("href")
                        await page.goto(href if href else target_blog)
                    else:
                        print("⚠️ 블로그 검색 결과 미발견 — 직접 진입")
                        mobile_blog = target_blog.replace("blog.naver.com", "m.blog.naver.com")
                        await page.goto(mobile_blog)

                else:
                    # ── 구글 검색 경유 (20%) ──
                    print(f"➡️ [구글 경유] 검색어: {keyword}")
                    await page.goto("https://www.google.co.kr", wait_until="domcontentloaded")
                    await asyncio.sleep(random.uniform(1.5, 2.5))

                    search_box = page.locator('textarea[name="q"], input[name="q"]').first
                    try:
                        await search_box.focus(timeout=3000)
                    except Exception:
                        try:
                            await search_box.click(force=True, timeout=2000)
                        except Exception:
                            pass

                    jitter = strategy.get('mouse_jitter', 0.25)
                    for char in keyword:
                        await page.keyboard.type(char)
                        await asyncio.sleep(random.uniform(jitter * 0.4, jitter * 1.8))

                    await search_box.press("Enter")
                    await asyncio.sleep(2.0)

                    if await self.check_bot_detection(page):
                        print("🚨 구글 검색 봇 감지 — 네이버로 전환 후 대기")
                        await browser.close()
                        return

                    target_blog = random.choice(self.config['blogs']).rstrip('/')
                    post_id = target_blog.split('/')[-1]
                    found_post = page.locator(f'a[href*="{post_id}"]')
                    if await found_post.count() > 0:
                        href = await found_post.first.get_attribute("href")
                        await page.goto(href if href else target_blog)
                    else:
                        mobile_blog = target_blog.replace("blog.naver.com", "m.blog.naver.com")
                        await page.goto(mobile_blog)

                if await self.check_bot_detection(page):
                    print("🚨 블로그 페이지 봇 감지 — 세션 중단")
                    await browser.close()
                    return

                # ── 블로그 정독 (신뢰 점수 적립) ──
                print("⏳ 블로그 콘텐츠 정독 중... (신뢰도 확보)")
                await self.human_action(page, strategy)
                await asyncio.sleep(random.uniform(3.0, 8.0))

                # ── 상품 상세 페이지로 이동 ──
                print(f"➡️ [최종 진입] 상품 페이지({product_id})로 이동")
                await page.evaluate(f"window.location.href = '{target_product}'")
                try:
                    await page.wait_for_load_state("networkidle", timeout=12000)
                except Exception:
                    pass

                await asyncio.sleep(5)

                if await self.check_bot_detection(page):
                    print("🚨 상품 페이지 봇 감지 — 세션 중단")
                    await browser.close()
                    return

                # ── 상품 페이지 체류 ──
                print(f"🎯 상품 페이지 체류 중...")
                await self.human_action(page, strategy)
                await page.mouse.wheel(0, random.randint(-300, 300))

                dwell_time = strategy.get('dwell_time', 85)
                print(f"⏱️ 체류 시간: {dwell_time}초")
                await asyncio.sleep(dwell_time)

                print("✨ [완료] 트래픽 1회 성공!")

                # 세션 상태 업데이트
                SESSION_STATE['last_session_time'] = time.time()
                SESSION_STATE['sessions_this_hour'] += 1
                SESSION_STATE['consecutive_fails'] = 0

                end_rank = await self.check_naver_ranking(keyword=keyword, product_id=product_id)
                self.log_activity(start_rank, end_rank, dwell_time, "성공")

            except Exception as e:
                self.fail_hits_count += 1
                SESSION_STATE['consecutive_fails'] += 1
                print(f"❌ 세션 오류: {e}")
                self.log_activity(start_rank, start_rank, 0, "실패")

                # 연속 실패 3회 이상 시 긴 대기
                if SESSION_STATE['consecutive_fails'] >= 3:
                    print(f"⚠️ 연속 {SESSION_STATE['consecutive_fails']}회 실패 — 30분 추가 대기")
                    await asyncio.sleep(30 * 60)
            finally:
                print("🔒 브라우저 완전 종료 (흔적 삭제)")
                await browser.close()

    # ── 24시간 메인 루프 ─────────────────────────────────────
    async def start_engine(self):
        global SESSION_STATE
        total_w = _WEIGHT_TOTAL
        print("\n" + "#" * 60)
        print("🚀 나눔랩 전 상품 순위 상승 엔진 가동 (다상품 분산 모드)")
        print(f"   - 대상 상품: {len(PRODUCT_TRAFFIC_MAP)}개")
        for p in PRODUCT_TRAFFIC_MAP:
            pct = round(p['weight'] / total_w * 100)
            print(f"     [{pct:2d}%] {p['name']}")
        print(f"   - 세션 간격: 최소 {self.focus['min_session_gap_sec']//60}분")
        print(f"   - 시간당 최대: {self.focus['max_sessions_per_hour']}회")
        print(f"   - 봇 감지 쿨다운: {self.focus['danger_cooldown_sec']//60}분")
        print(f"   - 타겟 스토어: {self.config['store_name']}")
        print("#" * 60 + "\n")

        while True:
            today_str = datetime.now().strftime("%Y-%m-%d")
            if self.current_date_str != today_str:
                await self.get_llama_report()
                self.current_date_str = today_str
                self.daily_hits_count = 0
                self.fail_hits_count = 0
                SESSION_STATE['focus_count_today'] = 0
                print(f"🌅 새 날짜({today_str}) — 카운터 초기화")

            daily_target, next_delay = self.calculate_current_delay()
            print(f"\n📊 [현황] 오늘 {self.daily_hits_count}/{daily_target}회 | 총 세션 {SESSION_STATE['focus_count_today']}회")

            extra_wait = self.safety_check_delay()
            if extra_wait > 0:
                await asyncio.sleep(extra_wait)
                continue

            try:
                await asyncio.wait_for(self.run_task(), timeout=360)
            except (asyncio.TimeoutError, TimeoutError):
                print("⏰ 타임아웃 (6분 초과) — 강제 종료")
                self.fail_hits_count += 1
            except Exception as e:
                print(f"❌ 엔진 오류: {e}")
                self.fail_hits_count += 1

            self.daily_hits_count += 1

            final_delay = int(next_delay * random.uniform(0.85, 1.15))
            wait_m, wait_s = divmod(final_delay, 60)
            print(f"😴 다음 세션까지 {wait_m}분 {wait_s}초 대기...")
            print("💡 (화면이 꺼진 것은 정상입니다 — 다음 타임을 기다리는 중)")
            print("-" * 55)
            await asyncio.sleep(final_delay)


# ── 단일 테스트 실행 ──────────────────────────────────────────
async def run_once_test():
    """1회 테스트 실행 (가중치 기반 상품 자동 선택)"""
    print("🧪 [테스트 모드] 1회 세션 실행 중...")
    print(f"📊 상품별 트래픽 배분:")
    for p in PRODUCT_TRAFFIC_MAP:
        pct = round(p['weight'] / _WEIGHT_TOTAL * 100)
        print(f"   [{pct:2d}%] {p['name']}")
    print()
    engine = PermacoatAutonomousEngine()
    await engine.run_task()
    print("🧪 [테스트 모드] 완료!")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="나눔랩 자동차코팅제 순위 상승 엔진")
    parser.add_argument('--test', action='store_true', help='1회 테스트 실행')
    parser.add_argument('--engine', action='store_true', help='24시간 연속 엔진 실행')
    args = parser.parse_args()

    if args.test:
        asyncio.run(run_once_test())
    elif args.engine:
        engine = PermacoatAutonomousEngine()
        asyncio.run(engine.start_engine())
    else:
        # 기본: 1회 테스트
        print("사용법: python traffic_single.py --test (1회) | --engine (연속)")
        print("기본값으로 1회 테스트 실행합니다.\n")
        asyncio.run(run_once_test())