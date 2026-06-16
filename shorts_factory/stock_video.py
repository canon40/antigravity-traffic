# -*- coding: utf-8 -*-
"""무료 스톡 B-roll — Pexels·Pixabay API + 로컬 클립 관리."""

from __future__ import annotations

import json
import os
import re
import urllib.parse
from pathlib import Path
from typing import Any

import requests

_ROOT = Path(__file__).resolve().parent.parent
_SOURCES_PATH = _ROOT / "data" / "shorts_factory" / "free_stock_sources.json"
_KEYS_PATH = _ROOT / "data" / "shorts_factory" / "stock_api_keys.json"
_MANIFEST_NAME = "broll_manifest.json"

PEXELS_VIDEO_API = "https://api.pexels.com/videos/search"
PIXABAY_VIDEO_API = "https://pixabay.com/api/videos/"


def _load_json(path: Path, default: dict | list) -> dict | list:
    if not path.is_file():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def load_sources() -> dict[str, Any]:
    return _load_json(_SOURCES_PATH, {"api_sources": [], "browse_sources": [], "editors": []})


def load_api_keys() -> dict[str, str]:
    keys: dict[str, str] = {}
    file_keys = _load_json(_KEYS_PATH, {})
    if isinstance(file_keys, dict):
        for k, v in file_keys.items():
            if k.startswith("_"):
                continue
            val = str(v or "").strip()
            if val and not val.startswith("YOUR_"):
                keys[k] = val
    pex = (os.environ.get("PEXELS_API_KEY") or keys.get("pexels_api_key") or "").strip()
    pix = (os.environ.get("PIXABAY_API_KEY") or keys.get("pixabay_api_key") or "").strip()
    if not pex or not pix:
        javis_keys = _ROOT.parent.parent.parent / "javis" / "config" / "api_keys.json"
        if javis_keys.is_file():
            jk = _load_json(javis_keys, {})
            if isinstance(jk, dict):
                if not pex:
                    pex = str(jk.get("pexels_api_key") or "").strip()
                if not pix:
                    pix = str(jk.get("pixabay_api_key") or "").strip()
    if pex and not pex.startswith("YOUR_"):
        keys["pexels_api_key"] = pex
    if pix and not pix.startswith("YOUR_"):
        keys["pixabay_api_key"] = pix
    return keys


def api_key_status() -> dict[str, bool]:
    k = load_api_keys()
    return {
        "pexels": bool(k.get("pexels_api_key")),
        "pixabay": bool(k.get("pixabay_api_key")),
    }


def broll_dir(slug: str, shorts_root: Path | None = None) -> Path:
    root = shorts_root or _ROOT / "docs" / "shorts"
    d = root / slug / "broll"
    d.mkdir(parents=True, exist_ok=True)
    return d


def manifest_path(slug: str, shorts_root: Path | None = None) -> Path:
    return broll_dir(slug, shorts_root) / _MANIFEST_NAME


def load_manifest(slug: str, shorts_root: Path | None = None) -> dict[str, Any]:
    p = manifest_path(slug, shorts_root)
    data = _load_json(p, {"assignments": {}, "clips": []})
    if not isinstance(data, dict):
        return {"assignments": {}, "clips": []}
    data.setdefault("assignments", {})
    data.setdefault("clips", [])
    return data


def save_manifest(slug: str, manifest: dict[str, Any], shorts_root: Path | None = None) -> None:
    p = manifest_path(slug, shorts_root)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")


def _safe_name(text: str, *, max_len: int = 40) -> str:
    s = re.sub(r"[^\w가-힣-]+", "_", (text or "clip").strip())[:max_len].strip("_")
    return s or "clip"


def _normalize_results(source: str, items: list[dict]) -> list[dict]:
    out: list[dict] = []
    for it in items:
        out.append(
            {
                "source": source,
                "id": it.get("id"),
                "title": it.get("title") or "",
                "duration": it.get("duration"),
                "width": it.get("width"),
                "height": it.get("height"),
                "preview_url": it.get("preview_url") or "",
                "download_url": it.get("download_url") or "",
                "page_url": it.get("page_url") or "",
                "orientation": it.get("orientation") or "",
            }
        )
    return out


