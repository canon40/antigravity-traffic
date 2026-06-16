# -*- coding: utf-8 -*-
"""Unsplash API로 블로그 이미지 검색·다운로드."""

from __future__ import annotations

import os
from typing import Any

import httpx

from content_factory.storage import save_image_bytes


def _access_key() -> str:
    return (
        os.environ.get("UNSPLASH_ACCESS_KEY", "").strip()
        or os.environ.get("UNSPLASH_API_KEY", "").strip()
    )


async def search_photos(query: str, *, per_page: int = 3) -> list[dict[str, Any]]:
    key = _access_key()
    if not key:
        return []
    url = "https://api.unsplash.com/search/photos"
    params = {"query": query, "per_page": per_page, "orientation": "landscape"}
    headers = {"Authorization": f"Client-ID {key}"}
    async with httpx.AsyncClient(timeout=30.0) as client:
        res = await client.get(url, params=params, headers=headers)
        res.raise_for_status()
        return list(res.json().get("results") or [])


async def download_and_save(query: str, *, max_images: int = 3) -> list[str]:
    """이미지 URL 검색 후 로컬 저장. 경로 문자열 리스트 반환."""
    photos = await search_photos(query, per_page=max_images)
    if not photos:
        return []
    saved: list[str] = []
    async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as client:
        for photo in photos:
            urls = photo.get("urls") or {}
            dl = urls.get("regular") or urls.get("small")
            if not dl:
                continue
            r = await client.get(dl)
            r.raise_for_status()
            path = save_image_bytes(r.content, ext="jpg", keyword=query)
            saved.append(str(path))
    return saved
