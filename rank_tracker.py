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

RANKS_PER_PAGE = 40
NAVER_API_MAX_START = 1000
DEFAULT_MAX_PAGES = 25  # 25페이지 × 40 = 1000위 (네이버 API 상한)
NOT_FOUND_RANK = 10001  # 실제 순위가 아닌 '탐색 범위 내 미노출' 저장값

_BUNDLE_DIR = os.path.dirname(os.path.abspath(__file__))
_DEFAULT_CONFIG_PATH = os.path.join(_BUNDLE_DIR, "config.defaults.json")

# Android Chrome UA — 모바일 앱·실기기에서 네이버 응답 안정화
MOBILE_UA = (
    "Mozilla/5.0 (Linux; Android 14; SM-S918N) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0.0.0 Mobile Safari/537.36"
)

_NAVER_OPENAPI_URL = "https://openapi.naver.com/v1/search/shop.json"
_SHOPPING_SESSION: requests.Session | None = None


def rank_scan_max_pages(config: dict | None = None) -> int:
    config = config or {}
    env = (os.environ.get("RANK_SCAN_MAX_PAGES") or "").strip()
    if env.isdigit():
        return max(1, int(env))
    return int(config.get("rank_scan_max_pages") or DEFAULT_MAX_PAGES)


def rank_depth_limit(max_pages: int | None = None, config: dict | None = None) -> int:
    mp = max_pages if max_pages is not None else rank_scan_max_pages(config)
    return min(mp * RANKS_PER_PAGE, NAVER_API_MAX_START)


def normalize_rank(rank) -> int | None:
    """999/10001 등 미노출 저장값은 None, 그 외는 실제 순위."""
    if rank is None:
        return None
    try:
        value = int(rank)
    except (TypeError, ValueError):
        return None
    if value >= 999:
        return None
    return value


def is_not_found_rank(rank) -> bool:
    return normalize_rank(rank) is None and rank is not None


def format_rank_label(rank, *, threshold: int = 100, scan_depth: int | None = None) -> str:
    real = normalize_rank(rank)
    if real is not None:
        if 1 <= real <= threshold:
            return f"{real}위"
        return f"{real}위 (100위 밖)"
    depth = scan_depth or rank_depth_limit()
    return f"{depth}위까지 탐색·미노출"


def _page_start(page: int) -> int:
    return (page - 1) * RANKS_PER_PAGE + 1


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
        "start": min(max(start, 1), NAVER_API_MAX_START),
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
                value = int(row.get("순위", 100))
            except (TypeError, ValueError):
                return None
            if value >= 999:
                return NOT_FOUND_RANK
            return value
    return None


def is_ranked(rank, threshold: int = 100) -> bool:
    """1~threshold위만 '순위 진입'으로 간주."""
    if rank is None:
        return False
    try:
        value = int(rank)
    except (TypeError, ValueError):
        return False
    return 1 <= value <= threshold


def _rank_overview_path() -> str:
    return os.path.join(get_storage_dir(), "data", "rank_latest_summary.json")


def _bundled_rank_overview_path() -> str:
    """배포 이미지에 포함된 순위 요약 (Cloudtype /tmp 비어 있을 때 사용)."""
    for base in (os.getcwd(), os.path.dirname(os.path.abspath(__file__))):
        path = os.path.join(base, "data", "rank_latest_summary.json")
        if os.path.isfile(path):
            return path
    return os.path.join(os.getcwd(), "data", "rank_latest_summary.json")


def _rank_overview_read_paths() -> list[str]:
    """클라우드: 번들 우선 → /tmp. 로컬: 쓰기 경로 우선."""
    runtime = _rank_overview_path()
    bundled = _bundled_rank_overview_path()
    if uses_ephemeral_disk():
        return [p for p in (bundled, runtime) if p]
    return [p for p in (runtime, bundled) if p]


