import csv
import json
import os
import re
from datetime import datetime
from urllib.parse import quote

import requests

from app_resources import get_storage_dir

HISTORY_HEADERS = ["날짜", "키워드", "스토어명", "순위", "이전순위", "변동", "작업유형", "상세"]

_BUNDLE_DIR = os.path.dirname(os.path.abspath(__file__))
_DEFAULT_CONFIG_PATH = os.path.join(_BUNDLE_DIR, "config.defaults.json")

# Android Chrome UA — 모바일 앱·실기기에서 네이버 응답 안정화
MOBILE_UA = (
    "Mozilla/5.0 (Linux; Android 14; SM-S918N) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0.0.0 Mobile Safari/537.36"
)


def _config_path():
    return os.path.join(get_storage_dir(), "config.json")


def _history_path():
    return os.path.join(get_storage_dir(), "rank_history.csv")


def _shopping_search_url(keyword, start=1):
    """네이버 모바일 쇼핑 검색 URL. start: 결과 시작 번호 (1, 41, 81, ...)"""
    return (
        f"https://m.search.naver.com/search.naver?"
        f"query={quote(keyword.strip())}&where=m_shop&start={start}"
    )


def _extract_ordered_product_ids(html):
    """스마트스토어 상품 ID 우선, 중복 제거 순서 유지."""
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



def test_naver_connection():
    """네이버 모바일 검색 연결 테스트."""
    try:
        res = requests.get(
            _shopping_search_url("퍼마코트"),
            headers={"User-Agent": MOBILE_UA, "Accept-Language": "ko-KR,ko;q=0.9"},
            timeout=20,
        )
        if res.status_code != 200:
            return False, f"HTTP {res.status_code}"
        ids = _extract_ordered_product_ids(res.text)
        if not ids:
            return False, "검색 페이지는 열렸으나 상품 목록을 파싱하지 못했습니다."
        return True, f"연결 정상 (샘플 상품 {len(ids)}건 인식)"
    except Exception as e:
        return False, str(e)


