import csv
import json
import os
import re
from datetime import datetime
from urllib.parse import quote

import requests

from app_resources import get_storage_dir
from hub_runtime import is_cloud_hub, is_cron_mode, uses_ephemeral_disk

HISTORY_HEADERS = ["날짜", "키워드", "스토어명", "순위", "이전순위", "변동", "작업유형", "상세"]

_BUNDLE_DIR = os.path.dirname(os.path.abspath(__file__))
_DEFAULT_CONFIG_PATH = os.path.join(_BUNDLE_DIR, "config.defaults.json")

# Android Chrome UA — 모바일 앱·실기기에서 네이버 응답 안정화
MOBILE_UA = (
    "Mozilla/5.0 (Linux; Android 14; SM-S918N) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0.0.0 Mobile Safari/537.36"
)

_NAVER_OPENAPI_URL = "https://openapi.naver.com/v1/search/shop.json"
_SHOPPING_SESSION: requests.Session | None = None


def _naver_api_credentials() -> tuple[str | None, str | None]:
    cid = (
        os.environ.get("NAVER_CLIENT_ID", "").strip()
        or os.environ.get("NAVER_SEARCH_CLIENT_ID", "").strip()
    )
    secret = (
        os.environ.get("NAVER_CLIENT_SECRET", "").strip()
        or os.environ.get("NAVER_SEARCH_CLIENT_SECRET", "").strip()
    )
    if cid and secret:
        return cid, secret
    return None, None


def _shopping_session() -> requests.Session:
    global _SHOPPING_SESSION
    if _SHOPPING_SESSION is None:
        _SHOPPING_SESSION = requests.Session()
    return _SHOPPING_SESSION


def _shopping_headers(keyword: str) -> dict[str, str]:
    return {
        "User-Agent": MOBILE_UA,
        "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Referer": "https://m.naver.com/",
        "Cache-Control": "no-cache",
    }


def _warmup_shopping_session(session: requests.Session) -> None:
    try:
        session.get("https://m.naver.com/", headers=_shopping_headers(""), timeout=12)
    except Exception:
        pass


def _openapi_product_ids(keyword: str, start: int = 1, display: int = 40) -> tuple[list[str] | None, str | None]:
    cid, secret = _naver_api_credentials()
    if not cid or not secret:
        return None, "no_api"
    params = {
        "query": keyword.strip(),
        "display": min(max(display, 1), 100),
        "start": max(start, 1),
        "sort": "sim",
    }
    headers = {
        "X-Naver-Client-Id": cid,
        "X-Naver-Client-Secret": secret,
        "User-Agent": MOBILE_UA,
    }
    try:
        res = requests.get(_NAVER_OPENAPI_URL, params=params, headers=headers, timeout=20)
        if res.status_code != 200:
            return None, f"api_http_{res.status_code}"
        ids: list[str] = []
        for item in res.json().get("items") or []:
            link = item.get("link") or ""
            match = re.search(r"/products/(\d+)", link)
            if match:
                ids.append(match.group(1))
                continue
            pid = str(item.get("productId") or item.get("product_id") or "").strip()
            if pid.isdigit():
                ids.append(pid)
        return ids, None
    except Exception as exc:
        return None, str(exc)


def _fetch_shopping_html(keyword: str, start: int = 1, logger=None) -> tuple[str | None, str | None]:
    """모바일 쇼핑 HTML. 오류: blocked|timeout|connection|error|empty"""
    import time

    def log(msg: str) -> None:
        if logger:
            logger(msg)

    on_cloud = is_cloud_hub()
    session = _shopping_session()
    url = _shopping_search_url(keyword, start=start)
    headers = _shopping_headers(keyword)
    delays = (0.4, 1.2, 2.5) if on_cloud else (0.2, 0.7)
    last_status = 0

    for attempt, delay in enumerate(delays, 1):
        if attempt == 1:
            _warmup_shopping_session(session)
        try:
            res = session.get(url, headers=headers, timeout=25)
            last_status = res.status_code
            if res.status_code == 200:
                if res.text.strip():
                    return res.text, None
                return None, "empty"
            if res.status_code in (403, 418, 429):
                if attempt < len(delays):
                    log(f"   ⚠️ HTTP {res.status_code} — {delay:.1f}초 후 재시도 ({attempt}/{len(delays)})")
                    time.sleep(delay)
                    continue
                return None, "blocked"
        except requests.exceptions.Timeout:
            if attempt >= len(delays):
                return None, "timeout"
            time.sleep(delay)
        except requests.exceptions.ConnectionError:
            if attempt >= len(delays):
                return None, "connection"
            time.sleep(delay)

    if last_status in (403, 418, 429):
        return None, "blocked"
    return None, "error"


