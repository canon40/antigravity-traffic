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


KEYWORDS = ['리빙코팅제', '발수코팅제', '자동차코팅제', '코팅제', '바이크코팅제', '오토바이코팅제']
TARGET_PRODUCTS = {
    "12148236431": "나눔랩 상품 1",
    "12846398455": "나눔랩 상품 2",
    "12606417663": "듀라코트 리빙코트",
    "12809532969": "나눔랩 상품 3",
    "12634187514": "나눔랩 상품 4",
    "12809541448": "나눔랩 상품 5",
    "12635263697": "퍼마코트 코팅제",
    "12808787263": "나눔랩 상품 6",
    "12639296730": "퍼마코트 자동차 코팅제",
    "12808836901": "나눔랩 바이크 코팅제"
}

CSV_FILE_PATH = r"d:\@code\monitor\rank_analysis_log.csv"

async def check_rank(page, keyword):
    """
    네이버 모바일 쇼핑 페이지에서 키워드 검색 후 상품 ID 순서를 추출합니다.
    """
    search_url = f"https://m.search.naver.com/search.naver?query={quote(keyword)}&where=m_shop"
    print(f"[{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] '{keyword}' 검색 중...")
    
    try:
        # 페이지 이동 및 DOM 로드 대기
        await page.goto(search_url, wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(2000)
        
        # 동적 스크롤링을 수행하여 더 많은 노출 순위를 로딩합니다.
        for _ in range(3):
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await page.wait_for_timeout(1500)
            
        # 페이지 소스 내에서 상품 링크를 추출하여 고유한 상품 ID 순서 목록을 생성합니다.
        pids = await page.evaluate("""() => {
            const links = Array.from(document.querySelectorAll('a[href*="/products/"]'));
            const seen = new Set();
            const ordered = [];
            links.forEach(a => {
                const href = a.href;
                const match = href.match(/\/products\/(\d+)/);
                if (match) {
                    const pid = match[1];
                    if (!seen.has(pid)) {
                        seen.add(pid);
                        ordered.push(pid);
                    }
                }
            });
            return ordered;
        }""")
        
        return pids
    except Exception as e:
        print(f"❌ '{keyword}' 파싱 중 오류 발생: {e}")
        return []

async def main():
    # 저장 폴더가 존재하지 않으면 생성
    os.makedirs(os.path.dirname(CSV_FILE_PATH), exist_ok=True)
    
    async with async_playwright() as p:
        # 모바일 환경 에뮬레이션 (Pixel 5)
        device = p.devices['Pixel 5']
        print("🤖 모바일 브라우저 실행 중...")
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(**device)
        page = await context.new_page()
        
        results_to_save = []
        now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        for idx, keyword in enumerate(KEYWORDS):
            pids = await check_rank(page, keyword)
            
            # 검색 리스트에서 타겟 상품들의 인덱스 찾기 (1-based index)
            for product_id, product_name in TARGET_PRODUCTS.items():
                rank = -1
                if product_id in pids:
                    rank = pids.index(product_id) + 1
                    print(f"  🎯 발견: {product_name} ({product_id}) -> {rank}위")
                else:
                    print(f"  ✕ 미발견: {product_name} ({product_id}) -> 1페이지 내 없음")
                
                results_to_save.append([now_str, keyword, product_id, product_name, rank if rank != -1 else "100위 밖"])
            
            # 마지막 키워드가 아닌 경우, 10~20초 사이의 임의 지연 적용
            if idx < len(KEYWORDS) - 1:
                delay = random.uniform(10.0, 20.0)
                print(f"⏳ 서버 부하 경감을 위해 {delay:.2f}초 동안 대기합니다...\n")
                await asyncio.sleep(delay)
                
        # CSV 누적 기록
        file_exists = os.path.exists(CSV_FILE_PATH)
        with open(CSV_FILE_PATH, mode='a', encoding='utf-8-sig', newline='') as f:
            writer = csv.writer(f)
            if not file_exists:
                writer.writerow(['Date', 'Keyword', 'Product ID', 'Product Name', 'Rank'])
            writer.writerows(results_to_save)
            
        print(f"\n💾 순위 기록 완료: {CSV_FILE_PATH}")
        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
