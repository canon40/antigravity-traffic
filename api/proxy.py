from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response

# Vercel: /api/* → Cloudtype Flask 허브로 프록시
app = FastAPI(title="Permacoat API Proxy", version="1.0")


def _base_url() -> str:
    # Vercel Project → Settings → Environment Variables
    # CLOUDTYPE_API_BASE=https://<your-service>.cloudtype.app
    return (os.environ.get("CLOUDTYPE_API_BASE") or "").strip().rstrip("/")


@app.get("/api/_proxy/health")
@app.get("/_proxy/health")
async def proxy_health():
    base = _base_url()
    return {
        "ok": bool(base),
        "proxy": "vercel",
        "cloudtype_base": base,
    }


@app.api_route("/api/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
@app.api_route("/api", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
async def proxy_api(request: Request, path: str = ""):
    base = _base_url()
    if not base:
        return JSONResponse(
            status_code=500,
            content={
                "ok": False,
                "error": "CLOUDTYPE_API_BASE not configured on Vercel.",
                "hint": "Vercel 환경변수에 Cloudtype 접속하기 URL을 넣으세요.",
            },
        )

    target = f"{base}/api/{path}".rstrip("/")
    q = str(request.url.query or "")
    if q:
        target = f"{target}?{q}"

    body = await request.body()
    incoming_headers = dict(request.headers)
    pass_headers = {}
    for key in ("authorization", "content-type", "x-request-id", "x-forwarded-for", "x-real-ip", "x-webhook-secret"):
        val = incoming_headers.get(key)
        if val:
            pass_headers[key] = val
    pass_headers["accept"] = incoming_headers.get("accept", "application/json")

    req = urllib.request.Request(
        target,
        data=body if body else None,
        headers=pass_headers,
        method=request.method,
    )

    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            raw = resp.read()
            content_type = resp.headers.get("content-type", "")
            if "application/json" in content_type:
                try:
                    parsed = json.loads(raw.decode("utf-8", errors="replace"))
                    return JSONResponse(status_code=resp.status, content=parsed)
                except Exception:
                    return Response(content=raw, status_code=resp.status, media_type=content_type)
            return Response(content=raw, status_code=resp.status, media_type=content_type or None)
    except urllib.error.HTTPError as e:
        raw = e.read()
        ctype = e.headers.get("content-type", "application/json")
        return Response(content=raw, status_code=e.code, media_type=ctype)
    except Exception as e:
        return JSONResponse(status_code=502, content={"ok": False, "error": f"proxy_error: {e}"})
