# -*- coding: utf-8 -*-
"""Vercel → Cloudtype API 프록시 (CLOUDTYPE_API_BASE). 다운 시 정적/허브 폴백."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

os.environ.setdefault("VERCEL", "1")
os.environ.setdefault("HUB_CLOUD_PLATFORM", "vercel")

app = FastAPI(title="SEO Hub Cloudtype Proxy", version="1.0")

_DEFAULT_CLOUDTYPE = (
    "https://port-0-antigravity-traffic-mqg8473t248a0738.sel3.cloudtype.app"
)
_READ_GET = frozenset(
    {"status", "health", "config", "logs", "history", "report", "keywords", "completion"}
)
_STATIC = {
    "status": _ROOT / "static" / "api" / "status.json",
    "health": _ROOT / "static" / "api" / "health.json",
    "config": _ROOT / "static" / "api" / "hub_config.json",
    "logs": _ROOT / "static" / "api" / "logs.json",
    "history": _ROOT / "static" / "api" / "history.json",
}


def _cloudtype_base() -> str:
    return (
        os.environ.get("CLOUDTYPE_API_BASE", "").strip()
        or os.environ.get("CLOUDTYPE_URL", "").strip()
        or _DEFAULT_CLOUDTYPE
    ).rstrip("/")


def _static_json(name: str) -> dict | list | None:
    p = _STATIC.get(name)
    if p and p.is_file():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    if name == "status":
        try:
            from api.hub_status import api_status

            return api_status()
        except Exception:
            pass
    return None


def _fallback_response(path: str, method: str) -> Response | None:
    root = (path or "").strip("/").split("/")[0] if path else ""
    if method.upper() != "GET" or root not in _READ_GET:
        return None
    data = _static_json(root)
    if data is None:
        return None
    return JSONResponse(
        data,
        headers={"X-Hub-Fallback": "static", "X-Cloudtype-Base": _cloudtype_base()},
    )


@app.get("/api/_proxy/health")
@app.get("/api/_proxy/health/")
def proxy_health():
    base = _cloudtype_base()
    try:
        r = httpx.get(f"{base}/api/health", timeout=8.0, follow_redirects=True)
        ok = r.status_code < 400
        body = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
    except Exception as exc:
        ok = False
        body = {"error": str(exc)}
    return {
        "ok": ok,
        "cloudtype_base": base,
        "cloudtype": body,
        "fallback": "static" if not ok else None,
        "dashboard": "https://app.cloudtype.io/@canon4040/antigravity-traffic:main/antigravity-traffic",
    }


async def _forward(path: str, request: Request) -> Response:
    base = _cloudtype_base()
    qs = str(request.url.query)
    target = f"{base}/api/{path}" + (f"?{qs}" if qs else "")
    skip = {"host", "content-length", "connection", "transfer-encoding"}
    headers = {k: v for k, v in request.headers.items() if k.lower() not in skip}
    body = await request.body()
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(20.0, connect=8.0)) as client:
            upstream = await client.request(
                request.method,
                target,
                content=body if body else None,
                headers=headers,
            )
        if upstream.status_code < 502:
            out_h = {
                k: v
                for k, v in upstream.headers.items()
                if k.lower() not in ("content-encoding", "transfer-encoding", "connection")
            }
            out_h["X-Hub-Proxy"] = "cloudtype"
            return Response(content=upstream.content, status_code=upstream.status_code, headers=out_h)
    except Exception:
        pass
    fb = _fallback_response(path, request.method)
    if fb:
        return fb
    return JSONResponse(
        {
            "success": False,
            "error": "Cloudtype 연결 실패 — 대시보드에서 재배포 후 CLOUDTYPE_API_BASE 확인",
            "cloudtype_base": base,
            "dashboard": "https://app.cloudtype.io/@canon4040/antigravity-traffic:main/antigravity-traffic#ingress",
        },
        status_code=503,
    )


@app.api_route("/api/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
async def proxy_api(path: str, request: Request):
    return await _forward(path, request)
