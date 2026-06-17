import os
import sys
import threading
import time
import traceback
import locale
from datetime import datetime
from pathlib import Path

from flask import Flask, abort, jsonify, render_template, request, send_from_directory
from werkzeug.exceptions import NotFound

from rank_tracker import (
    build_completion_report,
    get_history,
    load_config,
    save_config,
    track_all_keywords,
)
from seo_checker import get_latest_audit, run_full_audit
from keyword_analyzer import analyze_keyword, suggest_keywords_for_product, analyze_all_products
from seo_content_builder import generate_content, list_workflows, save_content
from rank_tracker import check_product_rank
from javis_programs import get_catalog, launch_program
from rank_persistence import load_hub_state, persistence_backend, save_hub_state
from hub_runtime import cloud_platform, is_cloud_hub, is_cloudtype, is_cron_mode
from hub_accounts import (
    keywords_from_accounts,
    merge_keywords_into_config,
    parse_keywords_text,
    save_accounts_keywords,
    sync_accounts_keywords_to_config,
)

_VT_ROOT = Path(__file__).resolve().parent / "vercel_traffic"
if _VT_ROOT.is_dir() and str(_VT_ROOT) not in sys.path:
    sys.path.insert(0, str(_VT_ROOT))
try:
    from traffic_session import run_traffic_session
    from traffic_backoff import apply_traffic_result, effective_interval_sec, format_backoff_note
    from traffic_targets import (
        collect_traffic_urls,
        label_for_url,
        pick_traffic_url,
        traffic_pool_summary,
    )
except ImportError:
    run_traffic_session = None
    apply_traffic_result = None
    effective_interval_sec = None
    format_backoff_note = lambda _s: ""
    collect_traffic_urls = None
    label_for_url = None
    pick_traffic_url = None
    traffic_pool_summary = None

app = Flask(__name__)

_BLOG_STUDIO_MOUNTED = False


def _mount_blog_studio() -> None:
    global _BLOG_STUDIO_MOUNTED
    try:
        from blog_studio_web import _drain_file_triggers, register_blog_routes

        register_blog_routes(app)
        _BLOG_STUDIO_MOUNTED = True

        def _blog_trigger_poll_loop() -> None:
            while True:
                try:
                    _drain_file_triggers()
                except Exception:
                    pass
                time.sleep(15)

        if os.environ.get("AUTO_START_SCHEDULER", "1") != "0":
            threading.Thread(target=_blog_trigger_poll_loop, daemon=True).start()
    except Exception as exc:
        print(f"blog_studio mount failed: {exc}", flush=True)


_mount_blog_studio()


@app.route("/blog-studio")
@app.route("/blog-studio/")
def blog_studio_page():
    """Cloudtype·로컬 — 블로그 스튜디오 (register 실패 시에도 페이지 제공)."""
    try:
        from hub_llm_env import apply_blog_llm_env

        apply_blog_llm_env()
    except Exception:
        pass
    jarvis_root = os.environ.get("JARVIS_ROOT", r"D:\@code\javis")
    port = int(os.environ.get("CANON_AUTOBLOG_PORT", "8790"))
    return render_template("blog_studio.html", jarvis_root=jarvis_root, port=port)

logs_queue = []
scheduler_running = False
scheduler_thread = None
traffic_loop_running = False
traffic_thread = None
rank_stop_event = threading.Event()
traffic_stop_event = threading.Event()
last_completion_report = None
_boot_auto_started = False


def _json_error(endpoint: str, exc: Exception, status_code: int = 500):
    """클라이언트 JSON 파싱 실패 방지: 모든 서버 예외를 JSON으로 반환."""
    detail = str(exc) or exc.__class__.__name__
    add_log(f"❌ {endpoint} 오류: {detail}")
    return jsonify({
        "success": False,
        "error": detail,
        "endpoint": endpoint,
    }), status_code


@app.errorhandler(NotFound)
def _handle_not_found(exc):
    detail = f"404 Not Found: {request.path}"
    add_log(f"❌ {detail}")
    return jsonify({"success": False, "error": detail, "endpoint": request.path}), 404


@app.errorhandler(Exception)
def _handle_unexpected_error(exc):
    detail = str(exc) or exc.__class__.__name__
    add_log(f"❌ unhandled: {detail}")
    return jsonify({
        "success": False,
        "error": detail,
        "endpoint": "unhandled",
    }), 500


def is_serverless():
    """Vercel Cron · Cloudtype — 우선 키워드·요청량 제한 모드."""
    return is_cloud_hub()


