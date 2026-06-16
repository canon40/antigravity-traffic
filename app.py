import os
import threading
import time
from datetime import datetime

from flask import Flask, jsonify, render_template, request, send_from_directory

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

app = Flask(__name__)

logs_queue = []
scheduler_running = False
scheduler_thread = None
stop_event = threading.Event()
last_completion_report = None


def add_log(msg):
    timestamp = datetime.now().strftime("%H:%M:%S")
    formatted_msg = f"[{timestamp}] {msg}"
    print(formatted_msg)
    logs_queue.append(formatted_msg)
    if len(logs_queue) > 150:
        logs_queue.pop(0)


def scheduler_loop():
    global scheduler_running, last_completion_report
    add_log("🚀 순위 추적 스케줄러가 시작되었습니다.")
    cycle = 0

    while not stop_event.is_set():
        cycle += 1
        config = load_config()
        interval = max(5, int(config.get("track_interval_minutes", 60)))

        add_log(f"🔄 [사이클 {cycle}] 순위 추적 + SEO 점검 시작")
        results = track_all_keywords(logger=add_log)
        report = build_completion_report(results)
        last_completion_report = report

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
            if stop_event.is_set():
                break
            time.sleep(10)

    scheduler_running = False
    add_log("🛑 순위 추적 스케줄러가 중지되었습니다.")


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


@app.route("/api/status")
def api_status():
    history = get_history()
    last_rank = None
    if history:
        try:
            last_rank = int(history[-1].get("순위", 100))
        except (TypeError, ValueError):
            last_rank = 100

    config = load_config()
    keywords = config.get("keywords") or []
    priority = config.get("priority_keywords") or []
    on_vercel = bool(os.environ.get("VERCEL"))
    track_count = len(priority) if (on_vercel and priority) else len(keywords)
    if on_vercel and not priority:
        track_count = min(len(keywords), int(config.get("priority_track_limit") or 10))

    return jsonify({
        "running": scheduler_running,
        "last_rank": last_rank,
        "total_tracks": len(history),
        "keyword_count": len(keywords),
        "priority_count": len(priority) or min(len(keywords), int(config.get("priority_track_limit") or 10)),
        "track_batch_count": track_count,
        "serverless": on_vercel,
        "interval_minutes": config.get("track_interval_minutes", 60),
        "last_report": last_completion_report,
    })


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


@app.route("/api/track-now", methods=["POST"])
def api_track_now():
    global last_completion_report
    add_log("📱 수동 순위 추적 요청")
    results = track_all_keywords(logger=add_log)
    report = build_completion_report(results)
    last_completion_report = report
    add_log(f"✅ {report['summary']}")
    return jsonify({"success": True, "report": report})


@app.route("/api/seo-audit", methods=["POST"])
def api_seo_audit():
    add_log("📱 SEO 체크리스트 점검 요청")
    audit = run_full_audit(logger=add_log)
    add_log(f"📋 SEO 평균 점수: {audit['summary'].get('average_score', 0)}점")
    return jsonify({"success": True, "audit": audit})


@app.route("/api/seo-audit/latest")
def api_seo_audit_latest():
    audit = get_latest_audit()
    return jsonify({"audit": audit})


@app.route("/api/start", methods=["POST"])
def api_start():
    global scheduler_running, scheduler_thread, stop_event
    if not scheduler_running:
        stop_event.clear()
        scheduler_running = True
        scheduler_thread = threading.Thread(target=scheduler_loop, daemon=True)
        scheduler_thread.start()
        add_log("▶️ 자동 순위 추적을 시작했습니다.")
        return jsonify({"success": True, "message": "자동 순위 추적이 시작되었습니다."})
    return jsonify({"success": False, "message": "이미 실행 중입니다."})


@app.route("/api/stop", methods=["POST"])
def api_stop():
    global scheduler_running, stop_event
    if scheduler_running:
        stop_event.set()
        add_log("⏸️ 자동 추적 중지 요청")
        return jsonify({"success": True, "message": "중지 명령이 전달되었습니다."})
    return jsonify({"success": False, "message": "실행 중이 아닙니다."})


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
    rank = check_product_rank(keyword, product_id)
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
        path = save_content(result, data.get("product_id"))
        result["saved_path"] = path
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


@app.route("/api/cron/track", methods=["GET", "POST"])
def api_cron_track():
    """Vercel Cron — 우선 키워드만 순위 추적."""
    secret = os.environ.get("CRON_SECRET", "")
    if secret:
        auth = request.headers.get("Authorization", "")
        if auth != f"Bearer {secret}":
            return jsonify({"success": False, "error": "unauthorized"}), 401
    global last_completion_report
    add_log("⏰ Cron 순위 추적 시작 (우선 키워드)")
    results = track_all_keywords(logger=add_log, serverless=True)
    report = build_completion_report(results)
    last_completion_report = report
    add_log(f"✅ Cron 완료: {report['summary']}")
    return jsonify({"success": True, "report": report, "tracked": len(results)})
def api_javis_programs():
    return jsonify(get_catalog())


@app.route("/api/javis/launch", methods=["POST"])
def api_javis_launch():
    data = request.get_json(silent=True) or {}
    program_id = (data.get("id") or data.get("program_id") or "").strip()
    if not program_id:
        return jsonify({"success": False, "error": "program id 필요"}), 400
    result = launch_program(program_id)
    if result.get("success"):
        add_log(f"🚀 JARVIS/로컬 프로그램 실행: {program_id}")
    else:
        add_log(f"⚠️ 프로그램 실행 실패: {result.get('error', program_id)}")
    return jsonify(result)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