def build_rank_overview(results: list[dict], *, threshold: int = 100) -> dict:
    """전체 순위 스캔 집계 — 대시보드·리포트용."""
    total = len(results)
    scanned = sum(1 for r in results if r.get("rank") is not None)
    ranked_top100 = [r for r in results if r.get("in_top100")]
    ranked_top50 = [r for r in results if is_ranked(r.get("rank"), 50)]
    ranked_top10 = [r for r in results if is_ranked(r.get("rank"), 10)]
    api_errors = sum(
        1
        for r in results
        if r.get("status") in ("error", "timeout", "connection", "api_error", "blocked")
        or (r.get("rank") is None and r.get("status") not in ("not_found", "ok", "no_product_id"))
    )
    outside_100 = [
        r
        for r in results
        if normalize_rank(r.get("rank")) is not None and not r.get("in_top100")
    ]
    not_found = [r for r in results if is_not_found_rank(r.get("rank")) or r.get("rank") is None]
    scan_depth = rank_depth_limit()

    pct = round(100 * len(ranked_top100) / total, 1) if total else 0.0
    return {
        "total": total,
        "scanned": scanned,
        "ranked_top100": len(ranked_top100),
        "ranked_top50": len(ranked_top50),
        "ranked_top10": len(ranked_top10),
        "outside_top100": len(outside_100),
        "not_found": len(not_found),
        "api_errors": api_errors,
        "unranked": total - len(ranked_top100),
        "progress_pct": pct,
        "threshold": threshold,
        "scan_depth": scan_depth,
        "scanned_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "top100_keywords": [
            {
                "keyword": r["keyword"],
                "rank": r.get("rank"),
                "product_name": r.get("product_name") or "",
                "product_id": r.get("product_id") or "",
            }
            for r in sorted(ranked_top100, key=lambda x: x.get("rank") or 9999)
        ],
        "work_queue": [
            {
                "keyword": r["keyword"],
                "rank": r.get("rank"),
                "rank_label": r.get("rank_label") or "미진입",
                "product_name": r.get("product_name") or "",
                "bucket": "boost",
            }
            for r in sorted(
                [x for x in results if not x.get("in_top100")],
                key=lambda x: (x.get("rank") is None, x.get("rank") or 9999),
            )[:40]
        ],
    }


def save_rank_overview(results: list[dict], *, threshold: int = 100, report_paths: dict | None = None) -> dict:
    """최신 전체 스캔 요약을 data/rank_latest_summary.json 에 저장."""
    overview = build_rank_overview(results, threshold=threshold)
    overview["keywords"] = {
        f"{r['keyword']}\0{r.get('store_name', '')}": {
            "rank": r.get("rank"),
            "in_top100": bool(r.get("in_top100")),
            "rank_label": r.get("rank_label"),
            "status": r.get("status"),
            "product_id": r.get("product_id"),
            "product_name": r.get("product_name"),
        }
        for r in results
    }
    if report_paths:
        overview["report_csv"] = str(report_paths.get("csv") or "")
        overview["report_txt"] = str(report_paths.get("txt") or "")

    written: set[str] = set()
    for path in _rank_overview_read_paths():
        if path in written:
            continue
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                json.dump(overview, f, ensure_ascii=False, indent=2)
            written.add(path)
        except OSError:
            continue

    try:
        from rank_persistence import load_hub_state, save_hub_state

        state = load_hub_state()
        state["last_full_scan_at"] = overview["scanned_at"]
        state["rank_overview"] = {
            k: overview[k]
            for k in (
                "total",
                "ranked_top100",
                "ranked_top50",
                "ranked_top10",
                "outside_top100",
                "not_found",
                "api_errors",
                "progress_pct",
                "scanned_at",
            )
        }
        save_hub_state(state)
    except Exception:
        pass

    return overview