def _fetch_shopping_page_ids(
    keyword: str,
    start: int = 1,
    logger=None,
) -> tuple[list[str], str | None, str]:
    """(상품 ID 목록, 오류코드, 소스) — 오류: blocked|empty|timeout|connection|error"""
    def log(msg: str) -> None:
        if logger:
            logger(msg)

    cid, _secret = _naver_api_credentials()
    if cid:
        ids, api_err = _openapi_product_ids(keyword, start=start)
        if ids is not None:
            return ids, None if ids else "empty", "openapi"
        if api_err and api_err != "no_api":
            log(f"   ⚠️ 네이버 검색 API 실패: {api_err}")

    html, err = _fetch_shopping_html(keyword, start=start, logger=logger)
    if err == "blocked":
        if not cid:
            ids, _api_err = _openapi_product_ids(keyword, start=start)
            if ids is not None:
                if ids:
                    log("   ☁️ 공식 검색 API로 대체 조회")
                return ids, None if ids else "empty", "openapi"
        return [], "blocked", "html"
    if err:
        return [], err, "html"
    ids = _extract_ordered_product_ids(html or "")
    return ids, None if ids else "empty", "html"


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
        ids, err, _source = _fetch_shopping_page_ids("퍼마코트")
        if err == "blocked":
            cid, _ = _naver_api_credentials()
            if cid:
                return False, "HTTP 403 — NAVER_CLIENT_ID가 설정되어 있으나 API 조회도 실패했습니다."
            return (
                False,
                "HTTP 403 — 클라우드 IP 차단. Cloudtype에 NAVER_CLIENT_ID·NAVER_CLIENT_SECRET 설정 또는 PC 로컬 허브 사용",
            )
        if err and err not in ("empty",):
            return False, f"조회 실패 ({err})"
        if not ids:
            return False, "검색 페이지는 열렸으나 상품 목록을 파싱하지 못했습니다."
        return True, f"연결 정상 (샘플 상품 {len(ids)}건 인식)"
    except Exception as e:
        return False, str(e)


def _load_defaults_config():
    for path in (
        _DEFAULT_CONFIG_PATH,
        os.path.join(os.getcwd(), "config.defaults.json"),
    ):
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
    return None


def load_config():
    defaults = _load_defaults_config()
    path = _config_path()
    user = None
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                user = json.load(f)
        except (json.JSONDecodeError, OSError):
            user = None

    if user and defaults:
        cfg = {**defaults, **user}
        for key in ("keywords", "products", "product_urls", "blog_urls", "priority_keywords"):
            if not cfg.get(key):
                cfg[key] = defaults.get(key) or []
        return cfg
    if user:
        if user.get("keywords"):
            return user
        if defaults:
            return {**defaults, **user, "keywords": defaults.get("keywords") or []}
        return user
    if defaults:
        return defaults
    return {
        "store_name": "나눔랩",
        "track_interval_minutes": 60,
        "priority_track_limit": 10,
        "keywords": [],
        "product_urls": [],
        "blog_urls": [],
    }


