# -*- coding: utf-8 -*-
"""장면별 스토리보드 이미지 생성·다운로드."""

from __future__ import annotations

import asyncio
import json
import os
import re
import shutil
import urllib.parse
from pathlib import Path
from typing import Callable

import httpx

LogFn = Callable[[str], None]
_ROOT = Path(__file__).resolve().parent.parent


def _log_default(msg: str) -> None:
    try:
        print(msg, flush=True)
    except UnicodeEncodeError:
        print(msg.encode("cp949", errors="replace").decode("cp949"), flush=True)


def _gemini_key() -> str:
    key = os.environ.get("GEMINI_API_KEY", "").strip() or os.environ.get("GOOGLE_API_KEY", "").strip()
    if key:
        return key
    acc = _ROOT / "accounts.json"
    if acc.is_file():
        try:
            data = json.loads(acc.read_text(encoding="utf-8"))
            return (data.get("gemini_key") or "").strip()
        except Exception:
            pass
    return ""


_GENERIC_STOCK_PHRASES = frozenset(
    {
        "photorealistic still frame",
        "photorealistic handheld shot",
        "photorealistic lifestyle",
        "natural daylight",
        "handheld lifestyle b-roll",
        "no cgi studio",
        "no text overlay",
        "lifestyle closeup",
        "natural light",
        "9:16 vertical",
        "cinematic 9:16 vertical",
    }
)


def _has_hangul(text: str) -> bool:
    return bool(re.search(r"[\uac00-\ud7a3]", text or ""))


def _is_usable_english_query(text: str) -> bool:
    t = re.sub(r"\s+", " ", (text or "").strip())
    if not t or _has_hangul(t):
        return False
    return len(re.findall(r"[a-zA-Z]{3,}", t)) >= 1


def _strip_generic_prefix(text: str) -> str:
    t = re.sub(r"\s+", " ", (text or "").strip())
    while t:
        low = t.lower()
        matched = False
        for prefix in _GENERIC_STOCK_PHRASES:
            if low.startswith(prefix):
                t = t[len(prefix) :].lstrip(" ,.-")
                matched = True
                break
        if not matched:
            break
    return t


def _pick_english_clause(text: str) -> str:
    """쉼표 구분 영어 프롬프트에서 스톡 검색에 쓸 구체 구절 선택."""
    t = _strip_generic_prefix(text)
    if not t:
        return ""
    parts = [p.strip() for p in t.split(",") if p.strip()]
    for part in parts:
        low = part.lower()
        if low in _GENERIC_STOCK_PHRASES:
            continue
        if _is_usable_english_query(part) and len(part) >= 4:
            return part[:80]
    if _is_usable_english_query(t):
        return t[:80]
    return ""


def _stock_search_query(scene: dict, plan_keywords: list[str] | None = None) -> str:
    """Pexels/Unsplash 등 — 반드시 장면 키워드(영어) 우선."""
    sk = str(scene.get("search_keyword") or "").strip()
    if _is_usable_english_query(sk):
        return sk[:80]

    for field in ("flow_prompt", "storyboard_image_prompt"):
        clause = _pick_english_clause(str(scene.get(field) or ""))
        if clause:
            return clause

    kws = [k.strip() for k in (plan_keywords or []) if str(k).strip()]
    if kws:
        n = max(1, int(scene.get("scene_no") or 1))
        return kws[(n - 1) % len(kws)][:80]

    return "home lifestyle cleaning closeup"


def _scene_prompt(scene: dict, plan: dict | None = None, product: dict | None = None) -> str:
    """Gemini/Pollinations용 — 키워드·장면 설명을 앞에 배치."""
    from shorts_factory.image_locale import append_locale_to_prompt
    from shorts_factory.products_loader import load_products_data

    sk = str(scene.get("search_keyword") or "").strip()
    kws = (plan or {}).get("input_keywords") or []
    if not sk and kws:
        n = max(1, int(scene.get("scene_no") or 1))
        sk = str(kws[(n - 1) % len(kws)])

    chunks: list[str] = []
    if sk:
        chunks.append(f"Main subject and scene: {sk}")
    for field in ("storyboard_image_prompt", "flow_prompt"):
        val = str(scene.get(field) or "").strip()
        if val and val not in chunks:
            chunks.append(val)
    visual = str(scene.get("visual_desc") or "").strip()
    if visual:
        chunks.append(visual)
    bg = str(scene.get("background_desc") or "").strip()
    if bg:
        chunks.append(bg)
    topic = str((plan or {}).get("topic") or "").strip()
    if topic:
        chunks.append(f"Topic context: {topic}")

    if chunks:
        base = re.sub(r"\s+", " ", ". ".join(chunks))[:480]
    else:
        base = "photorealistic lifestyle closeup, natural light, 9:16 vertical"

    if not product and plan:
        pid = str((plan or {}).get("product_id") or "").strip()
        if pid:
            product = load_products_data().get(pid)

    return append_locale_to_prompt(base, product)