def _bootstrap_from_persistence():
    global last_completion_report, logs_queue
    try:
        state = load_hub_state()
        if state.get("last_report"):
            last_completion_report = state["last_report"]
        if state.get("logs"):
            logs_queue = list(state["logs"])[-150:]
    except Exception:
        pass


_bootstrap_from_persistence()


def add_log(msg):
    timestamp = datetime.now().strftime("%H:%M:%S")
    formatted_msg = f"[{timestamp}] {msg}"
    _safe_console_print(formatted_msg)
    logs_queue.append(formatted_msg)
    if len(logs_queue) > 150:
        logs_queue.pop(0)
    if is_serverless() and len(logs_queue) % 5 == 0:
        try:
            state = load_hub_state()
            state["logs"] = logs_queue[-100:]
            save_hub_state(state)
        except Exception:
            pass


def _safe_console_print(text: str) -> None:
    """cp949 콘솔에서도 UnicodeEncodeError 없이 출력."""
    stream = sys.stdout
    encoding = (
        getattr(stream, "encoding", None)
        or locale.getpreferredencoding(False)
        or "utf-8"
    )
    try:
        print(text)
    except UnicodeEncodeError:
        safe = text.encode(encoding, errors="backslashreplace").decode(encoding, errors="replace")
        try:
            print(safe)
        except Exception:
            # stdout 자체가 비정상일 때 최후 수단으로 stderr 사용
            try:
                sys.stderr.write(safe + "\n")
            except Exception:
                pass


def scheduler_loop():
    global scheduler_running, last_completion_report
    add_log("🚀 순위 추적 스케줄러가 시작되었습니다.")
    cycle = 0

    while not rank_stop_event.is_set():
        cycle += 1
        config = load_config()
        interval = max(5, int(config.get("track_interval_minutes", 60)))

        add_log(f"🔄 [사이클 {cycle}] 순위 추적 + SEO 점검 시작")
        results = track_all_keywords(logger=add_log, serverless=is_cloud_hub())
        report = build_completion_report(results)
        last_completion_report = report
        try:
            state = load_hub_state()
            state["last_report"] = report
            state["logs"] = logs_queue[-100:]
            save_hub_state(state)
        except Exception:
            pass

        for item in report.get("items", []):
            if item.get("status") != "실패":
                add_log(f"📊 {item['keyword']}: {item.get('detail', '')}")

        add_log(f"✅ {report['summary']}")

        if cycle == 1 or cycle % 6 == 0:
            add_log("🔎 정기 SEO 체크리스트 점검 실행...")
            audit = run_full_audit(logger=add_log)
            avg = audit["summary"].get("average_score", 0)
            add_log(f"📋 SEO 평균 점수: {avg}점 (점검 {audit['summary']['audited_ok']}페이지)")

        add_log(f"😴 다음 추적까지 {interval}분 대기")
        for _ in range(interval * 6):
            if rank_stop_event.is_set():
                break
            time.sleep(10)

    scheduler_running = False
    add_log("🛑 순위 추적 스케줄러가 중지되었습니다.")


