"""Vercel 전용 — JARVIS 프로그램 실행 (Cloudtype 구버전 우회)."""

from __future__ import annotations

import os
import sys

from fastapi import FastAPI, Request

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

# Vercel 런타임 — bat 대신 서버리스 액션
os.environ.setdefault("VERCEL", "1")
os.environ.setdefault("HUB_CLOUD_PLATFORM", "vercel")

from javis_programs import get_catalog, launch_program

app = FastAPI(title="JARVIS Hub API", version="1.0")


@app.get("/api/javis/programs")
@app.get("/api/javis/programs/")
def api_javis_programs(workspace: str = "all"):
    data = get_catalog(workspace=workspace)
    data["programs_engine"] = "vercel-javis-hub"
    data["cloud_mode"] = True
    return data


@app.post("/api/javis/launch")
@app.post("/api/javis/launch/")
async def api_javis_launch(request: Request):
    data = await request.json()
    program_id = (data.get("id") or data.get("program_id") or "").strip()
    if not program_id:
        return {"success": False, "error": "program id 필요"}
    logs: list[str] = []

    def _log(msg: str) -> None:
        logs.append(str(msg))

    result = launch_program(program_id, logger=_log)
    result["programs_engine"] = "vercel-javis-hub"
    if logs:
        result["logs"] = logs[-30:]
    return result


@app.get("/api/_javis/health")
def javis_hub_health():
    return {"ok": True, "service": "vercel_javis_hub", "engine": "cloud-fallback-v2"}