def load_config():
    path = _config_path()
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    if os.path.exists(_DEFAULT_CONFIG_PATH):
        with open(_DEFAULT_CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {
        "store_name": "나눔랩",
        "track_interval_minutes": 60,
        "priority_track_limit": 10,
        "keywords": [],
        "product_urls": [],
        "blog_urls": [],
    }


def save_config(config):
    with open(_config_path(), "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)


def ensure_history_file():
    path = _history_path()
    if os.path.exists(path):
        return
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(HISTORY_HEADERS)


def get_history(limit=None):
    ensure_history_file()
    rows = []
    try:
        with open(_history_path(), "r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for row in reader:
                rows.append(row)
    except Exception:
        pass
    if limit:
        return rows[-limit:]
    return rows


def get_last_rank(keyword, store_name):
    for row in reversed(get_history()):
        if row.get("키워드") == keyword and row.get("스토어명") == store_name:
            try:
                return int(row.get("순위", 100))
            except (TypeError, ValueError):
                return 100
    return None


def append_history(keyword, store_name, rank, prev_rank, task_type, detail):
    ensure_history_file()
    if prev_rank is None:
        change = "-"
    elif rank < prev_rank:
        change = f"+{prev_rank - rank}"
    elif rank > prev_rank:
        change = f"-{rank - prev_rank}"
    else:
        change = "0"

    with open(_history_path(), "a", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([
            datetime.now().strftime("%Y-%m-%d %H:%M"),
            keyword,
            store_name,
            rank,
            prev_rank if prev_rank is not None else "-",
            change,
            task_type,
            detail,
        ])


def get_all_product_rankings(keyword, product_map, logger=None, max_pages=13):
    """
    여러 페이지를 순회하며 product_map에 등록된 모든 상품의 노출 순위를 반환.
    product_map: { "상품ID": "상품명", ... }
    max_pages: 탐색할 최대 페이지 수 (기본 13 ≒ 520위)
    """
    import time

    def log(msg):
        if logger:
            logger(msg)

    keyword = keyword.strip()
    if not keyword:
        return [], "키워드를 입력하세요."
    if not product_map:
        return [], "등록 상품 DB가 비어 있습니다. 앱을 재설치하거나 products.json을 확인하세요."

    headers = {
        "User-Agent": MOBILE_UA,
        "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.8",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }

    remaining = set(product_map.keys())  # 아직 못 찾은 상품
    results = []
    cumulative_rank = 0

    try:
        for page in range(1, max_pages + 1):
            if not remaining:
                break  # 모든 상품 발견

            start = (page - 1) * 40 + 1
            url = _shopping_search_url(keyword, start=start)
            log(f"   📄 {page}페이지 조회 중... (start={start}, 미발견 상품 {len(remaining)}건)")

            try:
                res = requests.get(url, headers=headers, timeout=20)
                if res.status_code != 200:
                    log(f"   ⚠️ HTTP {res.status_code} — 중단")
                    break
            except requests.exceptions.Timeout:
                log(f"   ⚠️ {page}페이지 타임아웃 — 중단")
                break
            except requests.exceptions.ConnectionError:
                log(f"   ⚠️ {page}페이지 연결 실패 — 중단")
                break

            page_ids = _extract_ordered_product_ids(res.text)
            if not page_ids:
                log(f"   ⚠️ {page}페이지에서 상품 미발견 — 탐색 종료")
                break

            for pid in page_ids:
                cumulative_rank += 1
                if pid in remaining:
                    remaining.discard(pid)
                    results.append({
                        "id": pid,
                        "name": product_map[pid],
                        "rank": cumulative_rank,
                        "page": (cumulative_rank - 1) // 40 + 1,
                        "rank_in_page": ((cumulative_rank - 1) % 40) + 1,
                        "display": (
                            f"{cumulative_rank}위 "
                            f"({(cumulative_rank - 1) // 40 + 1}페이지 "
                            f"{((cumulative_rank - 1) % 40) + 1}번째)"
                        ),
                    })
                    append_history(
                        keyword,
                        product_map[pid],
                        cumulative_rank,
                        get_last_rank(keyword, product_map[pid]),
                        "순위진단",
                        f"{product_map[pid]} {cumulative_rank}위",
                    )
                    log(f"   ✅ {product_map[pid]}: {cumulative_rank}위")

            if page < max_pages and remaining:
                time.sleep(0.5)  # 네이버 요청 간격 준수

        # 탐색 범위 내 미발견 상품 처리
        for pid in remaining:
            log(f"   ❌ {product_map[pid]}: {cumulative_rank}위 이후 미발견")

        log(f"✅ '{keyword}' — 나눔랩 상품 {len(results)}건 매칭 (총 {cumulative_rank}위까지 탐색)")
        return results, None
    except Exception as e:
        return results, str(e)


def check_product_rank(keyword, product_id, logger=None, max_pages=13):
    """
    특정 스마트스토어 상품 ID의 쇼핑 검색 노출 순위.
    max_pages: 탐색할 최대 페이지 수 (1페이지=40개, 기본 13페이지 ≒ 520위까지)
    반환값: 실제 순위(int) 또는 None(조회 실패)
    찾지 못하면 max_pages*40 초과를 의미하는 큰 값 대신 None 반환.
    """
    def log(msg):
        if logger:
            logger(msg)

    product_id = str(product_id).strip()
    log(f"🔍 '{keyword}' 검색 결과에서 상품 {product_id} 순위 조회 (최대 {max_pages}페이지)...")
    headers = {
        "User-Agent": MOBILE_UA,
        "Accept-Language": "ko-KR,ko;q=0.9",
    }

    cumulative_rank = 0  # 지금까지 세어온 상품 수

    try:
        for page in range(1, max_pages + 1):
            start = (page - 1) * 40 + 1
            url = _shopping_search_url(keyword, start=start)
            log(f"   📄 {page}페이지 조회 중... (start={start})")

            res = requests.get(url, headers=headers, timeout=20)
            if res.status_code != 200:
                log(f"   ⚠️ HTTP {res.status_code} — 중단")
                break

            page_ids = _extract_ordered_product_ids(res.text)
            if not page_ids:
                log(f"   ⚠️ {page}페이지에서 상품 미발견 — 탐색 종료")
                break

            for pid in page_ids:
                cumulative_rank += 1
                if pid == product_id:
                    log(f"✅ 상품 {product_id}: {cumulative_rank}위 ({page}페이지)")
                    return cumulative_rank

            import time
            time.sleep(0.5)  # 네이버 요청 간격 준수

        log(f"⚠️ 상품 {product_id} {cumulative_rank}위 이후에도 미발견")
        return None  # 탐색 범위 초과 — 순위 없음
    except Exception as e:
        log(f"❌ 상품 순위 조회 실패: {e}")
        return None


def check_naver_shopping_rank(keyword, store_name, logger=None):
    def log(msg):
        if logger:
            logger(msg)

    log(f"🔍 '{keyword}' 키워드로 '{store_name}' 순위 조회 중...")
    headers = {
        "User-Agent": MOBILE_UA,
        "Accept-Language": "ko-KR,ko;q=0.9",
    }

    try:
        res = requests.get(_shopping_search_url(keyword), headers=headers, timeout=20)
        res.raise_for_status()
        text = res.text

        try:
            from bs4 import BeautifulSoup

            soup = BeautifulSoup(text, "html.parser")
            items = soup.select(".lst_item") or soup.select("div[class*='product_item']")
            for idx, item in enumerate(items, 1):
                if store_name in item.get_text():
                    log(f"✅ {idx}위에서 '{store_name}' 발견")
                    return idx
        except Exception:
            matches = re.findall(
                r'<a[^>]*class="[^"]*product_link[^"]*"[^>]*>(.*?)</a>',
                text,
                re.DOTALL,
            )
            for idx, match in enumerate(matches, 1):
                if store_name in match:
                    log(f"✅ 정규식 파싱: {idx}위에서 '{store_name}' 발견")
                    return idx

        log("⚠️ 1페이지(약 100위) 내 미노출")
        return 100
    except Exception as e:
        log(f"❌ 순위 조회 실패: {e}")
        return None


def _keywords_for_run(config=None, *, serverless=False):
    """Vercel 등 서버리스에서는 우선 키워드만 추적."""
    config = config or load_config()
    if serverless or os.environ.get("VERCEL"):
        priority = config.get("priority_keywords") or []
        if priority:
            return priority
        limit = int(config.get("priority_track_limit") or 10)
        return (config.get("keywords") or [])[:limit]
    return config.get("keywords") or []


def track_all_keywords(logger=None, *, serverless=None):
    config = load_config()
    if serverless is None:
        serverless = bool(os.environ.get("VERCEL"))
    keywords = _keywords_for_run(config, serverless=serverless)
    if not keywords:
        kw = config.get("default_keyword")
        if kw:
            keywords = [{"keyword": kw, "store_name": config.get("store_name", "")}]
    if not keywords:
        if logger:
            logger("⚠️ 추적할 키워드가 없습니다. config.json을 설정하세요.")
        return []
    if logger and serverless:
        logger(f"📌 서버리스 우선 추적: {len(keywords)}개 키워드")

    results = []
    for item in keywords:
        keyword = item.get("keyword", "")
        store_name = item.get("store_name") or config.get("store_name", "")
        if not keyword or not store_name:
            continue

        prev = get_last_rank(keyword, store_name)
        product_id = item.get("product_id")
        if product_id:
            rank = check_product_rank(keyword, product_id, logger=logger)
        else:
            rank = check_naver_shopping_rank(keyword, store_name, logger=logger)
        if rank is None:
            # 탐색 범위 초과 — 미발견으로 기록
            detail = f"미발견 (520위 초과)" if prev is None else (
                f"{prev}위 → 미발견 (520위 초과)"
            )
            append_history(keyword, store_name, 999, prev, "순위추적", detail)
            results.append({
                "keyword": keyword,
                "store_name": store_name,
                "rank": None,
                "prev_rank": prev,
                "change": None,
                "detail": detail,
                "success": True,
                "not_found": True,
            })
            if logger:
                logger(f"📊 [{keyword}] {detail}")
            continue

        if prev is None:
            detail = f"첫 기록: {rank}위"
        elif rank < prev:
            detail = f"{prev}위 → {rank}위 ({prev - rank}단계 상승)"
        elif rank > prev:
            detail = f"{prev}위 → {rank}위 ({rank - prev}단계 하락)"
        else:
            detail = f"순위 유지 ({rank}위)"

        append_history(keyword, store_name, rank, prev, "순위추적", detail)
        results.append({
            "keyword": keyword,
            "store_name": store_name,
            "rank": rank,
            "prev_rank": prev,
            "change": prev - rank if prev is not None else 0,
            "detail": detail,
            "success": True,
            "not_found": False,
        })
        if logger:
            logger(f"📊 [{keyword}] {detail}")

    return results


def build_completion_report(results):
    if not results:
        return {
            "summary": "추적할 키워드가 없습니다.",
            "items": [],
            "improved": 0,
            "declined": 0,
            "unchanged": 0,
        }

    items = []
    improved = declined = unchanged = 0

    for r in results:
        if not r.get("success"):
            items.append({
                "keyword": r["keyword"],
                "status": "실패",
                "message": "순위 조회에 실패했습니다.",
            })
            continue

        prev = r.get("prev_rank")
        rank = r["rank"]
        if prev is None:
            status = "신규기록"
            unchanged += 1
        elif rank < prev:
            status = "상승"
            improved += 1
        elif rank > prev:
            status = "하락"
            declined += 1
        else:
            status = "유지"
            unchanged += 1

        rank_text = f"{rank}위" if rank is not None else "미발견"
        prev_text = f"{prev}위" if prev else "기록 없음"

        items.append({
            "keyword": r["keyword"],
            "store_name": r["store_name"],
            "status": status,
            "prev_rank": prev,
            "current_rank": rank,
            "prev_text": prev_text,
            "rank_text": rank_text,
            "detail": r.get("detail", ""),
            "tasks": ["네이버 쇼핑 모바일 검색 순위 조회"],
        })

    lines = []
    for item in items:
        if item["status"] == "실패":
            lines.append(f"• {item['keyword']}: 조회 실패")
        else:
            lines.append(f"• {item['keyword']}: {item['prev_text']} → {item['rank_text']} ({item['status']})")

    summary = (
        f"작업 완료 — 상승 {improved}건, 하락 {declined}건, "
        f"유지/신규 {unchanged + (len(items) - improved - declined - sum(1 for i in items if i['status']=='실패'))}건"
    )

    return {
        "summary": summary,
        "items": items,
        "improved": improved,
        "declined": declined,
        "unchanged": unchanged,
        "completed_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
    }