def load_rank_overview(*, max_age_hours: int = 168) -> dict | None:
    """최근 전체 스캔 요약 (기본 7일 이내)."""
    data = None
    for path in _rank_overview_read_paths():
        if not os.path.isfile(path):
            continue
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            break
        except Exception:
            continue
    if not data:
        return None
    scanned_at = data.get("scanned_at") or ""
    if scanned_at and max_age_hours > 0:
        try:
            ts = datetime.strptime(scanned_at, "%Y-%m-%d %H:%M:%S")
            age_h = (datetime.now() - ts).total_seconds() / 3600
            if age_h > max_age_hours:
                data["_stale"] = True
        except ValueError:
            pass
    return data


def _rank_from_overview(overview: dict | None, keyword: str, store_name: str) -> int | None:
    if not overview:
        return None
    keywords = overview.get("keywords") or {}
    row = keywords.get(f"{keyword}\0{store_name}")
    if not row:
        row = keywords.get(f"{keyword}\0") or keywords.get(keyword)
    if not row:
        return None
    rank = row.get("rank")
    if rank is None:
        return None
    try:
        return int(rank)
    except (TypeError, ValueError):
        return None


def _keyword_entries(config: dict | None = None) -> list[dict]:
    """priority_keywords + keywords 중복 제거 목록."""
    config = config or load_config()
    default_store = config.get("store_name", "")
    seen: set[tuple[str, str, str]] = set()
    entries: list[dict] = []

    for source in (config.get("priority_keywords") or [], config.get("keywords") or []):
        for item in source:
            if not isinstance(item, dict):
                continue
            keyword = (item.get("keyword") or "").strip()
            if not keyword:
                continue
            store_name = (item.get("store_name") or default_store).strip()
            product_id = str(item.get("product_id") or "").strip()
            key = (keyword, store_name, product_id)
            if key in seen:
                continue
            seen.add(key)
            entries.append({"keyword": keyword, "store_name": store_name, "product_id": product_id})
    return entries


def _product_name_for(config: dict, product_id: str) -> str:
    if not product_id:
        return ""
    for product in config.get("products") or []:
        if str(product.get("id")) == str(product_id):
            return (product.get("name") or "").strip()
    return ""


def split_keywords_by_rank(
    config: dict | None = None,
    threshold: int | None = None,
) -> tuple[list[dict], list[dict]]:
    """(미진입 키워드, 순위 유지 키워드) 분리."""
    config = config or load_config()
    limit = int(threshold or config.get("traffic_rank_threshold") or 100)
    overview = load_rank_overview()
    use_overview = bool(overview and not overview.get("_stale") and overview.get("keywords"))
    unranked: list[dict] = []
    ranked: list[dict] = []

    for entry in _keyword_entries(config):
        kw = entry["keyword"]
        store = entry["store_name"]
        rank = get_last_rank(kw, store)
        if use_overview:
            ov_rank = _rank_from_overview(overview, kw, store)
            if ov_rank is not None:
                rank = ov_rank
        row = {
            **entry,
            "last_rank": rank,
            "product_name": _product_name_for(config, entry.get("product_id", "")),
        }
        if is_ranked(rank, limit):
            ranked.append(row)
        else:
            unranked.append(row)
    return unranked, ranked


def _last_history_row(keyword: str, store_name: str) -> dict | None:
    for row in reversed(get_history()):
        if row.get("키워드") == keyword and row.get("스토어명") == store_name:
            return row
    return None


def _rank_status_label(rank, threshold: int, row: dict | None, *, scan_depth: int | None = None) -> str:
    depth = scan_depth or rank_depth_limit()
    real = normalize_rank(rank)
    if real is not None and is_ranked(real, threshold):
        change = str((row or {}).get("변동") or "")
        if "상승" in change or (change.startswith("+") and change not in ("0", "+0")):
            return f"{real}위 상승"
        if "하락" in change or (change.startswith("-") and change not in ("-", "-0")):
            return f"{real}위 하락"
        return f"{real}위 유지"
    if real is not None:
        change = str((row or {}).get("변동") or "")
        if "상승" in change or (change.startswith("+") and change not in ("0", "+0")):
            return f"{real}위 상승 (100위 밖)"
        if "하락" in change or (change.startswith("-") and change not in ("-", "-0")):
            return f"{real}위 하락 (100위 밖)"
        return f"{real}위 (100위 밖)"
    if rank is None and not row:
        return "미조회"
    return format_rank_label(None, scan_depth=depth)


