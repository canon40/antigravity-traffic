# -*- coding: utf-8 -*-
"""Vercel 폴백 — Cloudtype 다운 시에도 허브 UI(/api/status 등) 동작."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import JSONResponse

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

os.environ.setdefault("VERCEL", "1")
os.environ.setdefault("HUB_CLOUD_PLATFORM", "vercel")

app = FastAPI(title="SEO Hub Status Fallback", version="1.0")


def _config() -> dict:
    try:
        from rank_tracker import load_config

        return load_config() or {}
    except Exception:
        p = _ROOT / "config.json"
        if p.is_file():
            return json.loads(p.read_text(encoding="utf-8"))
        return {}


def _history_snapshot() -> tuple[dict[str, str] | None, int]:
    try:
        from rank_persistence import fetch_history_status

        last, total = fetch_history_status()
        return last, int(total or 0)
    except Exception:
        return None, 0


@app.get("/api/status")
@app.get("/api/status/")
def api_status():
    cfg = _config()
    keywords = cfg.get("keywords") or []
    priority = cfg.get("priority_keywords") or []
    products = cfg.get("products") or []
    last_row, total_tracks = _history_snapshot()
    last_rank = None
    last_rank_keyword = None
    if last_row:
        try:
            last_rank = int(last_row.get("순위") or last_row.get("rank") or 0) or None
        except (TypeError, ValueError):
            last_rank = None
        last_rank_keyword = last_row.get("키워드") or last_row.get("keyword")
    return {
        "running": False,
        "traffic_running": False,
        "traffic_enabled": True,
        "rank_enabled": True,
        "traffic_loop": False,
        "auto_started": False,
        "last_rank": last_rank,
        "last_rank_keyword": last_rank_keyword,
        "total_tracks": total_tracks,
        "keyword_count": len(keywords),
        "priority_count": len(priority),
        "track_batch_count": len(priority) or min(len(keywords), 10),
        "serverless": True,
        "platform": "vercel",
        "auto_mode": "cron",
        "persistence": "supabase" if total_tracks else "vercel_static",
        "naver_api_configured": bool(os.environ.get("NAVER_CLIENT_ID")),
        "interval_minutes": cfg.get("track_interval_minutes", 60),
        "products": [
            {
                "id": str(p.get("id") or ""),
                "name": p.get("name") or "",
                "url": p.get("url") or "",
            }
            for p in products
            if isinstance(p, dict) and p.get("id")
        ][:12],
        "priority_keywords": [
            {"keyword": (p.get("keyword") or ""), "product_id": p.get("product_id")}
            for p in priority[:12]
            if isinstance(p, dict) and p.get("keyword")
        ],
        "hub_note": "Vercel 프론트 모드 — 순위·트래픽 실행은 PC run.bat 또는 Cloudtype",
        "programs_engine": "vercel-status-fallback",
    }


@app.get("/api/health")
@app.get("/api/health/")
def api_health():
    return {"status": "healthy", "mode": "vercel_fallback", "ok": True}


@app.get("/api/config")
@app.get("/api/config/")
def api_config():
    return _config()


@app.get("/api/logs")
@app.get("/api/logs/")
def api_logs():
    return {"logs": ["[Vercel] API는 읽기 전용 — run.bat 또는 Cloudtype에서 순위·트래픽 실행"]}


@app.get("/api/history")
@app.get("/api/history/")
def api_history(limit: int | None = None):
    try:
        from rank_tracker import get_history

        rows = get_history(limit=limit or 120)
        return rows if isinstance(rows, list) else []
    except Exception:
        return []


@app.get("/api/_hub/health")
def hub_status_health():
    return {"ok": True, "service": "vercel_hub_status"}
