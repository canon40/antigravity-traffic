import asyncio
import csv
import datetime
import os
import random
import sys
from urllib.parse import quote
from playwright.async_api import async_playwright

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)
        sys.stderr.reconfigure(encoding="utf-8", line_buffering=True)
    except Exception:
        pass


# 1. 모니터링 대상 키워드 및 자사 상품 정보 설정
KEYWORDS = ['리빙코팅제', '발수코팅제', '자동차코팅제', '코팅제', '바이크코팅제', '오토바이코팅제']
TARGET_PRODUCTS = {
    "12148236431": "나눔랩 상품 12148",
    "12846398455": "나눔랩 상품 12846",
    "12606417663": "듀라코트 리빙코트",
    "12809532969": "나눔랩 코팅제 C",
    "12634187514": "나눔랩 코팅 상품",
    "12809541448": "나눔랩 코팅제 D",
    "12635263697": "퍼마코트 코팅제",
    "12808787263": "나눔랩 세정·관리제",
    "12639296730": "퍼마코트 자동차 코팅제",
    "12808836901": "나눔랩 바이크 코팅제"
}

# 2. 결과 저장 경로 설정 (안전한 폴더명 사용)
CSV_FILE_PATH = r"d:\@code\monitor\rank_analysis_log.csv"

def init_csv():
    """CSV 파일 초기화 및 헤더 생성"""
    os.makedirs(os.path.dirname(CSV_FILE_PATH), exist_ok=True)
    if not os.path.exists(CSV_FILE_PATH):
        with open(CSV_FILE_PATH, mode='w', encoding='utf-8-sig', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(['기록시간', '키워드', '상품ID', '상품명', '순위', '결과'])

def log_to_csv(keyword, product_id, product_name, rank, status):
    """결과를 CSV 파일에 한 줄씩 누적 저장"""
    current_time = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    with open(CSV_FILE_PATH, mode='a', encoding='utf-8-sig', newline='') as f:
        writer = csv.writer(f)
        writer.writerow([current_time, keyword, product_id, product_name, rank, status])

async def monitor_keyword(page, keyword):
    """특정 키워드로 검색 후 자사 상품의 노출 순위 분석"""
    print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] '{keyword}' 검색 분석 시작...")
    
    # [수정] 네이버 모바일 쇼핑 검색 URL 주소 최적화 (msearch.shopping.naver.com의 봇 탐지 우회)
    encoded_keyword = quote(keyword)
    search_url = f"https://m.search.naver.com/search.naver?query={encoded_keyword}&where=m_shop"
    
    try:
        await page.goto(search_url, wait_until="domcontentloaded", timeout=30000)
        # 동적 로딩을 위해 하단으로 약간 스크롤
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight / 2)")
        await asyncio.sleep(1.5)
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        await asyncio.sleep(1.5)
        
        # 페이지 내 모든 상품 ID 순서대로 추출
        pids = await page.evaluate("""() => {
            const links = Array.from(document.querySelectorAll('a'));
            const seen = new Set();
            const ordered = [];
            links.forEach(a => {
                const href = a.href || '';
                try {
                    const decodedUrl = decodeURIComponent(href);
                    const match = decodedUrl.match(/\/products\/(\d+)/);
                    if (match) {
                        const pid = match[1];
                        if (!seen.has(pid)) {
                            seen.add(pid);
                            ordered.push(pid);
                        }
                    }
                } catch(e) {}
            });
            return ordered;
        }""")
        
        found_products = set()
        
        # 발견된 상품 ID 매칭 및 순위 산출
        for pid in pids:
            if pid in TARGET_PRODUCTS and pid not in found_products:
                rank = pids.index(pid) + 1
                pname = TARGET_PRODUCTS[pid]
                print(f"   -> [발견] {pname} ({pid}) - {rank}위 노출 중")
                log_to_csv(keyword, pid, pname, rank, "1페이지 내 확인")
                found_products.add(pid)
                
        # 1페이지 내에서 발견되지 않은 나머지 자사 상품들 처리
        for pid, pname in TARGET_PRODUCTS.items():
            if pid not in found_products:
                log_to_csv(keyword, pid, pname, "-", "100위 밖 (미검색)")
                
    except Exception as e:
        print(f"   [오류] '{keyword}' 분석 중 오류 발생: {e}")
        for pid, pname in TARGET_PRODUCTS.items():
            log_to_csv(keyword, pid, pname, "에러", f"요청 실패 ({str(e)[:20]})")

async def run_monitoring():
    """모니터링 전체 프로세스 1회 실행"""
    init_csv()
    
    async with async_playwright() as p:
        # 모바일 환경 에뮬레이션 (Pixel 5 기준)
        device = p.devices['Pixel 5']
        print("[브라우저] 모바일 에뮬레이터 브라우저 실행...")
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(**device)
        page = await context.new_page()
        
        # 각 키워드 순회 분석
        for idx, keyword in enumerate(KEYWORDS):
            await monitor_keyword(page, keyword)
            
            # 마지막 키워드가 아니라면 안전을 위해 10~20초 사이 임의 지연 적용
            if idx < len(KEYWORDS) - 1:
                delay = random.uniform(10, 20)
                print(f"   [대기] 다음 분석까지 {delay:.1f}초 대기 중...")
                await asyncio.sleep(delay)
                
        await browser.close()

async def main():
    init_csv()
    
    # 1시간(3600초) 간격으로 밤새 무한 반복 실행
    while True:
        print("\n" + "="*40)
        print(f" 현재 시간: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(" 정기 노출 현황 모니터링을 시작합니다. ")
        print("=========================================")
        
        await run_monitoring()
        
        print("=========================================")
        print(" 이번 회차 모니터링 완료. 1시간 동안 대기합니다. ")
        print("=========================================")
        
        # 3600초(1시간) 대기 후 다시 처음부터 시작
        await asyncio.sleep(3600)

if __name__ == "__main__":
    asyncio.run(main())
