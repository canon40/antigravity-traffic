# -*- coding: utf-8 -*-
"""
FastAPI 콘텐츠 팩토리 API — n8n HTTP Request 노드 연동용.

엔드포인트:
  POST /api/save-data     — HTML/텍스트 저장
  POST /api/save-image    — URL에서 이미지 다운로드 저장
  GET  /api/affiliate     — 제휴 상품 검색
  POST /api/affiliate     — 제휴 상품 등록
  POST /api/generate      — 전체 파이프라인 실행
  GET  /health
"""

from __future__ import annotations

import os
from typing import Any, Optional

import httpx
from fastapi import BackgroundTasks, FastAPI, HTTPException
from pydantic import BaseModel, Field

from content_factory import affiliate_db, storage
from content_factory.pipeline import FactoryResult, run_content_factory

app = FastAPI(
    title="Content Factory API",
    description="n8n + 로컬 Gemma4 콘텐츠 팩토리 (지성스 워크플로)",
    version="1.0.0",
)


class SaveDataRequest(BaseModel):
    topic: str = Field(..., description="파일명 슬러그용 주제")
    content: str = Field(..., description="HTML 또는 Markdown 본문")
    format: str = Field("html", description="html | md")
    suffix: str = Field("", description="파일명 접미사 (draft, commercial 등)")


class SaveImageRequest(BaseModel):
    url: str
    keyword: str = ""


class AffiliateProduct(BaseModel):
    id: str
    name: str
    tags: list[str] = Field(default_factory=list)
    link: str = ""
    blog_html: str = ""


class GenerateRequest(BaseModel):
    topic: str
    use_naver_search: bool = True
    use_unsplash: bool = True
    max_images: int = 3


class JobStatus(BaseModel):
    job_id: str
    status: str
    result: Optional[dict[str, Any]] = None
    error: Optional[str] = None


_jobs: dict[str, JobStatus] = {}


@app.get("/health")
def health():
    return {
        "ok": True,
        "content_dir": str(storage.content_root()),
        "ollama_model": os.environ.get("CONTENT_FACTORY_MODEL", "gemma4:e2b"),
    }


@app.post("/api/save-data")
def save_data(req: SaveDataRequest):
    if req.format.lower() == "md":
        path = storage.save_text(req.topic, req.content, suffix=req.suffix or "draft")
    else:
        path = storage.save_html(req.topic, req.content, suffix=req.suffix or "draft")
    return {"ok": True, "path": str(path)}


@app.post("/api/save-image")
async def save_image(req: SaveImageRequest):
    try:
        async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as client:
            res = await client.get(req.url)
            res.raise_for_status()
            ext = "jpg"
            ct = (res.headers.get("content-type") or "").lower()
            if "png" in ct:
                ext = "png"
            elif "webp" in ct:
                ext = "webp"
            path = storage.save_image_bytes(res.content, ext=ext, keyword=req.keyword)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return {"ok": True, "path": str(path)}


@app.get("/api/affiliate")
def get_affiliate(q: str, limit: int = 5):
    items = affiliate_db.search_by_topic(q, limit=limit)
    return {"query": q, "count": len(items), "products": items}


@app.post("/api/affiliate")
def post_affiliate(product: AffiliateProduct):
    saved = affiliate_db.upsert_product(product.model_dump())
    return {"ok": True, "product": saved}


async def _run_job(job_id: str, req: GenerateRequest):
    _jobs[job_id] = JobStatus(job_id=job_id, status="running")

    def log(msg: str) -> None:
        print(f"[{job_id}] {msg}", flush=True)

    try:
        result: FactoryResult = await run_content_factory(
            req.topic,
            use_naver_search=req.use_naver_search,
            use_unsplash=req.use_unsplash,
            max_images=req.max_images,
            log=log,
        )
        _jobs[job_id] = JobStatus(
            job_id=job_id,
            status="done",
            result={
                "topic": result.topic,
                "title": result.title,
                "tags": result.tags,
                "draft_path": result.draft_path,
                "commercial_path": result.commercial_path,
                "image_paths": result.image_paths,
                "affiliate_count": len(result.affiliate_products),
            },
        )
    except Exception as e:
        _jobs[job_id] = JobStatus(job_id=job_id, status="error", error=str(e))


@app.post("/api/generate")
async def generate(req: GenerateRequest, background_tasks: BackgroundTasks, sync: bool = False):
    if sync:
        result = await run_content_factory(
            req.topic,
            use_naver_search=req.use_naver_search,
            use_unsplash=req.use_unsplash,
            max_images=req.max_images,
        )
        return {
            "ok": True,
            "topic": result.topic,
            "title": result.title,
            "draft_path": result.draft_path,
            "commercial_path": result.commercial_path,
            "image_paths": result.image_paths,
        }

    import uuid

    job_id = uuid.uuid4().hex[:12]
    background_tasks.add_task(_run_job, job_id, req)
    return {"ok": True, "job_id": job_id, "status": "queued"}


@app.get("/api/jobs/{job_id}")
def job_status(job_id: str):
    job = _jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="job not found")
    return job


def main() -> None:
    import uvicorn

    port = int(os.environ.get("CONTENT_FACTORY_PORT", "8792"))
    uvicorn.run(
        "content_factory.api:app",
        host=os.environ.get("CONTENT_FACTORY_HOST", "127.0.0.1"),
        port=port,
        reload=False,
    )


if __name__ == "__main__":
    main()