def _save_genai_inline_image(response, dest: Path) -> bool:
    """generate_content(IMAGE) 응답에서 첫 이미지를 dest에 저장."""
    from PIL import Image
    import io

    if not response or not getattr(response, "candidates", None):
        return False
    for cand in response.candidates:
        content = getattr(cand, "content", None)
        if not content:
            continue
        for part in getattr(content, "parts", None) or []:
            if not getattr(part, "inline_data", None):
                continue
            try:
                if hasattr(part, "as_image"):
                    part.as_image().save(dest)
                else:
                    Image.open(io.BytesIO(part.inline_data.data)).save(dest)
                return dest.is_file() and dest.stat().st_size > 1024
            except Exception:
                continue
    return False


async def _pollinations_keyword(keyword: str, dest: Path, log: LogFn) -> bool:
    """짧은 키워드만으로 Pollinations 재시도 (전체 프롬프트 실패 시)."""
    kw = re.sub(r"\s+", " ", (keyword or "home lifestyle closeup").strip())[:120]
    short = f"{kw}, photorealistic lifestyle photo, natural daylight, vertical portrait 9:16, no text"
    return await _pollinations_image(short, dest, log)


async def _pollinations_image(prompt: str, dest: Path, log: LogFn) -> bool:
    short = re.sub(r"\s+", " ", (prompt or ""))[:480]
    url = (
        "https://image.pollinations.ai/prompt/"
        + urllib.parse.quote(short, safe="")
        + "?width=720&height=1280&nologo=true&enhance=false"
    )
    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            res = await client.get(url)
            if res.status_code != 200:
                return False
            if res.content and len(res.content) > 1024 and res.headers.get("content-type", "").startswith("image"):
                dest.write_bytes(res.content)
                log(f"      Pollinations 콘티 OK: {dest.name}")
                return True
    except Exception as e:
        log(f"      Pollinations 실패: {str(e)[:60]}")
    return False


async def _genai_image(prompt: str, dest: Path, log: LogFn) -> bool:
    """blog_content_gen 없이 Gemini/Imagen으로 스토리보드 이미지 생성."""
    key = _gemini_key()
    if not key:
        return False
    try:
        from google import genai
        from google.genai import types
    except ImportError:
        log("      AI 이미지: google-genai 미설치 (pip install google-genai)")
        return False

    full_prompt = (
        re.sub(r"\s+", " ", (prompt or "").strip())
        + " Vertical 9:16 photorealistic lifestyle B-roll still frame, natural light, no text overlay."
    )
    client = genai.Client(api_key=key)
    env_model = os.environ.get("SHORTS_IMAGE_MODEL", "").strip()
    models: list[str] = []
    if env_model:
        models.append(env_model)
    models.extend(
        m
        for m in (
            "gemini-2.5-flash-image",
            "gemini-2.0-flash-preview-image-generation",
            "imagen-3.0-generate-002",
        )
        if m not in models
    )

    for model_name in models:
        try:
            log(f"      Gemini 이미지 ({model_name})...")
            if "imagen" in model_name.lower():
                res = await asyncio.to_thread(
                    client.models.generate_images,
                    model=model_name,
                    prompt=full_prompt,
                    config=types.GenerateImagesConfig(number_of_images=1),
                )
                if res and res.generated_images:
                    img = res.generated_images[0]
                    tmp = dest.parent / f"_tmp_{dest.stem}.png"
                    if hasattr(img, "image"):
                        img.image.save(tmp)
                    else:
                        from PIL import Image
                        import io

                        Image.open(io.BytesIO(img.image_bytes)).save(tmp)
                    shutil.copy2(tmp, dest)
                    tmp.unlink(missing_ok=True)
                    if dest.is_file() and dest.stat().st_size > 1024:
                        log(f"      AI 콘티 OK: {dest.name}")
                        return True
            else:
                res = await asyncio.to_thread(
                    client.models.generate_content,
                    model=model_name,
                    contents=full_prompt,
                    config=types.GenerateContentConfig(response_modalities=["IMAGE"]),
                )
                if _save_genai_inline_image(res, dest):
                    log(f"      AI 콘티 OK: {dest.name}")
                    return True
        except Exception as e:
            log(f"      AI 이미지 실패 ({model_name}): {str(e)[:80]}")
    return False


