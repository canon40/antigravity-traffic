from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response

# Vercel Python runtime entrypoint.
# `/api/*` 요청을 Cloudtype API로 프록시한다.
app = FastAPI(title="Vercel API Proxy", version="1.0")


def _base_url() -> str:
    # Vercel Project Environment Variable에 설정:
    # CLOUDTYPE_API_BASE=https://<your-cloudtype-domain>
    return (os.environ.get("CLOUDTYPE_API_BASE") or "").strip().rstrip("/")


def _forward_path(path: str) -> str:
    p = (path or "").lstrip("/")
    if p.startswith("api/"):
        p = p[4:]
    return p


@app.get("/_proxy/health")
async def proxy_health():
    base = _base_url()
    return {
        "ok": bool(base),
        "proxy": "vercel",
        "cloudtype_base": base,
    }


@app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
async def proxy(path: str, request: Request):
    base = _base_url()
    if not base:
        return JSONResponse(
            status_code=500,
            content={
                "ok": False,
                "error": "CLOUDTYPE_API_BASE not configured on Vercel.",
            },
        )

    target = f"{base}/api/{_forward_path(path)}".rstrip("/")
    q = str(request.url.query or "")
    if q:
        target = f"{target}?{q}"

    body = await request.body()
    incoming_headers = dict(request.headers)
    pass_headers = {}
    for key in ("authorization", "content-type", "x-request-id", "x-forwarded-for", "x-real-ip"):
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
        with urllib.request.urlopen(req, timeout=60) as resp:
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