def search_pexels(query: str, *, per_page: int = 8, orientation: str = "portrait") -> dict[str, Any]:
    keys = load_api_keys()
    key = keys.get("pexels_api_key", "")
    if not key:
        return {"ok": False, "error": "PEXELS_API_KEY 없음 — data/shorts_factory/stock_api_keys.json 또는 환경변수", "results": []}

    try:
        res = requests.get(
            PEXELS_VIDEO_API,
            headers={"Authorization": key},
            params={"query": query or "lifestyle", "per_page": per_page, "orientation": orientation},
            timeout=30,
        )
        res.raise_for_status()
        data = res.json()
    except Exception as e:
        return {"ok": False, "error": f"Pexels 검색 실패: {e}", "results": []}

    items: list[dict] = []
    for vid in data.get("videos") or []:
        best_url = ""
        best_score = -1
        best_w = best_h = 0
        for vf in vid.get("video_files") or []:
            link = vf.get("link") or ""
            h = int(vf.get("height") or 0)
            w = int(vf.get("width") or 0)
            if not link:
                continue
            score = h * 10 + min(float(vid.get("duration") or 0), 60)
            if orientation == "portrait" and h < w:
                score -= 5000
            if score > best_score:
                best_score = score
                best_url = link
                best_w, best_h = w, h
        if not best_url:
            continue
        items.append(
            {
                "id": vid.get("id"),
                "title": (vid.get("user", {}) or {}).get("name") or query,
                "duration": vid.get("duration"),
                "width": best_w,
                "height": best_h,
                "preview_url": (vid.get("image") or "") or best_url,
                "download_url": best_url,
                "page_url": vid.get("url") or "",
                "orientation": "portrait" if best_h >= best_w else "landscape",
            }
        )
    return {"ok": True, "results": _normalize_results("pexels", items), "query": query}


def search_pixabay(query: str, *, per_page: int = 8) -> dict[str, Any]:
    keys = load_api_keys()
    key = keys.get("pixabay_api_key", "")
    if not key:
        return {"ok": False, "error": "PIXABAY_API_KEY 없음 — data/shorts_factory/stock_api_keys.json 또는 환경변수", "results": []}

    try:
        res = requests.get(
            PIXABAY_VIDEO_API,
            params={"key": key, "q": query or "lifestyle", "per_page": per_page, "video_type": "film"},
            timeout=30,
        )
        res.raise_for_status()
        data = res.json()
    except Exception as e:
        return {"ok": False, "error": f"Pixabay 검색 실패: {e}", "results": []}

    items: list[dict] = []
    for hit in data.get("hits") or []:
        videos = hit.get("videos") or {}
        pick = videos.get("large") or videos.get("medium") or videos.get("small") or {}
        url = pick.get("url") or ""
        if not url:
            continue
        w = int(pick.get("width") or 0)
        h = int(pick.get("height") or 0)
        items.append(
            {
                "id": hit.get("id"),
                "title": hit.get("tags") or query,
                "duration": hit.get("duration"),
                "width": w,
                "height": h,
                "preview_url": hit.get("picture_id") and f"https://i.vimeocdn.com/video/{hit['picture_id']}_640.jpg" or "",
                "download_url": url,
                "page_url": hit.get("pageURL") or "",
                "orientation": "portrait" if h >= w else "landscape",
            }
        )
    return {"ok": True, "results": _normalize_results("pixabay", items), "query": query}


def search_stock(source: str, query: str, *, per_page: int = 8) -> dict[str, Any]:
    src = (source or "pexels").strip().lower()
    if src == "pexels":
        return search_pexels(query, per_page=per_page)
    if src == "pixabay":
        return search_pixabay(query, per_page=per_page)
    return {"ok": False, "error": f"지원하지 않는 API 소스: {source}", "results": []}


def browse_links(query: str) -> list[dict[str, str]]:
    q = urllib.parse.quote((query or "lifestyle").strip())
    sources = load_sources()
    links: list[dict[str, str]] = []
    for s in sources.get("browse_sources") or []:
        tpl = s.get("search_url") or s.get("url") or ""
        url = tpl.replace("{query}", q) if "{query}" in tpl else tpl
        links.append(
            {
                "id": s.get("id", ""),
                "name_ko": s.get("name_ko") or s.get("name") or "",
                "url": url,
                "attribution": s.get("attribution") or "",
                "badge": s.get("badge") or "",
            }
        )
    return links