def get_keyword_rank_summary(config: dict | None = None) -> list[dict]:
    """대시보드용 — 키워드별 최근 순위 (미진입 우선 정렬)."""
    config = config or load_config()
    threshold = int(config.get("traffic_rank_threshold") or 100)
    overview = load_rank_overview()
    use_overview = bool(overview and not overview.get("_stale") and overview.get("keywords"))
    scan_depth = int((overview or {}).get("scan_depth") or 0) or rank_depth_limit(config=config)

    unranked: list[dict] = []
    ranked: list[dict] = []
    for entry in _keyword_entries(config):
        kw = entry["keyword"]
        store = entry["store_name"]
        rank = get_last_rank(kw, store)
        if use_overview:
            ov_rank = _rank_from_overview(overview, kw, store)
            if ov_rank is not None:
                rank = ov_rank
        row = {
            **entry,
            "last_rank": rank,
            "product_name": _product_name_for(config, entry.get("product_id", "")),
        }
        if is_ranked(rank, threshold):
            ranked.append(row)
        else:
            unranked.append(row)

    def _bucket_for(rank_val) -> str:
        real = normalize_rank(rank_val)
        if real is not None and is_ranked(real, threshold):
            return "ranked"
        return "unranked"

    summary: list[dict] = []
    for row in unranked + ranked:
        rank = row.get("last_rank")
        hist = _last_history_row(row["keyword"], row["store_name"])
        bucket = _bucket_for(rank)
        summary.append(
            {
                "keyword": row["keyword"],
                "product_id": row.get("product_id"),
                "product_name": row.get("product_name") or row.get("product_id") or "",
                "last_rank": rank,
                "rank_display": format_rank_label(rank, threshold=threshold, scan_depth=scan_depth),
                "status_label": _rank_status_label(rank, threshold, hist, scan_depth=scan_depth),
                "bucket": bucket,
                "traffic_mode": "maintain" if bucket == "ranked" else "boost",
            }
        )
    return summary


def _listing_urls_for(config: dict, product_id: str) -> list[str]:
    """동일 storefront_id 에 매핑된 판매자 리스팅 URL (SEO 다중 상품)."""
    pid = str(product_id or "").strip()
    if not pid:
        return []
    urls: list[str] = []
    seen: set[str] = set()
    for row in config.get("product_listings") or []:
        if not isinstance(row, dict):
            continue
        if str(row.get("storefront_id") or "").strip() != pid:
            continue
        url = (row.get("url") or "").strip()
        if url.startswith(("http://", "https://")) and url not in seen:
            seen.add(url)
            urls.append(url)
    return urls


def _product_url_for(config: dict, product_id: str, hub_state: dict | None = None) -> str:
    store = (config.get("store_name") or "nanumlab").replace(" ", "")
    listings = _listing_urls_for(config, product_id)
    if listings and hub_state is not None:
        li = int(hub_state.get("listing_url_index") or 0)
        hub_state["listing_url_index"] = (li + 1) % len(listings)
        return listings[li % len(listings)]

    if product_id:
        for product in config.get("products") or []:
            if str(product.get("id")) == str(product_id):
                url = (product.get("url") or "").strip()
                if url:
                    return url
        if listings:
            return listings[0]
        return f"https://smartstore.naver.com/{store}/products/{product_id}"

    for product in config.get("products") or []:
        url = (product or {}).get("url", "")
        if url:
            return url
    urls = config.get("product_urls") or []
    for item in urls:
        if isinstance(item, str) and item:
            return item
        if isinstance(item, dict) and item.get("url"):
            return item["url"]
    return f"https://smartstore.naver.com/{store}"


