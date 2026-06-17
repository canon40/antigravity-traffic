# -*- coding: utf-8
"""블로그용 이미지·숏폼 영상 생성."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import requests

_ROOT = Path(__file__).resolve().parent.parent


def _out_base(keyword: str) -> Path:
    slug = "".join(c if c.isalnum() or c in "-_" else "_" for c in keyword[:30]).strip("_")
    p = _ROOT / "jarvis_output" / "blog_auto" / f"{slug}_{int(time.time())}"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _pil_placeholder(path: Path, label: str) -> dict[str, Any]:
    try:
        from PIL import Image, ImageDraw, ImageFont

        img = Image.new("RGB", (1200, 630), color=(18, 24, 38))
        draw = ImageDraw.Draw(img)
        text = (label or "Blog")[:40]
        draw.text((60, 280), text, fill=(230, 230, 240))
        img.save(path, "JPEG", quality=88)
        return {"ok": True, "path": str(path), "source": "pil"}
    except Exception as e:
        path.write_bytes(b"")
        return {"ok": False, "error": str(e), "path": str(path)}


def generate_gemini_blog_image(prompt: str, save_path: Path, *, aspect_ratio: str = "16:9") -> dict[str, Any]:
    """Gemini/Imagen API로 블로그 이미지 생성 (폴더·Pexels 없음)."""
    save_path = Path(save_path)
    save_path.parent.mkdir(parents=True, exist_ok=True)
    jpg_path = save_path.with_suffix(".jpg")
    png_path = save_path.with_suffix(".png")

    try:
        from integrations.gemini_image_bridge import generate_image_gemini

        r = generate_image_gemini(
            f"Professional blog photo, no text overlay, high quality: {prompt}",
            png_path,
            aspect_ratio=aspect_ratio,
        )
        if not r.get("ok"):
            return {**r, "path": str(jpg_path)}

        src = Path(r.get("output_file") or png_path)
        if not src.is_file():
            return {"ok": False, "error": "gemini 이미지 파일 없음", "path": str(jpg_path)}

        try:
            from PIL import Image

            im = Image.open(src)
            if im.mode in ("RGBA", "P"):
                im = im.convert("RGB")
            im.save(jpg_path, "JPEG", quality=90)
            if src.suffix.lower() == ".png" and src != jpg_path:
                try:
                    src.unlink(missing_ok=True)
                except Exception:
                    pass
        except Exception:
            jpg_path.write_bytes(src.read_bytes())

        return {
            "ok": True,
            "path": str(jpg_path),
            "source": r.get("engine") or "gemini",
            "model": r.get("model", ""),
        }
    except Exception as e:
        ph = _pil_placeholder(jpg_path, prompt)
        ph["error"] = str(e)
        return ph


def _image_source_mode() -> str:
    try:
        cfg = json.loads((_ROOT / "config" / "blog_automation.json").read_text(encoding="utf-8"))
        return (cfg.get("media") or {}).get("image_source") or "pillow"
    except Exception:
        return "pillow"


def create_blog_image(prompt: str, save_path: Path) -> dict[str, Any]:
    """설정에 따라 Pillow / Pexels / Gemini (기본은 API 없는 Pillow)."""
    mode = _image_source_mode().lower()
    if mode in ("pillow", "pil", "placeholder", "local"):
        return _pil_placeholder(save_path, prompt)
    if mode in ("pexels", "pexels_then_pil"):
        return download_pexels_photo(prompt, save_path)
    if mode in ("gemini", "gen", "imagen", "google"):
        return generate_gemini_blog_image(prompt, save_path)
    return _pil_placeholder(save_path, prompt)


def download_pexels_photo(keyword: str, save_path: Path) -> dict[str, Any]:
    from integrations.pexels_client import pexels_api_key

    key = pexels_api_key()
    save_path = Path(save_path)
    save_path.parent.mkdir(parents=True, exist_ok=True)
    if not key:
        return _pil_placeholder(save_path, keyword)

    try:
        res = requests.get(
            "https://api.pexels.com/v1/search",
            headers={"Authorization": key},
            params={"query": keyword or "blog", "per_page": 5},
            timeout=30,
        )
        res.raise_for_status()
        photos = res.json().get("photos") or []
        if not photos:
            return _pil_placeholder(save_path, keyword)
        src = photos[0].get("src") or {}
        url = src.get("large2x") or src.get("large") or src.get("original") or ""
        if not url:
            return _pil_placeholder(save_path, keyword)
        with requests.get(url, stream=True, timeout=60) as r:
            r.raise_for_status()
            save_path.write_bytes(r.content)
        return {"ok": True, "path": str(save_path), "source": "pexels", "url": url}
    except Exception as e:
        return _pil_placeholder(save_path, keyword) if save_path else {"ok": False, "error": str(e)}


def generate_blog_media(
    article: dict[str, Any], *, keyword: str = "", with_video: bool = False
) -> dict[str, Any]:
    """이미지 3장(Gemini) + 선택 시에만 숏폼 MP4."""
    kw = keyword or article.get("keyword") or "blog"
    out = _out_base(kw)
    prompts = article.get("image_prompts") or [kw, kw, kw]
    if isinstance(prompts, str):
        prompts = [prompts]

    cfg_media = {}
    try:
        cfg_media = json.loads((_ROOT / "config" / "blog_automation.json").read_text(encoding="utf-8")).get(
            "media"
        ) or {}
    except Exception:
        pass
    n_images = int(cfg_media.get("images_per_post") or 3)

    images: list[dict[str, Any]] = []
    for i, pr in enumerate(list(prompts)[:n_images]):
        r = create_blog_image(str(pr), out / f"img_{i}.jpg")
        images.append(r)

    video_r: dict[str, Any] = {"ok": False, "skipped": True}
    try:
        cfg = json.loads((_ROOT / "config" / "blog_automation.json").read_text(encoding="utf-8"))
    except Exception:
        cfg = {}
    video_on = with_video and cfg.get("media", {}).get("video_enabled", False)
    if video_on:
        topic = article.get("video_title") or article.get("title") or kw
        try:
            from agent.shorts_video_factory import run_shorts_video_factory

            mp4 = out / "clip.mp4"
            video_r = run_shorts_video_factory(topic, output_path=str(mp4))
            video_r["path"] = str(mp4) if mp4.is_file() else video_r.get("video_path", "")
        except Exception as e:
            video_r = {"ok": False, "error": str(e)}

    (out / "package.json").write_text(
        json.dumps({"keyword": kw, "title": article.get("title"), "images": images, "video": video_r}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return {
        "ok": True,
        "output_dir": str(out),
        "images": [i.get("path") for i in images if i.get("ok")],
        "video": video_r.get("path") or video_r.get("video_path") or "",
        "video_result": video_r,
    }