async def _unsplash(prompt: str, dest: Path, log: LogFn, *, search_query: str = "") -> bool:
    key = os.environ.get("UNSPLASH_ACCESS_KEY", "").strip() or os.environ.get("UNSPLASH_API_KEY", "").strip()
    if not key:
        return False
    q = (search_query or _pick_english_clause(prompt) or prompt)[:80]
    try:
        async with httpx.AsyncClient(timeout=40.0) as client:
            res = await client.get(
                "https://api.unsplash.com/search/photos",
                params={"query": q, "per_page": 1, "orientation": "portrait"},
                headers={"Authorization": f"Client-ID {key}"},
            )
            res.raise_for_status()
            results = res.json().get("results") or []
            if not results:
                return False
            dl = (results[0].get("urls") or {}).get("regular")
            if not dl:
                return False
            img = await client.get(dl)
            img.raise_for_status()
            dest.write_bytes(img.content)
        log(f"      Unsplash 콘티 OK: {dest.name}")
        return True
    except Exception as e:
        log(f"      Unsplash 실패: {str(e)[:60]}")
        return False


async def _pexels(prompt: str, dest: Path, log: LogFn, *, search_query: str = "") -> bool:
    key = os.environ.get("PEXELS_API_KEY", "").strip()
    if not key:
        return False
    q = (search_query or _pick_english_clause(prompt) or prompt)[:80]
    try:
        async with httpx.AsyncClient(timeout=40.0) as client:
            res = await client.get(
                "https://api.pexels.com/v1/search",
                params={"query": q, "per_page": 1, "orientation": "portrait"},
                headers={"Authorization": key},
            )
            res.raise_for_status()
            photos = res.json().get("photos") or []
            if not photos:
                return False
            src = (photos[0].get("src") or {}).get("large") or (photos[0].get("src") or {}).get("medium")
            if not src:
                return False
            img = await client.get(src)
            img.raise_for_status()
            dest.write_bytes(img.content)
        log(f"      Pexels 콘티 OK: {dest.name}")
        return True
    except Exception as e:
        log(f"      Pexels 실패: {str(e)[:60]}")
        return False


async def _pixabay(prompt: str, dest: Path, log: LogFn, *, search_query: str = "") -> bool:
    key = os.environ.get("PIXABAY_API_KEY", "").strip()
    if not key:
        return False
    q = urllib.parse.quote((search_query or _pick_english_clause(prompt) or prompt)[:80])
    try:
        async with httpx.AsyncClient(timeout=40.0) as client:
            res = await client.get(
                f"https://pixabay.com/api/?key={key}&q={q}&image_type=photo&orientation=vertical&per_page=3"
            )
            res.raise_for_status()
            hits = res.json().get("hits") or []
            if not hits:
                return False
            url = hits[0].get("largeImageURL") or hits[0].get("webformatURL")
            if not url:
                return False
            img = await client.get(url)
            img.raise_for_status()
            dest.write_bytes(img.content)
        log(f"      Pixabay 콘티 OK: {dest.name}")
        return True
    except Exception as e:
        log(f"      Pixabay 실패: {str(e)[:60]}")
        return False


