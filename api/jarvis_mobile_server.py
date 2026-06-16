# -*- coding: utf-8 -*-
"""JARVIS 모바일 — FastAPI (채팅·빠른 실행·PWA 정적 파일)."""

from __future__ import annotations

import os
import socket
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parent.parent
_MOBILE = _ROOT / "mobile"
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

try:
    from dotenv import load_dotenv

    load_dotenv(_ROOT / ".env")
except ImportError:
    pass

try:
    from integrations.jarvis_env_sync import apply_to_environ, load_api_keys

    apply_to_environ(load_api_keys())
    from jarvis_ultimate_system import ensure_gemini_configured
    from integrations.jarvis_instant import ensure_ready

    ensure_gemini_configured()
    ensure_ready()
except Exception:
    pass

from fastapi import FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

MOBILE_TOKEN = (os.environ.get("JARVIS_MOBILE_TOKEN") or "").strip()
# Cloud 런타임(Cloudtype/Render 등)은 보통 PORT를 주입하므로 최우선 사용.
PORT = int(os.environ.get("PORT") or os.environ.get("JARVIS_MOBILE_PORT") or "8766")

app = FastAPI(title="JARVIS Mobile", version="1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def _check_token(authorization: str | None) -> None:
    if not MOBILE_TOKEN:
        return
    token = (authorization or "").replace("Bearer", "").strip()
    if token != MOBILE_TOKEN:
        raise HTTPException(status_code=401, detail="인증 토큰이 올바르지 않습니다.")


class ChatBody(BaseModel):
    message: str = Field(..., min_length=1, max_length=4000)


class TaskCreateBody(BaseModel):
    url: str = Field(..., min_length=3, max_length=2000)


class InstantBody(BaseModel):
    platform: str = Field(..., description="genspark | skywork | video | thumbnail | workspace")
    query: str = Field("", max_length=2000)


class PlanSyncBody(BaseModel):
    todos: list[dict[str, Any]] = Field(default_factory=list)
    weekly_plan: list[dict[str, Any]] = Field(default_factory=list)
    label: str = ""
    client_revision: str = ""


class SchedulePushBody(BaseModel):
    todos: list[dict[str, Any]] | None = None
    weekly_plan: list[dict[str, Any]] | None = None
    label: str = ""
    client_revision: str = ""


class WeeklyRowPatchBody(BaseModel):
    fields: dict[str, Any] = Field(default_factory=dict)


class CommandBody(BaseModel):
    action_key: str = Field(..., min_length=1, max_length=64)
    payload: dict[str, Any] = Field(default_factory=dict)
    source: str = "mobile"
    run_now: bool = False


class CommandTextBody(BaseModel):
    text: str = Field(..., min_length=1, max_length=4000)
    source: str = "mobile"
    run_now: bool = False


class MeetingMinutesBody(BaseModel):
    subject: str = Field("", max_length=200)
    context: str = Field("", max_length=4000)
    notes: str = Field("", max_length=4000)


class ProgramPresetBody(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    program_key: str = Field(..., min_length=1, max_length=64)
    config_json: dict[str, Any] = Field(default_factory=dict)
    preset_id: str = ""
    is_default: bool = False
    device_label: str = ""
    sort_order: int = 0


class ProgramRunBody(BaseModel):
    program_key: str = Field("canon_autoblog", max_length=64)
    preset_id: str = ""
    payload: dict[str, Any] = Field(default_factory=dict)
    source: str = "mobile"
    run_now: bool = True
    cloud_only: bool = False


class GrokVideoBody(BaseModel):
    action: str = Field("start", max_length=32)
    prompt: str = Field("", max_length=2000)
    template: str = Field("", max_length=64)
    image_path: str = Field("", max_length=500)


_plan_snapshot: dict[str, Any] = {
    "synced_at": None,
    "todos": [],
    "weekly_plan": [],
    "label": "",
}
_PLAN_PAYLOAD = Path.home() / ".jarvis" / "learning" / "plan_sync_payload.json"
_GEMINI_WEEKLY = Path.home() / ".jarvis" / "learning" / "nanum_weekly_ops_gemini.txt"


def _bootstrap_plan_snapshot() -> None:
    """PC run_nanum_weekly_ops.py --sync 가 저장한 payload를 서버 기동 시 복원."""
    global _plan_snapshot
    if not _PLAN_PAYLOAD.is_file():
        return
    try:
        import json

        data = json.loads(_PLAN_PAYLOAD.read_text(encoding="utf-8"))
        if data.get("todos") or data.get("weekly_plan"):
            _plan_snapshot = {
                "synced_at": data.get("synced_at"),
                "todos": (data.get("todos") or [])[:500],
                "weekly_plan": (data.get("weekly_plan") or [])[:200],
                "label": (data.get("label") or "")[:200],
            }
    except Exception:
        pass


_bootstrap_plan_snapshot()


def _sync_plan_snapshot_to_db() -> None:
    try:
        from integrations.carendal_schedule_db import push_snapshot

        push_snapshot(
            weekly_plan=_plan_snapshot.get("weekly_plan") or [],
            todos=_plan_snapshot.get("todos") or [],
            label=_plan_snapshot.get("label") or "",
        )
    except Exception:
        pass


def _load_plan_snapshot_from_db() -> bool:
    global _plan_snapshot
    try:
        from integrations.carendal_schedule_db import pull_snapshot

        snap = pull_snapshot()
        if not snap.get("weekly_plan") and not snap.get("todos"):
            return False
        _plan_snapshot = {
            "synced_at": snap.get("last_sync_at"),
            "todos": (snap.get("todos") or [])[:500],
            "weekly_plan": (snap.get("weekly_plan") or [])[:200],
            "label": (snap.get("label") or "")[:200],
        }
        return True
    except Exception:
        return False


_load_plan_snapshot_from_db()


def _start_carendal_workers() -> None:
    try:
        from integrations.carendal_command_runner import start_command_worker
        from integrations.carendal_schedule_db import init_db

        init_db()
        start_command_worker()
    except Exception:
        pass


_start_carendal_workers()


def _format_plan_for_prompt(max_todos: int = 30, max_routines: int = 25) -> str:
    snap = _plan_snapshot
    todos = snap.get("todos") or []
    wp = snap.get("weekly_plan") or []
    if not todos and not wp:
        _bootstrap_plan_snapshot()
        snap = _plan_snapshot
        todos = snap.get("todos") or []
        wp = snap.get("weekly_plan") or []
    extra = ""
    if _GEMINI_WEEKLY.is_file():
        try:
            raw = _GEMINI_WEEKLY.read_text(encoding="utf-8")
            extra = raw[:3500] if raw else ""
        except Exception:
            pass
    if not todos and not wp and not extra:
        return ""
    lines = ["[나눔랩 일정 · TODO/주간계획 APK 동기화]"]
    if snap.get("label"):
        lines.append(f"기간: {snap['label']}")
    if snap.get("synced_at"):
        lines.append(f"동기화: {snap['synced_at']}")
    if todos:
        lines.append("\nTODO 목록:")
        for t in todos[:max_todos]:
            mark = "✓" if t.get("done") else "○"
            task = (t.get("task") or t.get("content") or "").replace("\n", " ")[:70]
            lines.append(
                f"  {mark} {t.get('date', '')} {t.get('timeStart', '')}-{t.get('timeEnd', '')} "
                f"{task} ({t.get('division', '')})"
            )
    if wp:
        lines.append("\n주간 루틴:")
        for r in wp[:max_routines]:
            task = (r.get("content") or r.get("division") or "").replace("\n", " ")[:60]
            lines.append(
                f"  · {r.get('day', '')} {r.get('time', '')} [{r.get('status', 'planned')}] {task}"
            )
    if extra:
        lines.append("\n[주간 실무 계획 상세]\n" + extra)
    return "\n".join(lines)


def _friendly_reply(text: str) -> str:
    t = (text or "").strip()
    if not t:
        return "응답을 생성하지 못했습니다. 잠시 후 다시 시도해 주세요."
    low = t.lower()
    if "429" in t or "resource_exhausted" in low or "quota" in low:
        return (
            "AI 사용량 한도(429)에 걸렸습니다. 1~2분 후 다시 시도하거나, "
            "PC에서 JARVIS를 직접 사용해 보세요. 인증 토큰 문제는 아닙니다."
        )
    if "401" in t or "인증" in t:
        return t
    return t


def _memory_snippet() -> str:
    try:
        from memory.memory_manager import format_memory_for_prompt, load_memory

        return format_memory_for_prompt(load_memory())
    except Exception:
        return ""


def _is_meeting_request(text: str) -> bool:
    t = (text or "").strip()
    if not t:
        return False
    low = t.lower()
    if any(k in t for k in ("회의록", "미팅록", "meeting minutes", "meeting note")):
        return True
    if not any(k in t for k in ("회의", "미팅")) and "mtg" not in low:
        return False
    if any(k in t for k in ("몇 시", "몇시", "언제", "일정 알", "미리보기", "몇 개")):
        return False
    return True


def _extract_meeting_subject(text: str) -> str:
    import re

    t = (text or "").strip()
    m = re.search(r"(.{1,50}?(?:회의|미팅))", t, re.IGNORECASE)
    if m:
        return m.group(1).strip()
    m2 = re.search(r"([^\n,]{2,40})", t)
    return (m2.group(1).strip() if m2 else "회의") + " 회의"


def _generate_meeting_minutes(subject: str, context: str, notes: str = "") -> dict:
    subj = (subject or "").strip() or _extract_meeting_subject(context)
    ctx = (context or "").strip()
    extra = (notes or "").strip()
    plan_ctx = _format_plan_for_prompt(max_todos=12, max_routines=10)
    today = datetime.now().strftime("%Y-%m-%d")
    prompt = (
        "나눔랩(코팅·마케팅·영업) 업무용 회의록 초안을 작성하세요.\n"
        f"회의명: {subj}\n"
        f"오늘 날짜: {today}\n"
    )
    if ctx:
        prompt += f"사용자 입력·맥락:\n{ctx}\n"
    if extra:
        prompt += f"회의 중 메모:\n{extra}\n"
    if plan_ctx:
        prompt += f"\n{plan_ctx}\n"
    prompt += (
        "\n아래 마크다운 형식으로만 출력하세요. 모르는 항목은 [작성]으로 두세요.\n"
        f"# {subj} 회의록\n"
        "- 일시: (입력·일정에서 추론, 없으면 [작성])\n"
        "- 장소/방식: [작성]\n"
        "- 참석: [작성]\n"
        "- 안건:\n"
        "  1. [작성]\n"
        "## 논의 내용\n"
        "(입력·일정 맥락에서 추론 가능한 항목 bullet, 없으면 [작성])\n"
        "## 결정 사항\n"
        "- [작성]\n"
        "## 액션 아이템\n"
        "| 담당 | 할 일 | 기한 |\n"
        "| --- | --- | --- |\n"
        "| [작성] | [작성] | [작성] |\n"
        "\n한국어, 간결하고 실무적으로."
    )
    try:
        from jarvis_ultimate_system import JarvisUltimateDirector

        director = JarvisUltimateDirector()
        reply = director._gemini_generate(prompt, flash=True)
        return {
            "ok": True,
            "reply": _friendly_reply(str(reply)),
            "subject": subj,
            "route": "gemini+meeting_minutes",
        }
    except Exception as e:
        return {"ok": False, "error": str(e), "subject": subj}


def _handle_chat(message: str) -> dict:
    text = (message or "").strip()
    if not text:
        return {"ok": False, "error": "메시지가 비어 있습니다."}

    try:
        from integrations.carendal_command_runner import detect_action_from_text, enqueue_from_text

        detected = detect_action_from_text(text)
        if detected:
            key, _payload = detected
            queued = enqueue_from_text(text, source="mobile_chat")
            action_labels = {
                "canon_autoblog": "블로그 자동 작성",
                "weekly_sync": "주간 계획 동기화",
                "weather": "날씨 조회",
            }
            label = action_labels.get(key, key)
            return {
                "ok": True,
                "final_result": f"「{label}」작업을 PC에 등록했습니다. 곧 실행됩니다.\n(명령 ID: {queued.get('id', '')})",
                "route": f"command:{key}",
                "command_id": queued.get("id"),
            }
    except Exception:
        pass

    low = text.lower()
    if "날씨" in text or "weather" in low:
        try:
            from actions.weather_report import weather_action

            city = "서울"
            if "서울" in text:
                city = "서울"
            elif "부산" in text:
                city = "부산"
            elif "대구" in text:
                city = "대구"
            elif "인천" in text:
                city = "인천"
            r = weather_action({"city": city})
            if isinstance(r, dict) and r.get("message"):
                return {"ok": True, "final_result": str(r["message"]), "route": "weather"}
            if isinstance(r, str):
                return {"ok": True, "final_result": r, "route": "weather"}
        except Exception as e:
            return {"ok": False, "error": f"날씨 조회 실패: {e}"}

    if _is_meeting_request(text):
        result = _generate_meeting_minutes(_extract_meeting_subject(text), text)
        if result.get("ok"):
            return {
                "ok": True,
                "final_result": result.get("reply") or "",
                "route": result.get("route", "gemini+meeting_minutes"),
                "subject": result.get("subject", ""),
            }
        return result

    try:
        from agent.fast_dialogue import is_fast_chat_eligible, run_fast_dialogue

        if is_fast_chat_eligible(text):
            return run_fast_dialogue(text, memory_snippet=_memory_snippet())
    except Exception:
        pass

    platform = None
    if any(k in text for k in ("검색", "찾아줘", "조사", "search")):
        platform = "genspark"
    elif any(k in text for k in ("슬라이드", "ppt", "문서", "발표")):
        platform = "skywork"
    elif any(k in text for k in ("영상", "비디오", "유튜브", "쇼츠")):
        platform = "video"
    elif any(k in text for k in ("썸네일", "thumbnail", "SUM NAIL")):
        platform = "thumbnail"

    if platform:
        try:
            from integrations.jarvis_instant import run

            r = run(platform, text)
            if isinstance(r, dict):
                msg = r.get("message") or r.get("summary") or r.get("text") or ""
                if not msg and r.get("ok"):
                    msg = "작업을 시작했습니다. PC에서 결과를 확인하세요."
                if not msg and r.get("error"):
                    msg = str(r["error"])
                return {
                    "ok": bool(r.get("ok", True)),
                    "final_result": msg or str(r)[:2000],
                    "route": platform,
                    "detail": r,
                }
        except Exception as e:
            return {"ok": False, "error": str(e), "route": platform}

    try:
        from jarvis_ultimate_system import JarvisUltimateDirector

        plan_ctx = _format_plan_for_prompt(max_todos=15, max_routines=12)
        director = JarvisUltimateDirector()
        prompt = (
            (plan_ctx + "\n\n" if plan_ctx else "")
            + f"[모바일 JARVIS · Gemini]\n사용자: {text}\n\n"
            "짧고 실용적으로 한국어로 답하세요. "
            "위 TODO·주간 루틴이 있으면 일정 맥락에 맞게 참고하세요. "
            "실행 불가한 PC 작업은 PC에서 하라고 안내하세요."
        )
        reply = director._gemini_generate(prompt, flash=True)
        return {"ok": True, "final_result": reply, "route": "gemini+plan" if plan_ctx else "gemini"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@app.get("/api/health")
def health():
    try:
        from integrations.jarvis_instant import ensure_ready

        st = ensure_ready()
    except Exception as e:
        st = {"error": str(e)}
    return {
        "ok": True,
        "service": "jarvis-mobile",
        "port": PORT,
        "lan_ip": lan_ip(),
        "phone_url": f"http://{lan_ip()}:{PORT}",
        "auth_required": bool(MOBILE_TOKEN),
        "status": st,
    }


@app.post("/api/chat")
def chat(body: ChatBody, authorization: str | None = Header(default=None)):
    _check_token(authorization)
    result = _handle_chat(body.message)
    raw = result.get("final_result") or result.get("error") or ""
    reply = _friendly_reply(str(raw))
    return {
        "ok": bool(result.get("ok", True)) or bool(reply),
        "reply": reply,
        "route": result.get("route", ""),
        "fast_path": result.get("fast_path", False),
    }


@app.post("/api/tasks")
def create_task(body: TaskCreateBody, authorization: str | None = Header(default=None)):
    """웹 대시보드 호환용: YouTube URL 작업 등록."""
    _check_token(authorization)
    text = (body.url or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="url 값이 비어 있습니다.")
    result = _handle_chat(f"유튜브 작업 등록 {text}")
    if not result.get("ok"):
        raise HTTPException(status_code=500, detail=result.get("error") or "작업 등록 실패")
    return {
        "ok": True,
        "queued": True,
        "url": text,
        "reply": _friendly_reply(str(result.get("final_result") or "작업이 등록되었습니다.")),
        "route": result.get("route", ""),
        "command_id": result.get("command_id"),
    }


@app.get("/api/tts")
def tts_audio(
    text: str = Query(..., min_length=1, max_length=500),
    authorization: str | None = Header(default=None),
):
    """모바일 앱에서 JARVIS 음성 재생용 MP3."""
    _check_token(authorization)
    import asyncio
    import time

    snippet = (text or "").strip()[:500]
    try:
        import edge_tts

        cache = _ROOT / "jarvis_output" / "mobile_tts"
        cache.mkdir(parents=True, exist_ok=True)
        out = cache / f"m_{int(time.time() * 1000)}.mp3"
        voice = os.environ.get("JARVIS_EDGE_VOICE") or "ko-KR-SunHiNeural"

        async def _gen() -> None:
            comm = edge_tts.Communicate(snippet, voice, rate="+0%", pitch="-5Hz")
            await comm.save(str(out))

        asyncio.run(_gen())
        if not out.is_file():
            raise HTTPException(status_code=500, detail="TTS 파일 생성 실패")
        return FileResponse(out, media_type="audio/mpeg", filename="jarvis.mp3")
    except ImportError:
        raise HTTPException(
            status_code=503,
            detail="edge-tts 미설치 — pip install edge-tts",
        ) from None
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"TTS 오류: {e}") from e


@app.post("/api/instant")
def instant(body: InstantBody, authorization: str | None = Header(default=None)):
    _check_token(authorization)
    try:
        from integrations.jarvis_instant import run

        r = run(body.platform, body.query or "요약해줘")
        msg = ""
        if isinstance(r, dict):
            msg = r.get("message") or r.get("summary") or r.get("text") or ""
            if not msg:
                msg = "완료" if r.get("ok") else str(r.get("error", r))
        return {"ok": True, "reply": str(msg)[:3000], "detail": r}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.post("/api/plan/sync")
def plan_sync(body: PlanSyncBody, authorization: str | None = Header(default=None)):
    """CARENDAL APK — TODO·주간 계획표 → Gemini 컨텍스트 + SQLite DB 동기화."""
    _check_token(authorization)
    global _plan_snapshot
    _plan_snapshot = {
        "synced_at": datetime.now().isoformat(timespec="seconds"),
        "todos": (body.todos or [])[:500],
        "weekly_plan": (body.weekly_plan or [])[:200],
        "label": (body.label or "")[:200],
    }
    db_info: dict[str, Any] = {}
    try:
        from integrations.carendal_schedule_db import push_snapshot

        db_info = push_snapshot(
            weekly_plan=_plan_snapshot["weekly_plan"],
            todos=_plan_snapshot["todos"],
            label=_plan_snapshot["label"],
            client_revision=body.client_revision or "",
        )
    except Exception as e:
        db_info = {"ok": False, "error": str(e)}
    return {
        "ok": True,
        "todo_count": len(_plan_snapshot["todos"]),
        "routine_count": len(_plan_snapshot["weekly_plan"]),
        "synced_at": _plan_snapshot["synced_at"],
        "db": db_info,
    }


@app.get("/api/plan/status")
def plan_status(authorization: str | None = Header(default=None)):
    _check_token(authorization)
    db_meta: dict[str, Any] = {}
    try:
        from integrations.carendal_schedule_db import get_revision

        db_meta = get_revision()
    except Exception:
        pass
    return {
        "ok": True,
        "synced_at": _plan_snapshot.get("synced_at"),
        "todo_count": len(_plan_snapshot.get("todos") or []),
        "routine_count": len(_plan_snapshot.get("weekly_plan") or []),
        "label": _plan_snapshot.get("label") or "",
        "db": db_meta,
    }


@app.get("/api/schedule/pull")
def schedule_pull(authorization: str | None = Header(default=None)):
    """PC·모바일 공유 DB에서 최신 주간표·TODO 가져오기."""
    _check_token(authorization)
    try:
        from integrations.carendal_schedule_db import pull_snapshot

        snap = pull_snapshot()
        global _plan_snapshot
        _plan_snapshot = {
            "synced_at": snap.get("last_sync_at"),
            "todos": (snap.get("todos") or [])[:500],
            "weekly_plan": (snap.get("weekly_plan") or [])[:200],
            "label": (snap.get("label") or "")[:200],
        }
        return snap
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.post("/api/schedule/push")
def schedule_push(body: SchedulePushBody, authorization: str | None = Header(default=None)):
    """휴대폰·PC에서 수정한 표를 DB에 저장."""
    _check_token(authorization)
    try:
        from integrations.carendal_schedule_db import push_snapshot

        result = push_snapshot(
            weekly_plan=body.weekly_plan,
            todos=body.todos,
            label=body.label,
            client_revision=body.client_revision or "",
        )
        if body.weekly_plan is not None or body.todos is not None:
            global _plan_snapshot
            snap = result
            if body.weekly_plan is not None:
                _plan_snapshot["weekly_plan"] = body.weekly_plan[:200]
            if body.todos is not None:
                _plan_snapshot["todos"] = body.todos[:500]
            if body.label:
                _plan_snapshot["label"] = body.label[:200]
            _plan_snapshot["synced_at"] = snap.get("last_sync_at") or datetime.now().isoformat(
                timespec="seconds"
            )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.patch("/api/schedule/weekly/{row_id}")
def schedule_weekly_patch(
    row_id: str,
    body: WeeklyRowPatchBody,
    authorization: str | None = Header(default=None),
):
    """코드·API에서 주간표 한 행 수정."""
    _check_token(authorization)
    try:
        from integrations.carendal_schedule_db import update_weekly_row

        return update_weekly_row(row_id, body.fields or {})
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.post("/api/schedule/command")
def schedule_command(body: CommandBody, authorization: str | None = Header(default=None)):
    """원격 작업 호출 — 큐 등록 또는 즉시 실행."""
    _check_token(authorization)
    try:
        from integrations.carendal_command_runner import run_command_now
        from integrations.carendal_schedule_db import enqueue_command as db_enqueue

        if body.run_now:
            result = run_command_now(body.action_key, body.payload)
            return {"ok": True, "immediate": True, "result": result}
        queued = db_enqueue(
            body.action_key,
            payload=body.payload,
            source=body.source or "api",
        )
        return queued
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.post("/api/schedule/command/text")
def schedule_command_text(body: CommandTextBody, authorization: str | None = Header(default=None)):
    """자연어 지시 → 작업 큐 (블로그 작성·동기화 등 자동 인식)."""
    _check_token(authorization)
    try:
        from integrations.carendal_command_runner import enqueue_from_text, run_command_now, detect_action_from_text

        if body.run_now:
            detected = detect_action_from_text(body.text)
            if not detected:
                return {"ok": False, "error": "인식된 작업 없음 — action_key로 직접 호출하세요."}
            key, payload = detected
            return {"ok": True, "immediate": True, "result": run_command_now(key, payload)}
        return enqueue_from_text(body.text, source=body.source or "mobile")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.get("/api/schedule/commands")
def schedule_commands(
    status: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    authorization: str | None = Header(default=None),
):
    _check_token(authorization)
    try:
        from integrations.carendal_schedule_db import list_commands

        return {"ok": True, "items": list_commands(status=status, limit=limit)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.get("/api/supabase/status")
def supabase_status(authorization: str | None = Header(default=None)):
    """Supabase 연동 상태 · 휴대폰 직접 접속용 anon 설정."""
    _check_token(authorization)
    try:
        from integrations.supabase_jarvis_mobile import mobile_client_config, supabase_enabled

        cfg = mobile_client_config()
        return {"ok": True, "enabled": supabase_enabled(), **cfg}
    except Exception as e:
        return {"ok": False, "enabled": False, "error": str(e)}


@app.get("/api/programs")
def programs_list(
    program_key: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=100),
    authorization: str | None = Header(default=None),
):
    """Supabase에 저장된 프로그램 프리셋 목록."""
    _check_token(authorization)
    try:
        from integrations.supabase_jarvis_mobile import list_presets, supabase_enabled

        if not supabase_enabled():
            return {"ok": False, "error": "SUPABASE 미설정", "items": []}
        return list_presets(program_key=program_key, limit=limit)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.post("/api/programs/push")
def programs_push(body: ProgramPresetBody, authorization: str | None = Header(default=None)):
    """PC·모바일에서 프로그램 설정을 Supabase에 업로드."""
    _check_token(authorization)
    try:
        from integrations.supabase_jarvis_mobile import supabase_enabled, upsert_preset

        if not supabase_enabled():
            return {"ok": False, "error": "SUPABASE_URL / KEY를 .env에 설정하세요."}
        return upsert_preset(
            name=body.name,
            program_key=body.program_key,
            config_json=body.config_json,
            preset_id=body.preset_id or None,
            is_default=body.is_default,
            device_label=body.device_label,
            sort_order=body.sort_order,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.get("/api/dashboard")
def api_dashboard(authorization: str | None = Header(default=None)):
    """Cowork 스타일 라이브 대시보드 데이터."""
    _check_token(authorization)
    try:
        from integrations.jarvis_live_dashboard import build_dashboard

        return build_dashboard()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.get("/api/guide")
def api_guide(
    topic: str = Query(default="all"),
    authorization: str | None = Header(default=None),
):
    """사용법 텍스트 — grok_video | cowork | mobile | all."""
    _check_token(authorization)
    try:
        from integrations.grok_video_15 import format_guide_text as grok_guide
        from integrations.jarvis_live_dashboard import load_cowork_playbook

        t = (topic or "all").strip().lower()
        parts: list[str] = []
        if t in ("all", "grok", "grok_video", "video"):
            parts.append(grok_guide())
        if t in ("all", "cowork", "mcp", "dashboard"):
            pb = load_cowork_playbook()
            parts.append("=== JARVIS · Cowork/MCP 대체 ===")
            concept = pb.get("concept_ko")
            if isinstance(concept, str) and concept:
                parts.append(concept)
            parts.extend(pb.get("jarvis_equivalent_ko") or [])
            parts.append("")
            parts.extend(pb.get("quick_start_ko") or [])
        if t in ("all", "mobile", "carendal"):
            parts.append(
                "=== 휴대폰 CARENDAL ===\n"
                "1. JARVIS 서버: http://PC_IP:8766\n"
                "2. 프로그램 원격 실행 → 블로그 / Grok 영상 / 지도\n"
                "3. 대시보드: /mobile/dashboard.html\n"
                "상세: JARVIS_바로사용_가이드.md"
            )
        text = "\n\n".join(parts).strip()
        return {"ok": True, "topic": t, "text": text, "guide": text}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.post("/api/grok-video")
def grok_video_api(body: GrokVideoBody, authorization: str | None = Header(default=None)):
    """Grok Imagine Video 1.5 — 브라우저 열기 + 프롬프트."""
    _check_token(authorization)
    try:
        from integrations.grok_video_15 import dispatch

        payload = {
            "prompt": body.prompt,
            "template": body.template,
            "image_path": body.image_path,
        }
        return dispatch(body.action or "start", payload)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.post("/api/programs/run")
def programs_run(body: ProgramRunBody, authorization: str | None = Header(default=None)):
    """프리셋 기반 원격 실행 — PC가 켜져 있으면 즉시, 아니면 Supabase 큐에 등록."""
    _check_token(authorization)
    try:
        from integrations.supabase_jarvis_mobile import (
            enqueue_cloud_command,
            merge_preset_payload,
            supabase_enabled,
        )
        from integrations.carendal_command_runner import run_command_now
        from integrations.carendal_schedule_db import enqueue_command as db_enqueue

        action = (body.program_key or "canon_autoblog").strip()
        payload = merge_preset_payload(body.preset_id or None, body.payload)

        if body.cloud_only and supabase_enabled():
            return enqueue_cloud_command(action, payload=payload, source=body.source or "mobile")

        if body.run_now:
            result = run_command_now(action, payload)
            return {"ok": True, "immediate": True, "action_key": action, "result": result}

        if supabase_enabled():
            cloud = enqueue_cloud_command(action, payload=payload, source=body.source or "mobile")
            if cloud.get("ok"):
                from integrations.supabase_jarvis_mobile import sync_cloud_commands_to_runner

                sync_cloud_commands_to_runner(limit=3)
        queued = db_enqueue(action, payload=payload, source=body.source or "mobile")
        return {"ok": True, "queued": True, "action_key": action, **queued}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.post("/api/plan/summary")
def plan_summary(authorization: str | None = Header(default=None)):
    """Gemini — 동기화된 TODO·루틴 요약."""
    _check_token(authorization)
    ctx = _format_plan_for_prompt()
    if not ctx:
        return {
            "ok": False,
            "error": "동기화된 일정이 없습니다. APK에서 「JARVIS 동기화」를 눌러주세요.",
        }
    try:
        from jarvis_ultimate_system import JarvisUltimateDirector

        director = JarvisUltimateDirector()
        reply = director._gemini_generate(
            ctx + "\n\n위 일정을 바탕으로 오늘·이번 주 우선순위와 체크포인트를 bullet 5개 이내로 정리해 주세요.",
            flash=True,
        )
        return {"ok": True, "reply": _friendly_reply(str(reply)), "route": "gemini+plan"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@app.post("/api/todos/parse")
def todos_parse(body: ChatBody, authorization: str | None = Header(default=None)):
    """Gemini — 자연어 → TODO 항목 제안."""
    _check_token(authorization)
    import json
    import re

    today = datetime.now().strftime("%Y-%m-%d")
    raw = ""
    try:
        from jarvis_ultimate_system import JarvisUltimateDirector

        director = JarvisUltimateDirector()
        raw = director._gemini_generate(
            "다음을 TODO JSON 배열로만 출력하세요. 각 항목 필드: "
            f'date(YYYY-MM-DD), timeStart(HH:MM), timeEnd(HH:MM), task, content, division. '
            f"오늘={today}. 설명 없이 JSON만.\n입력: {body.message}",
            flash=True,
        )
        text = str(raw).strip()
        m = re.search(r"\[[\s\S]*\]", text)
        items = json.loads(m.group(0) if m else text)
        if not isinstance(items, list):
            items = [items]
        return {"ok": True, "items": items[:20], "route": "gemini+todos"}
    except Exception as e:
        return {"ok": False, "error": str(e), "reply": str(raw)[:500] if raw else ""}


@app.post("/api/meeting/minutes")
def meeting_minutes(body: MeetingMinutesBody, authorization: str | None = Header(default=None)):
    """Gemini — 회의명·맥락 → 회의록 초안."""
    _check_token(authorization)
    subject = (body.subject or "").strip() or _extract_meeting_subject(body.context or "")
    result = _generate_meeting_minutes(subject, body.context or "", body.notes or "")
    if not result.get("ok"):
        raise HTTPException(status_code=500, detail=result.get("error") or "회의록 생성 실패")
    return {
        "ok": True,
        "reply": result.get("reply") or "",
        "subject": result.get("subject") or subject,
        "route": result.get("route", "gemini+meeting_minutes"),
    }


@app.get("/")
def index():
    index_path = _MOBILE / "index.html"
    if index_path.is_file():
        return FileResponse(index_path)
    raise HTTPException(status_code=404, detail="mobile/index.html 없음")


if _MOBILE.is_dir():
    app.mount("/mobile", StaticFiles(directory=str(_MOBILE)), name="mobile-static")


def lan_ip() -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


def main() -> None:
    try:
        import uvicorn
    except ImportError:
        import subprocess

        subprocess.check_call([sys.executable, "-m", "pip", "install", "fastapi", "uvicorn[standard]", "-q"])
        import uvicorn

    ip = lan_ip()
    print("=" * 52)
    print("  JARVIS 모바일 서버")
    print(f"  이 PC:     http://127.0.0.1:{PORT}")
    print(f"  휴대폰:    http://{ip}:{PORT}")
    print(f"  대시보드:  http://{ip}:{PORT}/mobile/dashboard.html")
    print("  같은 Wi-Fi에서 휴대폰 브라우저로 접속하세요.")
    print("  가이드:    JARVIS_바로사용_가이드.md")
    print("  홈 화면에 추가하면 앱처럼 사용할 수 있습니다.")
    if MOBILE_TOKEN:
        print("  인증: Authorization: Bearer <JARVIS_MOBILE_TOKEN>")
    print("=" * 52)
    uvicorn.run(app, host="0.0.0.0", port=PORT, log_level="info")


if __name__ == "__main__":
    main()