def _run_traffic_once(target_url: str, *, log_label: str = "자동", detail: str = "") -> dict | None:
    """1회 트래픽 방문 + 429 백오프 상태 저장."""
    if run_traffic_session is None:
        return None
    suffix = f" {detail}" if detail else ""
    add_log(f"🚗 {log_label} 트래픽{suffix}: {target_url}")
    try:
        result = run_traffic_session(target_url, timeout_sec=8.0)
    except Exception as exc:
        add_log(f"❌ 트래픽 실패: {exc}")
        raise

    status = result.get("status_code")
    if result.get("ok"):
        add_log(f"✅ 트래픽 OK {status} · {result.get('elapsed_sec')}초")
    else:
        note = format_backoff_note(status) if format_backoff_note else ""
        add_log(f"⚠️ 트래픽 응답 {status}{note}")

    if apply_traffic_result is not None:
        state = load_hub_state()
        apply_traffic_result(state, result)
        state["last_traffic_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        state["logs"] = logs_queue[-100:]
        save_hub_state(state)
    return result


def _reconcile_traffic_thread() -> None:
    """죽은 스레드면 traffic_loop_running 플래그 정리."""
    global traffic_loop_running
    if traffic_thread is not None and not traffic_thread.is_alive():
        traffic_loop_running = False


def _stop_traffic_loop(*, join_sec: float = 12.0) -> None:
    """트래픽 루프 중지 신호 + 짧은 join 후 플래그 정리."""
    global traffic_loop_running
    traffic_stop_event.set()
    if traffic_thread is not None and traffic_thread.is_alive():
        traffic_thread.join(timeout=join_sec)
    traffic_loop_running = False


def traffic_loop():
    """로컬 서버 — 브라우저 없이 주기적 스마트스토어 방문 (429 시 간격 자동 연장)."""
    global traffic_loop_running
    if run_traffic_session is None:
        traffic_loop_running = False
        return
    try:
        state0 = load_hub_state()
        base_iv = effective_interval_sec(state0) if effective_interval_sec else max(
            300, int(os.environ.get("TRAFFIC_INTERVAL_SEC", "1200"))
        )
        add_log(f"🚗 트래픽 루프 시작 (기본 {base_iv // 60}분 간격, 429 시 자동 연장)")

        while not traffic_stop_event.is_set():
            if not load_hub_state().get("traffic_enabled", True):
                break
            target_url, detail = _resolve_traffic_visit(advance=True)
            try:
                _run_traffic_once(target_url, log_label="자동", detail=detail)
            except Exception:
                pass

            if traffic_stop_event.is_set() or not load_hub_state().get("traffic_enabled", True):
                break

            state = load_hub_state()
            interval_sec = effective_interval_sec(state) if effective_interval_sec else max(
                300, int(os.environ.get("TRAFFIC_INTERVAL_SEC", "1200"))
            )
            if int(state.get("traffic_backoff_streak") or 0) > 0:
                add_log(f"⏳ 다음 트래픽까지 {interval_sec // 60}분 대기 (rate limit 백오프)")

            waited = 0
            while waited < interval_sec and not traffic_stop_event.is_set():
                if not load_hub_state().get("traffic_enabled", True):
                    break
                time.sleep(10)
                waited += 10

        add_log("🛑 로컬 트래픽 루프가 중지되었습니다.")
    finally:
        traffic_loop_running = False


def ensure_background_services(*, log_boot: bool = False) -> None:
    """서버 기동 시 순위·트래픽을 각각 독립적으로 시작 (탭/워크스페이스 전환과 무관)."""
    global scheduler_running, scheduler_thread, traffic_loop_running, traffic_thread
    global rank_stop_event, traffic_stop_event, _boot_auto_started

    state = load_hub_state()
    rank_on = state.get("auto_enabled", True) is not False
    traffic_on = state.get("traffic_enabled", True) is not False

    if is_cron_mode():
        if state.get("auto_enabled") is None:
            state["auto_enabled"] = True
        if state.get("traffic_enabled") is None:
            state["traffic_enabled"] = True
        save_hub_state(state)
        if log_boot:
            add_log("▶️ Vercel Cron 24시간 — 순위·트래픽 독립 제어 (기본 켜짐)")
        _boot_auto_started = True
        return

    started = False
    if rank_on and not scheduler_running:
        rank_stop_event.clear()
        scheduler_running = True
        scheduler_thread = threading.Thread(target=scheduler_loop, daemon=True)
        scheduler_thread.start()
        started = True
    elif not rank_on and log_boot:
        add_log("⏸️ 순위 추적 꺼짐 (트래픽은 traffic_enabled 기준)")

    _reconcile_traffic_thread()
    if traffic_on and run_traffic_session is not None and not traffic_loop_running:
        traffic_stop_event.clear()
        traffic_loop_running = True
        traffic_thread = threading.Thread(target=traffic_loop, daemon=True)
        traffic_thread.start()
        started = True
    elif not traffic_on and log_boot:
        add_log("⏸️ 트래픽 루프 꺼짐")

    if started and log_boot:
        plat = cloud_platform()
        if is_cloudtype():
            add_log("▶️ Cloudtype 기동 — 순위·트래픽 24시간 백그라운드 (Cron 불필요)")
        else:
            add_log("▶️ 서버 기동 — 순위·트래픽 백그라운드 (브라우저·탭 전환과 무관)")
    _boot_auto_started = started or scheduler_running or traffic_loop_running


def generate_daily_report():
    history = get_history()
    if not history:
        return "아직 순위 기록이 없습니다. '지금 추적' 버튼을 눌러 첫 기록을 만드세요."

    recent = history[-10:]
    lines = ["### 📊 일일 순위 리포트", f"- 생성: {datetime.now().strftime('%Y-%m-%d %H:%M')}", ""]
    for row in recent:
        kw = row.get("키워드", "")
        rank = row.get("순위", "-")
        change = row.get("변동", "-")
        task = row.get("작업유형", "")
        detail = row.get("상세", "")
        lines.append(f"- **{kw}**: {detail} (변동: {change}, 작업: {task})")

    audit = get_latest_audit()
    if audit:
        lines.extend([
            "",
            "### 🔎 최근 SEO 점검",
            f"- 평균 점수: {audit['summary'].get('average_score', 0)}점",
            f"- 점검 페이지: {audit['summary'].get('audited_ok', 0)}개",
        ])
        recs = audit["summary"].get("recommendations", [])[:5]
        if recs:
            lines.append("- 개선 권장:")
            for r in recs:
                lines.append(f"  - {r}")

    return "\n".join(lines)


@app.route("/")
def index():
    return render_template("index.html")


def _all_catalog_programs() -> list[dict]:
    catalog = get_catalog(workspace="all")
    return list(catalog.get("programs") or [])


@app.route("/programs")
def programs_hub():
    return render_template("programs.html")


@app.route("/program/<program_id>")
def program_ui(program_id: str):
    programs = _all_catalog_programs()
    entry = next((p for p in programs if p.get("id") == program_id), None)
    if not entry:
        abort(404)
    return render_template("program_ui.html", program_id=program_id, program_name=entry.get("name", program_id))


@app.route("/api/programs")
def api_programs_all():
    programs = _all_catalog_programs()
    return jsonify({
        "success": True,
        "count": len(programs),
        "programs": programs,
    })


@app.route("/api/program/<program_id>")
def api_program_detail(program_id: str):
    programs = _all_catalog_programs()
    entry = next((p for p in programs if p.get("id") == program_id), None)
    if not entry:
        return jsonify({"success": False, "error": "program not found", "program_id": program_id}), 404
    return jsonify({"success": True, "program": entry})


@app.route("/api/status")
def api_status():
    try:
        history = get_history()
        last_rank = None
        last_rank_keyword = None
        if history:
            last_row = history[-1]
            last_rank_keyword = (last_row.get("키워드") or "").strip() or None
            try:
                last_rank = int(last_row.get("순위", 100))
            except (TypeError, ValueError):
                last_rank = 100

        config = load_config()
        keywords = config.get("keywords") or []
        priority = config.get("priority_keywords") or []
        on_cron = is_cron_mode()
        on_cloud = is_cloud_hub()
        platform = cloud_platform()
        track_count = len(priority) if (on_cron and priority) else len(keywords)
        if on_cron and not priority:
            track_count = min(len(keywords), int(config.get("priority_track_limit") or 10))

        state = load_hub_state()
        rank_on = state.get("auto_enabled", True) is not False
        traffic_on = state.get("traffic_enabled", True) is not False
        running = scheduler_running
        if on_cron:
            running = rank_on

        _reconcile_traffic_thread()
        traffic_running = bool(traffic_on and traffic_loop_running)
        if on_cron:
            traffic_running = traffic_on

        report = last_completion_report or state.get("last_report")
        auto_mode = "cron" if on_cron else ("daemon" if is_cloudtype() else "local")
        traffic_url = _traffic_target_url()
        traffic_pool = (
            traffic_pool_summary(load_config(), state)
            if traffic_pool_summary is not None
            else {}
        )
        priority_preview = [
            {
                "keyword": (p.get("keyword") or "").strip(),
                "product_id": (p.get("product_id") or "").strip(),
            }
            for p in priority
            if (p.get("keyword") or "").strip()
        ][:12]

        return jsonify({
            "running": running,
            "traffic_running": traffic_running,
            "traffic_enabled": traffic_on,
            "rank_enabled": rank_on,
            "traffic_loop": traffic_loop_running,
            "auto_started": _boot_auto_started or running,
            "last_rank": last_rank,
            "last_rank_keyword": last_rank_keyword,
            "total_tracks": len(history),
            "keyword_count": len(keywords),
            "priority_count": len(priority) or min(len(keywords), int(config.get("priority_track_limit") or 10)),
            "track_batch_count": track_count,
            "serverless": on_cron,
            "platform": platform,
            "auto_mode": auto_mode,
            "last_cron_at": state.get("last_cron_at"),
            "last_traffic_at": state.get("last_traffic_at"),
            "traffic_target_url": traffic_url,
            "traffic_pool": traffic_pool,
            "traffic_mode": (
                f"클라우드 HTTP 방문 · 상품 URL {traffic_pool.get('traffic_pool_size', 1)}개 순환"
                if (on_cron or on_cloud) and traffic_pool.get("traffic_pool_size", 1) > 1
                else (
                    "클라우드 HTTP 방문 (상품 페이지 직접 방문 · 키워드 검색 아님)"
                    if on_cron or on_cloud
                    else "로컬 HTTP 방문 (상품 URL 순환)"
                )
            ),
            "priority_keywords": priority_preview,
            "persistence": persistence_backend(),
            "interval_minutes": config.get("track_interval_minutes", 60),
            "cron_schedule": "매시 정각 · 트래픽 20분마다 (0 * * * * / */20 * * * *)" if on_cron else None,
            "daemon_schedule": (
                f"순위 {config.get('track_interval_minutes', 60)}분 · 트래픽 {max(5, int(os.environ.get('TRAFFIC_INTERVAL_SEC', '1200')) // 60)}분"
                if auto_mode == "daemon"
                else None
            ),
            "last_report": report,
        })
    except Exception as exc:
        add_log(traceback.format_exc())
        return _json_error("/api/status", exc)


@app.route("/api/config", methods=["GET", "POST"])
def api_config():
    if request.method == "GET":
        return jsonify(load_config())
    data = request.get_json(silent=True) or {}
    config = load_config()
    for key in ("store_name", "brand", "track_interval_minutes", "keywords", "products", "product_urls", "blog_urls"):
        if key in data:
            config[key] = data[key]
    save_config(config)
    add_log("⚙️ 설정이 저장되었습니다.")
    return jsonify({"success": True, "config": config})


@app.route("/api/keywords", methods=["GET", "POST"])
def api_keywords():
    """accounts.json + config.json 키워드 (블로그·순위 추적 공용)."""
    if request.method == "GET":
        kws = keywords_from_accounts()
        config = load_config()
        if not kws:
            kws = [
                str(x.get("keyword") or "").strip()
                for x in (config.get("priority_keywords") or [])
                if isinstance(x, dict) and (x.get("keyword") or "").strip()
            ]
        return jsonify({"keywords": kws, "keywords_text": "\n".join(kws), "count": len(kws)})

    data = request.get_json(silent=True) or {}
    raw = data.get("keywords_text")
    if raw is None:
        raw = data.get("keywords", "")
    if isinstance(raw, list):
        kws = parse_keywords_text(", ".join(str(x) for x in raw))
    else:
        kws = parse_keywords_text(str(raw or ""))

    save_accounts_keywords(kws)
    config = load_config()
    if kws:
        config = merge_keywords_into_config(config, kws)
    else:
        config["priority_keywords"] = []
    save_config(config)
    add_log(f"🔑 키워드 {len(kws)}개 저장 (accounts.json + config.json)")
    return jsonify({"success": True, "keywords": kws, "count": len(kws)})


@app.route("/api/track-now", methods=["POST"])
def api_track_now():
    global last_completion_report
    add_log("📱 수동 순위 추적 요청")
    results = track_all_keywords(logger=add_log, serverless=is_serverless())
    report = build_completion_report(results)
    last_completion_report = report
    try:
        state = load_hub_state()
        state["last_report"] = report
        save_hub_state(state)
    except Exception:
        pass
    add_log(f"✅ {report['summary']}")
    return jsonify({"success": True, "report": report})


@app.route("/api/seo-audit", methods=["POST"])
def api_seo_audit():
    add_log("📱 SEO 체크리스트 점검 요청")
    data = request.get_json(silent=True) or {}
    limit = data.get("product_limit")
    try:
        product_limit = int(limit) if limit is not None else None
    except (TypeError, ValueError):
        product_limit = None
    audit = run_full_audit(logger=add_log, product_limit=product_limit)
    total = audit["summary"].get("product_total")
    sampled = audit["summary"].get("product_limit")
    if total and sampled and total > sampled:
        add_log(f"📋 상품 SEO: 우선 {sampled}개 점검 (전체 {total}개 — 네이버 차단 방지)")
    add_log(f"📋 SEO 평균 점수: {audit['summary'].get('average_score', 0)}점")
    return jsonify({"success": True, "audit": audit})


@app.route("/api/seo-audit/latest")
def api_seo_audit_latest():
    audit = get_latest_audit()
    return jsonify({"audit": audit})


def _parse_scope(body: dict | None, default: str) -> str:
    scope = (body or {}).get("scope", default).strip().lower()
    if scope not in ("rank", "traffic", "all"):
        return default
    return scope


@app.route("/api/start", methods=["POST"])
def api_start():
    global scheduler_running, scheduler_thread, traffic_loop_running, traffic_thread
    global rank_stop_event, traffic_stop_event
    body = request.get_json(silent=True) or {}
    scope = _parse_scope(body, "all")

    state = load_hub_state()
    if scope in ("rank", "all"):
        state["auto_enabled"] = True
    if scope in ("traffic", "all"):
        state["traffic_enabled"] = True
    save_hub_state(state)

    if is_serverless():
        add_log(f"▶️ Cron 활성화 (scope={scope})")
        return jsonify({
            "success": True,
            "message": "24시간 Cron이 켜졌습니다. JARVIS 탭을 봐도 트래픽은 백그라운드에서 계속됩니다.",
            "mode": "cron",
            "scope": scope,
        })

    if scope in ("rank", "all"):
        rank_stop_event.clear()
    if scope in ("traffic", "all"):
        traffic_stop_event.clear()
    ensure_background_services()

    ok = (scope in ("traffic", "all") and traffic_loop_running) or (
        scope in ("rank", "all") and scheduler_running
    ) or (scope == "all" and (scheduler_running or traffic_loop_running))
    if ok:
        add_log(f"▶️ 시작 (scope={scope})")
        return jsonify({"success": True, "message": "백그라운드 작업이 실행 중입니다.", "scope": scope})
    return jsonify({"success": False, "message": "시작에 실패했습니다.", "scope": scope})


@app.route("/api/stop", methods=["POST"])
def api_stop():
    global scheduler_running, traffic_loop_running
    global rank_stop_event, traffic_stop_event
    body = request.get_json(silent=True) or {}
    scope = _parse_scope(body, "rank")

    state = load_hub_state()
    if scope in ("rank", "all"):
        state["auto_enabled"] = False
        rank_stop_event.set()
    if scope in ("traffic", "all"):
        state["traffic_enabled"] = False
        if not is_serverless():
            _stop_traffic_loop()
        else:
            traffic_stop_event.set()
    save_hub_state(state)

    if is_serverless():
        if scope == "traffic":
            msg = "트래픽 Cron이 꺼졌습니다. 순위 추적 Cron은 유지됩니다."
        elif scope == "rank":
            msg = "순위 Cron이 꺼졌습니다. 트래픽 Cron은 계속 동작합니다."
        else:
            msg = "순위·트래픽 Cron이 모두 꺼졌습니다."
        add_log(f"⏸️ Cron 중지 (scope={scope})")
        return jsonify({"success": True, "message": msg, "mode": "cron", "scope": scope})

    if scope == "traffic":
        add_log("⏸️ 트래픽 루프 중지 (순위 추적 유지)")
        return jsonify({"success": True, "message": "트래픽이 중지되었습니다. 순위 추적은 계속됩니다.", "scope": scope})
    if scope == "rank" and scheduler_running:
        add_log("⏸️ 순위 추적 중지 (트래픽 유지)")
        return jsonify({"success": True, "message": "순위 추적만 중지했습니다. 트래픽은 계속됩니다.", "scope": scope})
    if scope == "all" and (scheduler_running or traffic_loop_running):
        add_log("⏸️ 순위·트래픽 모두 중지")
        return jsonify({"success": True, "message": "순위·트래픽이 모두 중지됩니다.", "scope": scope})
    return jsonify({"success": True, "message": "중지 상태로 저장했습니다.", "scope": scope})


@app.route("/api/logs")
def api_logs():
    return jsonify({"logs": logs_queue})


@app.route("/api/history")
def api_history():
    return jsonify(get_history())


@app.route("/api/report")
def api_report():
    return jsonify({"report": generate_daily_report()})


@app.route("/api/completion")
def api_completion():
    return jsonify({"report": last_completion_report})


@app.route("/api/keyword/analyze", methods=["POST"])
def api_keyword_analyze():
    data = request.get_json(silent=True) or {}
    keyword = data.get("keyword", "")
    product_id = data.get("product_id")
    result = analyze_keyword(keyword, product_id=product_id)
    if result.get("success"):
        add_log(f"🔑 키워드 분석: {keyword} — {result.get('opportunity_score')}점")
    return jsonify(result)


@app.route("/api/keyword/suggest", methods=["POST"])
def api_keyword_suggest():
    data = request.get_json(silent=True) or {}
    name = data.get("product_name", "퍼마코트")
    suggestions = suggest_keywords_for_product(name)
    return jsonify({"success": True, "suggestions": suggestions})


@app.route("/api/product/rank", methods=["POST"])
def api_product_rank():
    data = request.get_json(silent=True) or {}
    keyword = data.get("keyword", "")
    product_id = data.get("product_id", "")
    rank, status = check_product_rank(keyword, product_id)
    if status == "blocked":
        return jsonify({
            "success": False,
            "rank": None,
            "display": "네이버 차단 (403)",
            "blocked": True,
        })
    display = f"{rank}위" if rank and rank < 100 else "100위 밖"
    return jsonify({"success": rank is not None, "rank": rank, "display": display})


@app.route("/api/content/workflows")
def api_content_workflows():
    return jsonify({"workflows": list_workflows()})


@app.route("/api/content/generate", methods=["POST"])
def api_content_generate():
    data = request.get_json(silent=True) or {}
    result = generate_content(
        data.get("workflow", "product_detail"),
        data.get("keyword", ""),
        data.get("product_name"),
        data.get("brand"),
    )
    if result.get("success"):
        try:
            path = save_content(result, data.get("product_id"))
            result["saved_path"] = path
        except OSError as exc:
            result["saved_path"] = None
            result["save_warning"] = str(exc)
        add_log(f"📝 콘텐츠 생성: {result.get('workflow_label')}")
    return jsonify(result)


@app.route("/manifest.json")
def manifest():
    return send_from_directory("static", "manifest.json")


@app.route("/sw.js")
def service_worker():
    return send_from_directory("static", "sw.js")


@app.route("/openapi.json")
def openapi_spec():
    return send_from_directory(".", "openapi.json")


def _cron_authorized() -> bool:
    secret = os.environ.get("CRON_SECRET", "").strip()
    if not secret:
        return True
    auth = request.headers.get("Authorization", "")
    if auth == f"Bearer {secret}":
        return True
    # Vercel Cron 내장 헤더 (CRON_SECRET 미전달 환경 대비)
    if request.headers.get("x-vercel-cron") == "1":
        return True
    return False


def _webhook_authorized() -> bool:
    secret = os.environ.get("WEBHOOK_SECRET", "").strip()
    if not secret:
        return True
    auth = request.headers.get("Authorization", "")
    if auth == f"Bearer {secret}":
        return True
    return request.headers.get("X-Webhook-Secret") == secret


def _traffic_target_url(*, peek: bool = True) -> str:
    """다음 방문 URL (peek=True면 인덱스만 조회, 실제 방문 시 advance)."""
    url, _ = _resolve_traffic_visit(advance=not peek)
    return url


def _resolve_traffic_visit(*, advance: bool) -> tuple[str, str]:
    """방문 URL + 로그용 라벨 (예: '(3/9 퍼마코트)')."""
    explicit = os.environ.get("TRAFFIC_TARGET_URL", "").strip()
    if explicit:
        return explicit, ""

    config = load_config()
    if pick_traffic_url is None:
        products = config.get("products") or []
        for product in products:
            url = (product or {}).get("url", "")
            if url:
                return url, ""
        store = (config.get("store_name") or "nanumlab").replace(" ", "")
        return f"https://smartstore.naver.com/{store}", ""

    state = load_hub_state()
    url, new_state = pick_traffic_url(config, dict(state), advance=advance)
    if advance:
        save_hub_state(new_state)

    candidates = collect_traffic_urls(config) if collect_traffic_urls else [url]
    n = len(candidates)
    try:
        idx = candidates.index(url) + 1
    except ValueError:
        idx = 1
    label = label_for_url(config, url) if label_for_url else url
    detail = f"({idx}/{n} {label})" if n > 1 else f"({label})"
    return url, detail


@app.route("/api/health", methods=["GET"])
@app.route("/api/traffic/health", methods=["GET"])
def api_health():
    return jsonify({
        "status": "healthy",
        "serverless": is_cron_mode(),
        "platform": cloud_platform(),
        "persistence": persistence_backend(),
        "traffic_available": run_traffic_session is not None,
        "auto_mode": "cron" if is_cron_mode() else ("daemon" if is_cloudtype() else "local"),
        "scheduler_running": scheduler_running,
        "traffic_loop_running": traffic_loop_running,
        "traffic_enabled": load_hub_state().get("traffic_enabled", True),
        "traffic_interval_sec": (
            effective_interval_sec(load_hub_state()) if effective_interval_sec else None
        ),
        "programs_engine": "cloud-fallback-v2",
    })


@app.route("/api/traffic", methods=["POST"])
def api_traffic():
    if not _webhook_authorized():
        return jsonify({"success": False, "error": "unauthorized"}), 401
    if run_traffic_session is None:
        return jsonify({"success": False, "error": "traffic_session 미설치"}), 500

    data = request.get_json(silent=True) or {}
    explicit = (data.get("target_url") or "").strip()
    if explicit:
        target_url, detail = explicit, ""
    else:
        target_url, detail = _resolve_traffic_visit(advance=True)
    timeout_sec = min(float(data.get("timeout_sec") or 8), 9.0)

    add_log(f"🚗 클라우드 트래픽: {target_url}")
    try:
        result = _run_traffic_once(target_url, log_label="클라우드", detail=detail)
    except ValueError as exc:
        return jsonify({"success": False, "error": str(exc)}), 400
    except Exception as exc:
        add_log(f"❌ 트래픽 실패: {exc}")
        return jsonify({"success": False, "error": str(exc)}), 500

    if result is None:
        return jsonify({"success": False, "error": "traffic_session 미설치"}), 500

    if is_serverless():
        state = load_hub_state()
        state["logs"] = logs_queue[-100:]
        save_hub_state(state)

    return jsonify({"success": bool(result.get("ok")), "result": result, "target_url": target_url})


@app.route("/api/cron/traffic", methods=["GET", "POST"])
def api_cron_traffic():
    """Vercel Cron — 주기적 스마트스토어 httpx 방문."""
    if not _cron_authorized():
        return jsonify({"success": False, "error": "unauthorized"}), 401

    state = load_hub_state()
    if not state.get("traffic_enabled", True):
        add_log("⏭️ 트래픽 Cron 건너뜀 (traffic_enabled 꺼짐)")
        return jsonify({"success": True, "skipped": True, "reason": "traffic_disabled"})

    if run_traffic_session is None:
        return jsonify({"success": False, "error": "traffic_session 미설치"}), 500

    target_url, detail = _resolve_traffic_visit(advance=True)
    try:
        result = _run_traffic_once(target_url, log_label="Cron", detail=detail)
    except Exception as exc:
        add_log(f"❌ Cron 트래픽 실패: {exc}")
        return jsonify({"success": False, "error": str(exc)}), 500

    if result is None:
        return jsonify({"success": False, "error": "traffic_session 미설치"}), 500

    state = load_hub_state()
    state["logs"] = logs_queue[-100:]
    save_hub_state(state)
    add_log(f"✅ Cron 트래픽 완료 ({result.get('status_code')})")
    return jsonify({"success": True, "result": result, "target_url": target_url})


@app.route("/api/cron/track", methods=["GET", "POST"])
def api_cron_track():
    """Vercel Cron — 매시 우선 키워드 순위 추적."""
    if not _cron_authorized():
        return jsonify({"success": False, "error": "unauthorized"}), 401

    state = load_hub_state()
    if not state.get("auto_enabled", True):
        add_log("⏭️ Cron 건너뜀 (자동 추적 꺼짐)")
        return jsonify({"success": True, "skipped": True, "reason": "auto_disabled"})

    global last_completion_report
    config = load_config()
    priority = config.get("priority_keywords") or config.get("keywords") or []
    batch_size = int(config.get("cron_batch_size") or 4)
    offset = int(state.get("cron_keyword_offset") or 0)

    add_log("⏰ Cron 순위 추적 시작 (우선 키워드)")
    results = track_all_keywords(
        logger=add_log,
        serverless=True,
        keyword_offset=offset,
        keyword_batch_size=batch_size,
    )
    if priority:
        state["cron_keyword_offset"] = (offset + batch_size) % max(1, len(priority))
    report = build_completion_report(results)
    last_completion_report = report
    state["last_cron_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    state["last_report"] = report
    state["logs"] = logs_queue[-100:]
    save_hub_state(state)
    add_log(f"✅ Cron 완료: {report['summary']}")
    return jsonify({
        "success": True,
        "report": report,
        "tracked": len(results),
        "persistence": persistence_backend(),
    })


@app.route("/api/javis/programs")
def api_javis_programs():
    workspace = (request.args.get("workspace") or "all").strip().lower()
    return jsonify(get_catalog(workspace=workspace))


@app.route("/api/javis/launch", methods=["POST"])
def api_javis_launch():
    try:
        data = request.get_json(silent=True) or {}
        program_id = (data.get("id") or data.get("program_id") or "").strip()
        if not program_id:
            return jsonify({"success": False, "error": "program id 필요"}), 400
        result = launch_program(program_id, logger=add_log)
        if result.get("success"):
            mode = "클라우드" if result.get("cloud") else "로컬"
            add_log(f"🚀 JARVIS 프로그램 ({mode}): {program_id}")
        else:
            add_log(f"⚠️ 프로그램 실행 실패: {result.get('error', program_id)}")
        return jsonify(result)
    except Exception as exc:
        add_log(traceback.format_exc())
        return _json_error("/api/javis/launch", exc)


if os.environ.get("AUTO_START_SCHEDULER", "1") != "0":
    try:
        sync_accounts_keywords_to_config()
    except Exception:
        pass
    ensure_background_services(log_boot=True)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8000"))
    app.run(host="0.0.0.0", port=port, debug=False)