def _pillow_storyboard(scene: dict, dest: Path, log: LogFn) -> bool:
    try:
        from PIL import Image, ImageDraw

        w, h = 720, 1280
        n = int(scene.get("scene_no") or 1)
        palettes = [
            ((30, 58, 95), (15, 23, 42)),
            ((22, 78, 99), (12, 40, 55)),
            ((88, 52, 98), (45, 25, 60)),
            ((194, 65, 12), (80, 30, 10)),
        ]
        c1, c2 = palettes[(n - 1) % len(palettes)]
        img = Image.new("RGB", (w, h))
        draw = ImageDraw.Draw(img)
        for y in range(h):
            t = y / max(h - 1, 1)
            r = int(c1[0] * (1 - t) + c2[0] * t)
            g = int(c1[1] * (1 - t) + c2[1] * t)
            b = int(c1[2] * (1 - t) + c2[2] * t)
            draw.line([(0, y), (w, y)], fill=(r, g, b))
        # MP4용 — 글자·STORYBOARD 라벨 없이 은은한 배경만 (나레이션·자막과 겹치지 않게)
        draw.rounded_rectangle((24, 24, w - 24, h - 24), radius=24, outline=(255, 255, 255, 28), width=2)
        img.save(dest, "JPEG", quality=88)
        log(f"      임시 배경(무텍스트): {dest.name}")
        return True
    except Exception as e:
        log(f"      로컬 카드 실패: {str(e)[:60]}")
        return False


async def _one_scene_image(
    scene: dict,
    img_dir: Path,
    log: LogFn,
    *,
    plan: dict | None = None,
) -> None:
    n = int(scene.get("scene_no") or 0)
    dest = img_dir / f"scene_{n:02d}.jpg"
    if dest.is_file() and dest.stat().st_size > 2048 and scene.get("image_file"):
        return
    plan_keywords = (plan or {}).get("input_keywords") or []
    prompt = _scene_prompt(scene, plan)
    stock_q = _stock_search_query(scene, plan_keywords)
    log(f"   장면 {n} 콘티 이미지… (키워드: {stock_q})")
    for fn in (_genai_image, _pollinations_image, _unsplash, _pexels, _pixabay):
        if fn in (_unsplash, _pexels, _pixabay):
            ok = await fn(prompt, dest, log, search_query=stock_q)
        else:
            ok = await fn(prompt, dest, log)
        if ok:
            scene["image_file"] = f"images/{dest.name}"
            scene["image_source"] = fn.__name__.strip("_")
            scene["image_search_query"] = stock_q
            return
    kw = stock_q or str(scene.get("search_keyword") or "").strip()
    if kw and await _pollinations_keyword(kw, dest, log):
        scene["image_file"] = f"images/{dest.name}"
        scene["image_source"] = "pollinations_keyword"
        scene["image_search_query"] = kw
        return
    if _pillow_storyboard(scene, dest, log):
        scene["image_file"] = f"images/{dest.name}"
        scene["image_source"] = "pillow_storyboard"
        return
    log(f"   장면 {n} 이미지 실패")


async def attach_storyboard_images(
    plan: dict,
    out_dir: Path,
    *,
    log: LogFn | None = None,
    max_parallel: int = 2,
    force: bool = False,
) -> dict:
    log = log or _log_default
    scenes = plan.get("scenes") or []
    if not scenes:
        return plan
    img_dir = out_dir / "images"
    img_dir.mkdir(parents=True, exist_ok=True)
    sem = asyncio.Semaphore(max_parallel)

    async def run(sc: dict) -> None:
        async with sem:
            if force:
                sc.pop("image_file", None)
            await _one_scene_image(sc, img_dir, log, plan=plan)

    log(f"콘티 이미지 {len(scenes)}장 생성...")
    await asyncio.gather(*(run(sc) for sc in scenes))
    ok = sum(1 for sc in scenes if sc.get("image_file"))
    log(f"콘티 이미지 완료: {ok}/{len(scenes)}장")
    plan["images_ready"] = ok
    return plan


def ensure_storyboard_images(
    plan: dict,
    out_dir: Path,
    *,
    log: LogFn | None = None,
    force: bool = False,
) -> dict:
    """MP4 렌더 전 — 장면 이미지가 없으면 동기 생성."""
    scenes = plan.get("scenes") or []
    missing = sum(
        1
        for sc in scenes
        if not sc.get("image_file")
        or not (out_dir / str(sc.get("image_file", "")).replace("\\", "/")).is_file()
    )
    if not missing and not force:
        plan["images_ready"] = sum(1 for sc in scenes if sc.get("image_file"))
        return plan
    log = log or _log_default
    log(f"장면 이미지 {missing}장 없음 → 자동 생성…")
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(
            attach_storyboard_images(plan, out_dir, log=log, force=force)
        )
    finally:
        loop.close()
