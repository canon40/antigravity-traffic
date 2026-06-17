# -*- coding: utf-8 -*-
"""
평일(월~금) 블로그 일과:
  1) hymini1 · hymini11 · 티스토리 글 1편 발행
  2) 네이버 계정끼리 서로이웃 신청
  3) 상대 최신 글에 답글
  4) 티스토리 피드 구독·댓글 (선택)

실행: python blog_daily_weekday.py
      python blog_daily_weekday.py --force
Windows 작업 스케줄러: run_daily_weekday.bat (평일 오전 9시 등)
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

_ROOT = Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
os.chdir(_ROOT)

ROUTINE_PATH = _ROOT / "data" / "daily_weekday_routine.json"
STATE_PATH = _ROOT / "data" / "daily_weekday_state.json"
ACCOUNTS_PATH = _ROOT / "accounts.json"
LOG_PATH = _ROOT / "data" / "daily_weekday.log"


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


def save_state(payload: dict) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def is_weekday(cfg: dict) -> bool:
    if not cfg.get("weekdays_only", True):
        return True
    allowed = cfg.get("weekday_range") or [0, 1, 2, 3, 4]
    return datetime.now().weekday() in allowed


def already_ran_today(force: bool) -> bool:
    if force:
        return False
    st = load_json(STATE_PATH)
    today = datetime.now().strftime("%Y-%m-%d")
    if st.get("date") == today and st.get("completed"):
        return True
    return False


def cred(account_data: dict, id_key: str, pw_key: str) -> tuple[str, str]:
    return (
        (account_data.get(id_key) or "").strip(),
        (account_data.get(pw_key) or "").strip(),
    )


def _build_post_payload(account_data: dict, routine: dict, round_cfg: dict | None) -> dict:
    """라운드 설정을 accounts.json 발행용 payload에 반영."""
    from blog_constants import PRODUCT_KEYWORDS, PRODUCT_POST_TYPE
    from blog_content_gen import apply_product_choice

    post_cfg = routine.get("post") or {}
    payload = dict(account_data)
    rnd = round_cfg or {}

    if rnd:
        choice = (rnd.get("product_choice") or "auto").strip().lower()
        payload["product_choice"] = choice
        payload["post_type"] = (rnd.get("post_type") or PRODUCT_POST_TYPE.get(choice, "자동차 정보")).strip()
        payload["keywords"] = rnd.get("keywords") or PRODUCT_KEYWORDS.get(choice, [])
        if rnd.get("product_url"):
            payload["product_url"] = rnd["product_url"]
        payload["use_naver1"] = bool(rnd.get("use_naver1", post_cfg.get("use_naver1", True)))
        payload["use_naver2"] = bool(rnd.get("use_naver2", post_cfg.get("use_naver2", True)))
        payload["use_tistory"] = bool(rnd.get("use_tistory", post_cfg.get("use_tistory", True)))
    else:
        payload["use_naver1"] = bool(post_cfg.get("use_naver1", True))
        payload["use_naver2"] = bool(post_cfg.get("use_naver2", True))
        payload["use_tistory"] = bool(post_cfg.get("use_tistory", True))

    payload["count"] = int(rnd.get("count", post_cfg.get("count", 1)))
    payload["gap"] = int(rnd.get("gap_minutes", post_cfg.get("gap_minutes", 1)))
    payload["use_google"] = bool(post_cfg.get("use_google", False))
    apply_product_choice(payload)
    kws = payload.get("keywords")
    if isinstance(kws, list):
        payload["keywords"] = ", ".join(str(x).strip() for x in kws if str(x).strip())
    return payload


def _run_one_post_session(py: Path, session_script: Path, label: str) -> bool:
    log(f"📝 글쓰기·발행: {label}")
    r = subprocess.run(
        [str(py), str(session_script)],
        cwd=str(_ROOT),
        capture_output=False,
    )
    ok = r.returncode == 0
    log(f"   {'✅' if ok else '⚠️'} {label} — 종료 코드 {r.returncode}")
    return ok


def run_posting(account_data: dict, routine: dict) -> bool:
    """GUI 없이 발행 (_run_blog_session.py). post_rounds 가 있으면 라운드별 실행."""
    post_cfg = routine.get("post") or {}
    session_script = _ROOT / "_run_blog_session.py"
    if not session_script.is_file():
        log("❌ _run_blog_session.py 없음")
        return False

    py = _ROOT / ".venv" / "Scripts" / "python.exe"
    if not py.is_file():
        py = Path(sys.executable)

    rounds = routine.get("post_rounds") or []
    if not rounds:
        payload = _build_post_payload(account_data, routine, None)
        ACCOUNTS_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return _run_one_post_session(py, session_script, "hymini1 / hymini11 / 티스토리")

    log(f"📝 퍼마코트 글 {len(rounds)}라운드 발행 시작 (hymini1 / hymini11 / 티스토리)")
    all_ok = True
    pause = int((routine.get("delays") or {}).get("between_steps_seconds", 30))
    for idx, rnd in enumerate(rounds, start=1):
        name = (rnd.get("name") or f"라운드 {idx}").strip()
        payload = _build_post_payload(account_data, routine, rnd)
        ACCOUNTS_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        ok = _run_one_post_session(py, session_script, f"[{idx}/{len(rounds)}] {name}")
        all_ok = all_ok and ok
        if idx < len(rounds) and pause > 0:
            log(f"   ⏳ 다음 라운드까지 {pause}초 대기…")
            time.sleep(pause)

    log("✅ 전체 라운드 발행 완료" if all_ok else "⚠️ 일부 라운드 발행 실패")
    return all_ok


def run_cross_neighbors(account_data: dict, routine: dict) -> None:
    from blog_cross_neighbor import run_cross_neighbor_sync

    accounts = routine.get("accounts") or {}
    neighbor_msg = (routine.get("neighbor_message") or "").strip()
    replies = [m.strip() for m in (routine.get("reply_messages") or []) if m.strip()]
    delays = routine.get("delays") or {}
    min_d = float(delays.get("neighbor_min", 4))
    max_d = float(delays.get("neighbor_max", 9))

    cross_n = routine.get("cross_neighbors") or []
    cross_c = routine.get("cross_comments") or []

    by_actor_neighbors: dict[str, list[str]] = {}
    by_actor_comments: dict[str, list[str]] = {}
    tistory_sub_map: dict[str, list[str]] = dict(routine.get("tistory_subscribe_by_actor") or {})
    for row in cross_n:
        by_actor_neighbors.setdefault(row["from_blog"], []).append(row["to_blog"])
    for row in cross_c:
        by_actor_comments.setdefault(row["actor_blog"], []).append(row["target_blog"])

    for key in ("naver1", "naver2"):
        acc = accounts.get(key) or {}
        blog_id = (acc.get("blog_id") or "").strip()
        if not blog_id:
            continue
        nid, npw = cred(account_data, acc.get("id_key", ""), acc.get("pw_key", ""))
        if not nid or not npw:
            log(f"⚠️ {key} 계정 정보 없음 — 스킵")
            continue
        n_targets = by_actor_neighbors.get(blog_id, [])
        c_targets = by_actor_comments.get(blog_id, [])
        if not n_targets and not c_targets:
            continue
        t_sub = [u.strip() for u in (tistory_sub_map.get(blog_id) or []) if str(u).strip()]
        log(f"🤝 [{blog_id}] 서로이웃·답글·티스토리 구독 작업")
        run_cross_neighbor_sync(
            nid,
            npw,
            blog_id,
            n_targets,
            c_targets,
            neighbor_msg,
            replies,
            log,
            min_d,
            max_d,
            t_sub or None,
        )
        pause = int(delays.get("between_steps_seconds", 30))
        if pause > 0:
            log(f"   ⏳ 다음 계정까지 {pause}초 대기…")
            time.sleep(pause)


def run_tistory_feed(account_data: dict, routine: dict) -> None:
    after = routine.get("after_post") or {}
    if not after.get("run_tistory_feed", True):
        return
    acc = (routine.get("accounts") or {}).get("tistory") or {}
    tid, tpw = cred(account_data, acc.get("id_key", "tistory_id"), acc.get("pw_key", "tistory_pw"))
    if not tid or not tpw:
        log("⚠️ 티스토리 계정 없음 — 피드 댓글 스킵")
        return

    from tistory_visit import run_tistory_neighbor_comment

    delays = routine.get("delays") or {}
    max_actions = int(after.get("tistory_max_actions", 10))
    replies = [m.strip() for m in (routine.get("reply_messages") or []) if m.strip()]

    log("📌 티스토리 구독·댓글 (피드)")
    import asyncio

    if sys.platform == "win32":
        try:
            asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
        except Exception:
            pass
    asyncio.run(
        run_tistory_neighbor_comment(
            tid,
            tpw,
            logger=log,
            max_actions=max_actions,
            min_delay=float(delays.get("neighbor_min", 4)),
            max_delay=float(delays.get("neighbor_max", 9)),
            messages=replies or None,
        )
    )


def run_daily_weekday(
    *,
    force: bool = False,
    post_only: bool = False,
    neighbor_only: bool = False,
) -> int:
    routine = load_json(ROUTINE_PATH)
    if not routine.get("enabled", True):
        log("평일 일과가 비활성화되어 있습니다 (daily_weekday_routine.json).")
        return 0

    if not is_weekday(routine):
        log("오늘은 주말입니다. 평일(월~금)에만 실행됩니다. --force 로 무시 가능.")
        if not force:
            return 0

    if already_ran_today(force) and not neighbor_only:
        log("오늘 평일 일과가 이미 완료되었습니다. --force 로 다시 실행하세요.")
        return 0

    account_data = load_json(ACCOUNTS_PATH)
    if not account_data:
        log("❌ accounts.json 이 없습니다. GUI 설정 탭에서 저장하세요.")
        return 1

    log("=== 평일 블로그 일과 시작 ===")
    post_ok = True
    if not neighbor_only:
        post_ok = run_posting(account_data, routine)
        pause = int((routine.get("delays") or {}).get("between_steps_seconds", 30))
        if pause > 0 and (routine.get("after_post") or {}).get("run_cross_neighbor", True):
            log(f"   ⏳ 서로이웃·답글 전 {pause}초 대기…")
            time.sleep(pause)

    if not post_only and (routine.get("after_post") or {}).get("run_cross_neighbor", True):
        run_cross_neighbors(account_data, routine)

    if not post_only and not neighbor_only:
        run_tistory_feed(account_data, routine)

    save_state(
        {
            "date": datetime.now().strftime("%Y-%m-%d"),
            "completed": post_ok,
            "weekday": datetime.now().weekday(),
            "finished_at": datetime.now().isoformat(timespec="seconds"),
        }
    )
    log("=== 평일 블로그 일과 종료 ===")

    try:
        from vercel_traffic_client import load_vercel_config, trigger_traffic

        vcfg = load_vercel_config(ACCOUNTS_PATH)
        if vcfg.get("vercel_enabled"):
            target = (vcfg.get("product_url") or "").strip()
            if target:
                log(f"☁️ 평일 일과 후 Vercel 트래픽: {target}")
                outcome = trigger_traffic(target, config=vcfg, log=log)
                log("   ✅ Vercel 트래픽 완료" if outcome.get("ok") else f"   ⚠️ Vercel 트래픽 실패: {outcome}")
    except Exception as exc:
        log(f"   ⚠️ Vercel 트래픽 연동 생략: {exc}")

    return 0 if post_ok else 2


def main() -> int:
    p = argparse.ArgumentParser(description="평일 블로그 일과 (월~금)")
    p.add_argument("--force", action="store_true", help="주말·중복 실행 무시")
    p.add_argument("--post-only", action="store_true", help="글쓰기만")
    p.add_argument("--neighbor-only", action="store_true", help="서로이웃·답글만")
    args = p.parse_args()
    return run_daily_weekday(
        force=args.force,
        post_only=args.post_only,
        neighbor_only=args.neighbor_only,
    )


if __name__ == "__main__":
    raise SystemExit(main())
