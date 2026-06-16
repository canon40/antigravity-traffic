# -*- coding: utf-8 -*-
"""
평일(월~금) 통합 업무 자동화:
  1) 퍼마코트 자동차 · 바이크 · 리빙코트 블로그 발행
  2) 서로이웃·답글·티스토리
  3) 네이버 이웃 새글 공감/댓글 (양 계정)
  4) 인스타 DM 오늘 팩 생성
  5) 오늘 할 일 대시보드 HTML

실행: python blog_weekly_ops.py
      run_daily_ops.bat
Windows 작업 스케줄러: 평일 오전 9시 run_daily_ops.bat
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
import webbrowser
from datetime import datetime
from pathlib import Path

_ROOT = Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

ROUTINE_PATH = _ROOT / "data" / "weekly_ops_routine.json"
STATE_PATH = _ROOT / "data" / "weekly_ops_state.json"
OPS_DIR = _ROOT / "data" / "ops"
LOG_PATH = _ROOT / "data" / "weekly_ops.log"
ACCOUNTS_PATH = _ROOT / "accounts.json"
DAILY_ROUTINE = _ROOT / "data" / "daily_weekday_routine.json"


def log(msg: str) -> None:
    line = f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    try:
        print(line, flush=True)
    except UnicodeEncodeError:
        print(line.encode("cp949", errors="replace").decode("cp949"), flush=True)
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def load_json(path: Path) -> dict:
    if not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def is_weekday(cfg: dict) -> bool:
    if not cfg.get("weekdays_only", True):
        return True
    allowed = cfg.get("weekday_range") or [0, 1, 2, 3, 4]
    return datetime.now().weekday() in allowed


def _task_applies_today(task: dict, weekday: int) -> bool:
    days = task.get("days")
    if days == "daily" or days is None:
        return True
    if isinstance(days, list):
        return weekday in days
    return False


_TASK_ACTIONS: dict[str, tuple[str, str]] = {
    "ig_dm_send": ("dm", "DM 팩 만들기"),
    "blog_neighbor_check": ("blog", "블로그+서이추 실행"),
    "smartstore_check": ("link", "https://sell.smartstore.naver.com/"),
}


def build_ops_dashboard(routine: dict) -> Path:
    OPS_DIR.mkdir(parents=True, exist_ok=True)
    today = datetime.now()
    wd = today.weekday()
    wd_names = ["월", "화", "수", "목", "금", "토", "일"]
    manual = routine.get("manual_checklist") or []
    sections: dict[str, list[str]] = {}
    for t in manual:
        if not _task_applies_today(t, wd):
            continue
        cat = t.get("category") or "기타"
        hint = t.get("hint") or ""
        link = t.get("link") or ""
        tid = t.get("id") or ""
        extra = ""
        action = _TASK_ACTIONS.get(tid)
        if action:
            if action[0] == "link":
                extra = f' <button type="button" class="btn-sm" onclick="window.open(\'{action[1]}\',\'_blank\')">열기</button>'
            else:
                extra = f' <button type="button" class="btn-sm" data-run="{action[0]}">{action[1]}</button>'
        elif link:
            extra = f' <button type="button" class="btn-sm" onclick="window.open(\'{link}\',\'_blank\')">열기</button>'
        if tid == "ig_dm_send":
            extra += ' <button type="button" class="btn-sm secondary" onclick="location.href=\'dm_today.html\'">DM 화면</button>'
        if hint:
            extra += f'<div class="hint">{hint}</div>'
        sections.setdefault(cat, []).append(f"<li><strong>{t.get('title','')}</strong>{extra}</li>")

    sec_html = ""
    for cat, items in sections.items():
        sec_html += f'<h2>{cat}</h2><ul class="task-list">{"".join(items)}</ul>'

    html = f"""<!DOCTYPE html>
