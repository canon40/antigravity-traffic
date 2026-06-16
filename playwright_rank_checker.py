import asyncio
import datetime
import os
import random
from playwright.async_api import async_playwright

# 검색 순위 모니터링 설정
KEYWORDS = ["퍼마코트 자동차 코팅제", "유리막 코팅제", "듀라코트 리빙코트"]
TARGET_PRODUCT_ID = "12639296730"  # 순위를 조회할 대상 상품 ID
TARGET_STORE_NAME = "나눔랩"       # 순위를 조회할 대상 스토어명
OUTPUT_LOG_FILE = "rank_monitoring.log"

async def check_rank_with_playwright(page, keyword, product_id, store_name):
    """
    Playwright를 사용하여 모바일 검색 결과 페이지에서 상품의 순위를 파싱합니다.
    """
    # 쇼핑 검색 URL 생성 (모바일 버전 검색 페이지)
    search_url = f"https://m.search.naver.com/search.naver?query={keyword}&where=m_shop"
    
    print(f"[{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] '{keyword}' 순위 검색 중...")
    
    try:
        # 검색 페이지 이동
        await page.goto(search_url, wait_until="domcontentloaded", timeout=30000)
        
        # 페이지 내 동적 요소가 렌더링될 수 있도록 잠시 대기
        await page.wait_for_timeout(2000)
        
        # 쇼핑 상품 컨테이너 목록 추출
        #lst_item(구형 테마) 혹은 product_item 등을 포함하는 셀렉터 매칭
        product_elements = await page.locator("div[class*='product_item'], li.lst_item, div.lst_item").all()
        
        if not product_elements:
            # 셀렉터 미매칭 시 전체 a 태그의 href 경로 분석법 적용 (백업용)
            hrefs = await page.evaluate("""() => {
                return Array.from(document.querySelectorAll('a')).map(a => a.href);
            }""")
            
            rank = 1
            seen_pids = set()
            for href in hrefs:
                if "/products/" in href:
                    # URL에서 상품 ID 파싱
                    parts = href.split("/products/")
                    if len(parts) > 1:
                        pid = parts[1].split("?")[0].split("/")[0]
                        if pid not in seen_pids:
                            seen_pids.add(pid)
                            if pid == product_id:
                                return rank
                            rank += 1
            return -1  # 검색 결과 내 없음
        
        # 상품 리스트 요소를 순회하며 순위 판별
        rank = 1
        for element in product_elements:
            html_content = await element.inner_html()
            text_content = await element.inner_text()
            
            # 상품 ID 또는 스토어명으로 매칭 여부 체크
            if product_id in html_content or store_name in text_content:
                return rank
            rank += 1
            
        return -1  # 1페이지 내에 없음
        
    except Exception as e:
        print(f"❌ 순위 파싱 중 오류 발생: {e}")
        return -2  # 에러 발생

async def run_monitoring():
    async with async_playwright() as p:
        # 모바일 브라우저 환경 에뮬레이션 (Pixel 5 기준)
        device = p.devices['Pixel 5']
        
        print("🤖 모바일 에뮬레이터 브라우저 기동...")
        browser = await p.chromium.launch(headless=True)  # 백그라운드 모드로 동작
        context = await browser.new_context(**device)
        page = await context.new_page()
        
        for kw in KEYWORDS:
            rank = await check_rank_with_playwright(page, kw, TARGET_PRODUCT_ID, TARGET_STORE_NAME)
            timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            # 결과 가공 및 로깅
            if rank > 0:
                log_message = f"[{timestamp}] 키워드: '{kw}' | 상태: 성공 | 순위: {rank}위"
            elif rank == -1:
                log_message = f"[{timestamp}] 키워드: '{kw}' | 상태: 미검색 | 순위: 1페이지 내 없음 (100위 밖)"
            else:
                log_message = f"[{timestamp}] 키워드: '{kw}' | 상태: 실패 (네트워크/구조 변경 에러)"
                
            print(log_message)
            
            # 로그 파일 기록
            with open(OUTPUT_LOG_FILE, "a", encoding="utf-8") as f:
                f.write(log_message + "\n")
                
            # 정기 조회 간격 조율 및 서버 부하 경감을 위한 임의의 딜레이
            sleep_time = random.uniform(3.0, 7.0)
            print(f"⏳ 다음 키워드 검색 전 {sleep_time:.1f}초 동안 대기합니다...")
            await asyncio.sleep(sleep_time)
            
        await browser.close()
        print("🏁 모니터링 작업 완료.")

if __name__ == "__main__":
    asyncio.run(run_monitoring())
