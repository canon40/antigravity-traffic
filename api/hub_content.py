"""Vercel 전용 — 블로그·콘텐츠 생성 API (Cloudtype 없이 동작)."""

from __future__ import annotations

import os
import sys

from fastapi import FastAPI, Request

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from seo_content_builder import generate_content, list_workflows, save_content

app = FastAPI(title="Hub Content API", version="1.0")


@app.get("/api/content/workflows")
@app.get("/api/content/workflows/")
def api_workflows():
    return {"workflows": list_workflows()}


@app.post("/api/content/generate")
@app.post("/api/content/generate/")
async def api_generate(request: Request):
    data = await request.json()
    result = generate_content(
        data.get("workflow", "blog_review"),
        (data.get("keyword") or "").strip(),
        data.get("product_name"),
        data.get("brand"),
    )
    if result.get("success"):
        try:
            result["saved_path"] = save_content(result, data.get("product_id"))
        except OSError as exc:
            result["saved_path"] = None
            result["save_warning"] = str(exc)
    return result


@app.get("/api/_content/health")
def content_health():
    return {"ok": True, "service": "vercel_hub_content"}