def pick_traffic_target(config: dict | None = None, hub_state: dict | None = None) -> dict:
    """미진입 키워드 우선 트래픽, 모두 진입 후 유지 모드."""
    config = config or load_config()
    hub_state = hub_state or {}
    unranked, ranked = split_keywords_by_rank(config)

    if unranked:
        pool, mode = unranked, "boost"
    elif ranked:
        pool, mode = ranked, "maintain"
    else:
        return {
            "url": _product_url_for(config, ""),
            "keyword": "",
            "product_id": "",
            "mode": "fallback",
            "last_rank": None,
            "next_index": int(hub_state.get("traffic_target_index") or 0),
            "unranked_count": 0,
            "ranked_count": 0,
            "referer_url": "https://m.naver.com/",
        }

    idx = int(hub_state.get("traffic_target_index") or 0)
    picked = pool[idx % len(pool)]
    next_index = (idx + 1) % len(pool)
    keyword = picked["keyword"]

    return {
        "url": _product_url_for(config, picked.get("product_id", ""), hub_state),
        "keyword": keyword,
        "product_id": picked.get("product_id", ""),
        "product_name": picked.get("product_name") or _product_name_for(config, picked.get("product_id", "")),
        "mode": mode,
        "last_rank": picked.get("last_rank"),
        "next_index": next_index,
        "unranked_count": len(unranked),
        "ranked_count": len(ranked),
        "referer_url": (
            f"https://search.shopping.naver.com/search/all?query={quote(keyword)}"
            if mode == "boost" and keyword
            else "https://m.naver.com/"
        ),
    }


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


def check_product_rank(keyword, product_id, logger=None, max_pages=None, config=None):
    """
    특정 스마트스토어 상품 ID의 쇼핑 검색 노출 순위.
    반환: (순위 또는 None, 상태) — 상태는 None|blocked|not_found|error
    """
    def log(msg):
        if logger:
            logger(msg)

    if max_pages is None:
        max_pages = rank_scan_max_pages(config)
    depth_limit = rank_depth_limit(max_pages, config)
    product_id = str(product_id).strip()
    log(f"🔍 '{keyword}' 검색 결과에서 상품 {product_id} 순위 조회 (최대 {depth_limit}위까지)...")

    cumulative_rank = 0

    try:
        for page in range(1, max_pages + 1):
            start = _page_start(page)
            if start > NAVER_API_MAX_START:
                break
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

        log(f"⚠️ 상품 {product_id} {depth_limit}위까지 탐색·미노출 (실제 {cumulative_rank}개 상품 조회)")
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
    """클라우드·Cron: 미진입 키워드 우선 추적."""
    config = config or load_config()
    threshold = int(config.get("traffic_rank_threshold") or 100)
    default_store = config.get("store_name", "")

    def sort_key(item: dict) -> tuple[int, int]:
        rank = get_last_rank(item.get("keyword", ""), item.get("store_name") or default_store)
        if is_ranked(rank, threshold):
            return (1, rank or 9999)
        return (0, rank if rank is not None else 9999)

    if serverless or is_cron_mode() or is_cloud_hub():
        priority = config.get("priority_keywords") or []
        if priority:
            keywords = list(priority)
        else:
            limit = int(config.get("priority_track_limit") or 10)
            keywords = (config.get("keywords") or [])[:limit]
        return sorted(keywords, key=sort_key)
    return sorted(config.get("keywords") or [], key=sort_key)


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

    max_pages = rank_scan_max_pages(config)
    if serverless:
        batch_cap = int(config.get("serverless_max_pages") or 0)
        if batch_cap > 0:
            max_pages = min(max_pages, batch_cap)
    depth_limit = rank_depth_limit(max_pages, config)

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
            detail = format_rank_label(None, scan_depth=depth_limit)
            if normalize_rank(prev) is not None:
                detail = f"{format_rank_label(prev)} → {detail}"
            append_history(keyword, store_name, NOT_FOUND_RANK, prev, "순위추적", detail)
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
                "scan_depth": depth_limit,
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
        rank = r.get("rank")
        prev_real = normalize_rank(prev)
        rank_real = normalize_rank(rank)
        if r.get("not_found") or rank_real is None:
            status = "미발견"
            unchanged += 1
        elif prev_real is None:
            status = "신규기록"
            unchanged += 1
        elif rank_real < prev_real:
            status = "상승"
            improved += 1
        elif rank_real > prev_real:
            status = "하락"
            declined += 1
        else:
            status = "유지"
            unchanged += 1

        rank_text = (
            format_rank_label(rank, scan_depth=r.get("scan_depth") or rank_depth_limit())
            if r.get("not_found") or rank is None
            else format_rank_label(rank)
        )
        prev_real = normalize_rank(prev)
        prev_text = format_rank_label(prev) if prev_real is not None else "기록 없음"

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