def save_config(config):
    path = _config_path()
    try:
        parent = os.path.dirname(path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
    except OSError:
        if not uses_ephemeral_disk():
            raise


def ensure_history_file():
    path = _history_path()
    if os.path.exists(path):
        return
    parent = os.path.dirname(path)
    if parent:
        try:
            os.makedirs(parent, exist_ok=True)
        except OSError:
            if not uses_ephemeral_disk():
                raise
            return
    try:
        with open(path, "w", encoding="utf-8-sig", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(HISTORY_HEADERS)
    except OSError:
        if not uses_ephemeral_disk():
            raise


def get_history(limit=None):
    try:
        from rank_persistence import fetch_history

        rows = fetch_history(limit=limit)
        if rows:
            return rows
    except Exception:
        pass
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
    if prev_rank is None:
        change = "-"
    elif rank < prev_rank:
        change = f"+{prev_rank - rank}"
    elif rank > prev_rank:
        change = f"-{rank - prev_rank}"
    else:
        change = "0"

    row = {
        "날짜": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "키워드": keyword,
        "스토어명": store_name,
        "순위": rank,
        "이전순위": prev_rank if prev_rank is not None else "-",
        "변동": change,
        "작업유형": task_type,
        "상세": detail,
    }
    try:
        from rank_persistence import append_history_row

        append_history_row(row)
        return
    except Exception:
        pass
    ensure_history_file()
    try:
        with open(_history_path(), "a", encoding="utf-8-sig", newline="") as f:
            writer = csv.writer(f)
            writer.writerow([row[h] for h in HISTORY_HEADERS])
    except OSError:
        if not uses_ephemeral_disk():
            raise


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

    remaining = set(product_map.keys())  # 아직 못 찾은 상품
    results = []
    cumulative_rank = 0
    blocked = False

    try:
        for page in range(1, max_pages + 1):
            if not remaining:
                break  # 모든 상품 발견

            start = (page - 1) * 40 + 1
            log(f"   📄 {page}페이지 조회 중... (start={start}, 미발견 상품 {len(remaining)}건)")

            page_ids, err, _source = _fetch_shopping_page_ids(keyword, start=start, logger=logger)
            if err == "blocked":
                log("   ⚠️ HTTP 403 — 네이버 접근 차단 (클라우드 IP 또는 NAVER_CLIENT_ID 필요)")
                blocked = True
                break
            if err in ("timeout", "connection", "error"):
                log(f"   ⚠️ {page}페이지 {err} — 중단")
                break
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
                time.sleep(1.0 if is_cloud_hub() else 0.5)  # 네이버 요청 간격 준수

        if blocked:
            return results, "blocked"

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
    반환: (순위 또는 None, 상태) — 상태는 None|blocked|not_found|error
    """
    def log(msg):
        if logger:
            logger(msg)

    product_id = str(product_id).strip()
    log(f"🔍 '{keyword}' 검색 결과에서 상품 {product_id} 순위 조회 (최대 {max_pages}페이지)...")

    cumulative_rank = 0

    try:
        for page in range(1, max_pages + 1):
            start = (page - 1) * 40 + 1
            log(f"   📄 {page}페이지 조회 중... (start={start})")

            page_ids, err, _source = _fetch_shopping_page_ids(keyword, start=start, logger=logger)
            if err == "blocked":
                log("   ⚠️ HTTP 403 — 중단")
                return None, "blocked"
            if err in ("timeout", "connection", "error"):
                log(f"   ⚠️ 조회 실패 ({err}) — 중단")
                return None, err
            if not page_ids:
                log(f"   ⚠️ {page}페이지에서 상품 미발견 — 탐색 종료")
                break

            for pid in page_ids:
                cumulative_rank += 1
                if pid == product_id:
                    log(f"✅ 상품 {product_id}: {cumulative_rank}위 ({page}페이지)")
                    return cumulative_rank, None

            import time
            time.sleep(1.0 if is_cloud_hub() else 0.5)

        log(f"⚠️ 상품 {product_id} {cumulative_rank}위 이후에도 미발견")
        return None, "not_found"
    except Exception as e:
        log(f"❌ 상품 순위 조회 실패: {e}")
        return None, "error"


def check_naver_shopping_rank(keyword, store_name, logger=None):
    def log(msg):
        if logger:
            logger(msg)

    log(f"🔍 '{keyword}' 키워드로 '{store_name}' 순위 조회 중...")

    try:
        text, err = _fetch_shopping_html(keyword, logger=logger)
        if err == "blocked":
            log("❌ 순위 조회 실패: 네이버 HTTP 403 (클라우드 IP 차단)")
            return None
        if err or not text:
            log("⚠️ 1페이지(약 100위) 내 미노출")
            return 100

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
    """클라우드·Cron에서는 우선 키워드만 추적 (403·할당량 방지)."""
    config = config or load_config()
    if serverless or is_cron_mode() or is_cloud_hub():
        priority = config.get("priority_keywords") or []
        if priority:
            return priority
        limit = int(config.get("priority_track_limit") or 10)
        return (config.get("keywords") or [])[:limit]
    return config.get("keywords") or []


def _rotate_keywords(keywords, offset: int, batch_size: int):
    if not keywords or batch_size <= 0:
        return keywords
    n = len(keywords)
    size = min(batch_size, n)
    start = offset % n
    picked = [keywords[(start + i) % n] for i in range(size)]
    return picked


def track_all_keywords(logger=None, *, serverless=None, keyword_offset=0, keyword_batch_size=None):
    config = load_config()
    if serverless is None:
        serverless = is_cron_mode()
    keywords = _keywords_for_run(config, serverless=serverless)
    if keyword_batch_size:
        keywords = _rotate_keywords(keywords, int(keyword_offset or 0), int(keyword_batch_size))
        if logger:
            logger(f"📌 Cron 배치: {len(keywords)}개 키워드 (offset={keyword_offset})")
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

    max_pages = int(config.get("serverless_max_pages") or 5) if serverless else 13

    results = []
    blocked_abort = False
    for item in keywords:
        if blocked_abort:
            break
        keyword = item.get("keyword", "")
        store_name = item.get("store_name") or config.get("store_name", "")
        if not keyword or not store_name:
            continue

        prev = get_last_rank(keyword, store_name)
        product_id = item.get("product_id")
        rank_status = None
        if product_id:
            rank, rank_status = check_product_rank(keyword, product_id, logger=logger, max_pages=max_pages)
        else:
            rank = check_naver_shopping_rank(keyword, store_name, logger=logger)
            if rank is None:
                rank_status = "blocked"

        if rank_status == "blocked":
            detail = "네이버 HTTP 403 — NAVER_CLIENT_ID·SECRET 설정 필요 (developers.naver.com 검색 API)"
            results.append({
                "keyword": keyword,
                "store_name": store_name,
                "product_id": product_id,
                "rank": None,
                "prev_rank": prev,
                "change": None,
                "detail": detail,
                "success": False,
                "blocked": True,
            })
            if logger:
                logger(f"📊 [{keyword}] {detail}")
                rest = len(keywords) - len(results)
                if rest > 0:
                    logger(f"⏭️ 네이버 403 — 나머지 {rest}개 키워드 스킵 (.env 또는 Cloudtype에 API 키 설정)")
                blocked_abort = True
            continue

        if rank_status in ("timeout", "connection", "error"):
            detail = f"순위 조회 실패 ({rank_status})"
            results.append({
                "keyword": keyword,
                "store_name": store_name,
                "product_id": product_id,
                "rank": None,
                "prev_rank": prev,
                "change": None,
                "detail": detail,
                "success": False,
            })
            if logger:
                logger(f"📊 [{keyword}] {detail}")
            continue

        if rank is None:
            # 탐색 범위 초과 — 미발견으로 기록
            detail = f"미발견 (520위 초과)" if prev is None else (
                f"{prev}위 → 미발견 (520위 초과)"
            )
            append_history(keyword, store_name, 999, prev, "순위추적", detail)
            results.append({
                "keyword": keyword,
                "store_name": store_name,
                "product_id": product_id,
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
            "product_id": product_id,
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
        if r.get("blocked"):
            items.append({
                "keyword": r["keyword"],
                "status": "차단",
                "message": r.get("detail") or "네이버 접근 차단 (HTTP 403)",
            })
            continue
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
            "product_id": r.get("product_id"),
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