<html lang="ko"><head><meta charset="utf-8"/><meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>오늘 업무 — {today.strftime('%Y-%m-%d')} ({wd_names[wd]})</title>
<style>
body{{font-family:'Malgun Gothic',sans-serif;background:#f8fafc;margin:0;padding:24px;max-width:880px;}}
h1{{font-size:24px;color:#0f172a;}} h2{{font-size:18px;color:#334155;margin-top:28px;border-bottom:2px solid #e2e8f0;padding-bottom:6px;}}
ul{{line-height:1.9;padding-left:20px;}} a{{color:#2563eb;}}
.actions{{display:flex;flex-wrap:wrap;gap:10px;margin:20px 0;}}
.btn{{background:#2563eb;color:#fff;border:none;padding:12px 18px;border-radius:10px;font-size:15px;font-weight:700;cursor:pointer;}}
.btn:hover{{background:#1d4ed8;}} .btn:disabled{{opacity:.5;cursor:not-allowed;}}
.btn.secondary{{background:#0f766e;}} .btn.warn{{background:#7c3aed;}}
.btn-sm{{background:#e0e7ff;color:#1e3a8a;border:none;padding:6px 12px;border-radius:8px;font-size:13px;cursor:pointer;margin-left:6px;}}
.btn-sm.secondary{{background:#f1f5f9;color:#334155;}}
.status{{background:#0f172a;color:#e2e8f0;border-radius:12px;padding:14px 16px;margin-bottom:16px;font-size:14px;}}
.status.running{{border:2px solid #22c55e;}} .status .dot{{display:inline-block;width:8px;height:8px;border-radius:50%;background:#64748b;margin-right:8px;}}
.status.running .dot{{background:#22c55e;animation:pulse 1s infinite;}}
@keyframes pulse{{50%{{opacity:.4;}}}}
.log{{background:#020617;color:#94a3b8;border-radius:10px;padding:12px;font-family:Consolas,monospace;font-size:12px;max-height:220px;overflow:auto;white-space:pre-wrap;margin-top:12px;}}
.hint{{font-size:13px;color:#64748b;margin-top:4px;}} .nav{{margin-bottom:12px;}}
.nav a,.nav button{{display:inline-block;margin-right:8px;margin-bottom:8px;color:#2563eb;background:none;border:none;cursor:pointer;font-size:14px;text-decoration:underline;}}
</style></head>
<body>
<h1>📋 {today.strftime('%Y-%m-%d')} ({wd_names[wd]}) 업무</h1>
<div id="status" class="status"><span class="dot"></span><span id="statusText">대기 중 — 아래 버튼을 눌러 실행</span></div>
<div class="actions">
  <button type="button" class="btn" data-run="full">▶ 전체 일과 실행</button>
  <button type="button" class="btn secondary" data-run="blog">블로그 3종 + 서이추</button>
  <button type="button" class="btn secondary" data-run="neighbor">이웃 새글 댓글</button>
  <button type="button" class="btn secondary" data-run="dm">인스타 DM 팩</button>
  <button type="button" class="btn warn" data-run="force">전체 (강제 재실행)</button>
</div>
<div class="nav">
  <button type="button" onclick="location.href='dm_today.html'">인스타 DM 화면</button>
  <button type="button" onclick="window.open('http://127.0.0.1:8765/','_blank')">스마트스토어 상세 미리보기</button>
  <button type="button" onclick="window.open('https://sell.smartstore.naver.com/','_blank')">스마트스토어 센터</button>
  <button type="button" onclick="location.reload()">새로고침</button>
</div>
<h2>오늘 수동 체크</h2>
{sec_html or "<p>오늘 수동 체크 항목 없음</p>"}
<div class="log" id="logBox">로그 대기 중…</div>
<script>
const statusEl = document.getElementById('status');
const statusText = document.getElementById('statusText');
const logBox = document.getElementById('logBox');
let pollTimer = null;

function setBusy(busy, msg) {{
  document.querySelectorAll('[data-run],.btn-sm[data-run]').forEach(b => b.disabled = busy);
  statusEl.classList.toggle('running', busy);
  statusText.textContent = msg || (busy ? '실행 중…' : '대기 중');
}}

async function runTask(action) {{
  setBusy(true, '시작: ' + action);
  try {{
    const r = await fetch('/api/run/' + action, {{method:'POST'}});
    const j = await r.json();
    if (!r.ok) throw new Error(j.error || '실행 실패');
    if (action === 'dm') location.href = 'dm_today.html';
    pollStatus();
  }} catch (e) {{
    setBusy(false, '오류: ' + e.message);
    alert(e.message);
  }}
}}

document.querySelectorAll('[data-run]').forEach(btn => {{
  btn.addEventListener('click', () => runTask(btn.getAttribute('data-run')));
}});

async function pollStatus() {{
  try {{
    const r = await fetch('/api/status');
    const j = await r.json();
    if (j.log_tail) logBox.textContent = j.log_tail;
    if (j.running) {{
      setBusy(true, '실행 중: ' + (j.task || ''));
      pollTimer = setTimeout(pollStatus, 2000);
    }} else {{
      setBusy(false, j.last_error ? ('오류: ' + j.last_error) : '완료 — ' + (j.last_task || '대기'));
      if (j.last_task === 'dm') location.href = 'dm_today.html';
    }}
  }} catch (e) {{
    setBusy(false, '서버 연결 끊김 — view_daily_ops.bat 실행');
  }}
}}
pollStatus();
</script>
</body></html>"""
    out = OPS_DIR / "dashboard.html"
    out.write_text(html, encoding="utf-8")
    return out


def run_blog_pipeline(*, force: bool = False) -> int:
    from blog_daily_weekday import run_daily_weekday

    log("--- 블로그 3종 + 서이추 + 티스토리 ---")
    return run_daily_weekday(force=force, post_only=False, neighbor_only=False)


def run_dm_pack_only() -> None:
    from instagram_dm_runner import build_daily_pack

    routine = load_json(ROUTINE_PATH)
    ig_cfg = routine.get("instagram_dm") or {}
    cfg_path = _ROOT / (ig_cfg.get("config") or "data/instagram_dm_config.json")
    build_daily_pack(
        config_path=cfg_path,
        per_category=int(ig_cfg.get("per_category", 3)),
        log=log,
    )


def run_neighbor_only() -> None:
    routine = load_json(ROUTINE_PATH)
    account_data = load_json(ACCOUNTS_PATH)
    if not account_data:
        raise RuntimeError("accounts.json 없음")
    log("--- 네이버 이웃 새글 공감/댓글 ---")
    run_neighbor_visits(routine, account_data)


def run_neighbor_visits(routine: dict, account_data: dict) -> None:
    nv = routine.get("neighbor_visit") or {}
    daily = load_json(DAILY_ROUTINE)
    accounts = daily.get("accounts") or {}
    msgs = nv.get("messages") or (daily.get("reply_messages") or [])
    max_a = int(nv.get("max_actions_per_account", 15))
    min_d = float(nv.get("min_delay", 4))
    max_d = float(nv.get("max_delay", 9))

    from blog_automation_visit import run_blog_automation_for_account

    if sys.platform == "win32":
        try:
            asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
        except Exception:
            pass

    for key in ("naver1", "naver2"):
        acc = accounts.get(key) or {}
        nid = (account_data.get(acc.get("id_key", "")) or "").strip()
        npw = (account_data.get(acc.get("pw_key", "")) or "").strip()
        blog_id = acc.get("blog_id") or nid
        if not nid or not npw:
            log(f"⚠️ {key} 계정 없음 — 서이추 댓글 스킵")
            continue
        log(f"🤝 [{blog_id}] 이웃 새글 공감/댓글")
        try:
            asyncio.run(
                run_blog_automation_for_account(
                    naver_id=nid,
                    naver_pw=npw,
                    logger=log,
                    max_actions=max_a,
                    min_delay=min_d,
                    max_delay=max_d,
                    messages=msgs,
                )
            )
        except Exception as e:
            log(f"❌ [{blog_id}] 서이추 오류: {e}")
        pause = int((routine.get("delays") or {}).get("between_major_steps_seconds", 45))
        if pause > 0:
            time.sleep(pause)


def run_weekly_ops(
    *,
    force: bool = False,
    blog_only: bool = False,
    dm_only: bool = False,
    open_browser: bool = True,
) -> int:
    routine = load_json(ROUTINE_PATH)
    if not routine.get("enabled", True):
        log("weekly_ops_routine.json 비활성화")
        return 0

    if not is_weekday(routine) and not force:
        log("주말 — 평일(월~금)에만 실행. --force 로 무시")
        return 0

    today = datetime.now().strftime("%Y-%m-%d")
    st = load_json(STATE_PATH)
    if st.get("date") == today and st.get("completed") and not force and not dm_only:
        log("오늘 통합 일과가 이미 완료됨. --force 로 재실행")
        return 0

    auto = routine.get("auto") or {}
    account_data = load_json(ACCOUNTS_PATH)
    if not account_data and not dm_only:
        log("❌ accounts.json 없음 — GUI 설정 탭에서 저장")
        return 1

    log("=== 평일 통합 업무 시작 ===")
    blog_ok = True

    if not dm_only:
        if auto.get("blog_three_products") or auto.get("cross_neighbor") or auto.get("tistory_feed"):
            log("--- [1] 블로그 3종 + 서이웃 + 티스토리 ---")
            code = run_blog_pipeline(force=force)
            blog_ok = code == 0

        pause = int((routine.get("delays") or {}).get("between_major_steps_seconds", 45))
        if pause > 0 and auto.get("neighbor_visit_accounts"):
            log(f"   ⏳ 서이추 댓글 전 {pause}초 대기…")
            time.sleep(pause)

        if not blog_only and auto.get("neighbor_visit_accounts"):
            log("--- [2] 네이버 이웃 새글 공감/댓글 ---")
            run_neighbor_visits(routine, account_data)

    if not blog_only and auto.get("instagram_dm_pack"):
        log("--- [3] 인스타 DM 오늘 팩 ---")
        run_dm_pack_only()
        ig_cfg = routine.get("instagram_dm") or {}
        if ig_cfg.get("open_browser_links"):
            from instagram_dm_runner import open_dm_links

            pack = load_json(OPS_DIR / "dm_today.json")
            if pack:
                open_dm_links(pack, log=log)

    build_ops_dashboard(routine)
    log("--- [4] 대시보드 갱신 완료 ---")
    if open_browser and auto.get("open_ops_dashboard", True):
        try:
            import urllib.request

            urllib.request.urlopen("http://127.0.0.1:8770/api/status", timeout=1)
            webbrowser.open("http://127.0.0.1:8770/")
        except Exception:
            log("대시보드: view_daily_ops.bat 실행 → http://127.0.0.1:8770/")

    save_json(
        STATE_PATH,
        {
            "date": today,
            "completed": blog_ok,
            "weekday": datetime.now().weekday(),
            "finished_at": datetime.now().isoformat(timespec="seconds"),
        },
    )
    log("=== 평일 통합 업무 종료 ===")
    return 0 if blog_ok else 2


def main() -> int:
    p = argparse.ArgumentParser(description="평일 통합 업무 (블로그·DM·체크리스트)")
    p.add_argument("--force", action="store_true")
    p.add_argument("--blog-only", action="store_true", help="블로그·서이추만")
    p.add_argument("--dm-only", action="store_true", help="DM 팩·대시보드만")
    p.add_argument("--dashboard-only", action="store_true", help="대시보드 HTML만 갱신")
    args = p.parse_args()

    if args.dashboard_only:
        from ops_dashboard_server import serve_forever

        serve_forever()
        return 0

    return run_weekly_ops(force=args.force, blog_only=args.blog_only, dm_only=args.dm_only)


if __name__ == "__main__":
    raise SystemExit(main())