def download_url_to_file(url: str, dest: Path, *, timeout: int = 180) -> dict[str, Any]:
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    if not url:
        return {"ok": False, "error": "download_url 없음"}
    try:
        with requests.get(url, stream=True, timeout=timeout) as r:
            r.raise_for_status()
            with open(dest, "wb") as f:
                for chunk in r.iter_content(chunk_size=65536):
                    if chunk:
                        f.write(chunk)
    except Exception as e:
        return {"ok": False, "error": f"다운로드 실패: {e}"}
    if not dest.is_file() or dest.stat().st_size < 1024:
        return {"ok": False, "error": "파일이 비어 있거나 너무 작습니다"}
    return {"ok": True, "path": str(dest), "filename": dest.name}


def download_clip(
    slug: str,
    *,
    source: str,
    download_url: str,
    scene_no: int | None = None,
    title: str = "",
    video_id: str | int | None = None,
    shorts_root: Path | None = None,
) -> dict[str, Any]:
    root = shorts_root or _ROOT / "docs" / "shorts"
    if not (root / slug).is_dir():
        return {"ok": False, "error": f"프로젝트 없음: {slug}"}

    src = _safe_name(source, max_len=12)
    vid = _safe_name(str(video_id or "x"), max_len=16)
    fname = f"scene_{int(scene_no or 0):02d}_{src}_{vid}.mp4" if scene_no else f"{src}_{vid}.mp4"
    dest = broll_dir(slug, root) / fname

    dl = download_url_to_file(download_url, dest)
    if not dl.get("ok"):
        return dl

    manifest = load_manifest(slug, root)
    clip_entry = {
        "filename": fname,
        "source": source,
        "video_id": video_id,
        "title": title,
        "scene_no": scene_no,
        "download_url": download_url,
    }
    clips = [c for c in manifest.get("clips") or [] if c.get("filename") != fname]
    clips.append(clip_entry)
    manifest["clips"] = clips
    if scene_no is not None:
        manifest["assignments"][str(int(scene_no))] = fname
    save_manifest(slug, manifest, root)

    return {"ok": True, "filename": fname, "path": str(dest), "manifest": manifest, "rel": f"broll/{fname}"}


def assign_scene(slug: str, scene_no: int, filename: str, shorts_root: Path | None = None) -> dict[str, Any]:
    root = shorts_root or _ROOT / "docs" / "shorts"
    path = broll_dir(slug, root) / filename
    if not path.is_file():
        return {"ok": False, "error": f"파일 없음: {filename}"}
    manifest = load_manifest(slug, root)
    manifest["assignments"][str(int(scene_no))] = filename
    save_manifest(slug, manifest, root)
    return {"ok": True, "manifest": manifest}


def list_local_clips(slug: str, shorts_root: Path | None = None) -> dict[str, Any]:
    root = shorts_root or _ROOT / "docs" / "shorts"
    bdir = broll_dir(slug, root)
    manifest = load_manifest(slug, root)
    files: list[dict] = []
    for p in sorted(bdir.glob("*.mp4")):
        rel = f"broll/{p.name}"
        files.append(
            {
                "filename": p.name,
                "rel": rel,
                "size_mb": round(p.stat().st_size / (1024 * 1024), 2),
                "assigned_scene": next(
                    (int(k) for k, v in (manifest.get("assignments") or {}).items() if v == p.name),
                    None,
                ),
            }
        )
    return {"ok": True, "clips": files, "manifest": manifest, "assignments": manifest.get("assignments") or {}}


def broll_path_for_scene(
    slug: str,
    scene_no: int,
    *,
    shorts_root: Path | None = None,
) -> Path | None:
    root = shorts_root or _ROOT / "docs" / "shorts"
    manifest = load_manifest(slug, root)
    fname = (manifest.get("assignments") or {}).get(str(int(scene_no)))
    if not fname:
        return None
    p = broll_dir(slug, root) / fname
    return p if p.is_file() and p.stat().st_size > 1024 else None


def broll_path_for_scene_in_dir(
    out_dir: Path,
    scene_no: int,
) -> Path | None:
    slug = out_dir.name
    return broll_path_for_scene(slug, scene_no, shorts_root=out_dir.parent)