def build_workflow_status(
    config: dict | None = None,
    *,
    hub_state: dict | None = None,
    kw_summary: list[dict] | None = None,
    rank_overview: dict | None = None,
) -> dict:
    """대시보드 플로우차트용 — 단계별 작업·순위 진행."""
    config = config or load_config()
    hub_state = hub_state or {}
    kw_summary = kw_summary or get_keyword_rank_summary(config)
    overview = rank_overview or load_rank_overview() or {}
    scan_depth = int(overview.get("scan_depth") or 0) or rank_depth_limit(config=config)

    unranked = [s for s in kw_summary if s.get("bucket") == "unranked"]
    ranked = [s for s in kw_summary if s.get("bucket") == "ranked"]
    boost_targets = unranked[:8]

    steps = [
        {
            "id": "scan",
            "title": "1. 순위 조회",
            "status": "done" if overview.get("scanned_at") else "pending",
            "detail": (
                f"NAVER API · 최대 {scan_depth}위 탐색 · "
                f"{overview.get('scanned_at') or '미실행'}"
            ),
        },
        {
            "id": "classify",
            "title": "2. 진입/미진입 분류",
            "status": "done" if kw_summary else "pending",
            "detail": f"100위 이내 {len(ranked)} · 미진입 {len(unranked)}",
        },
        {
            "id": "boost",
            "title": "3. 미진입 트래픽 (boost)",
            "status": "active" if hub_state.get("traffic_enabled") and unranked else "idle",
            "detail": (
                f"다음: {boost_targets[0]['keyword']}"
                if boost_targets
                else "대상 없음"
            ),
        },
        {
            "id": "maintain",
            "title": "4. 순위 유지 (maintain)",
            "status": "active" if ranked and hub_state.get("traffic_enabled") else "idle",
            "detail": f"유지 {len(ranked)}개 키워드",
        },
        {
            "id": "seo",
            "title": "5. SEO·블로그",
            "status": "idle",
            "detail": "스마트스토어 메타 · Gemini 블로그 · 구글 색인",
        },
    ]

    return {
        "scan_depth": scan_depth,
        "ranked_count": len(ranked),
        "unranked_count": len(unranked),
        "boost_queue": [
            {
                "keyword": x["keyword"],
                "rank_display": x.get("rank_display") or x.get("status_label"),
                "product_name": x.get("product_name"),
            }
            for x in boost_targets
        ],
        "ranked_highlights": [
            {
                "keyword": x["keyword"],
                "rank_display": x.get("rank_display") or format_rank_label(x.get("last_rank")),
            }
            for x in sorted(ranked, key=lambda r: normalize_rank(r.get("last_rank")) or 9999)[:6]
        ],
        "steps": steps,
    }
