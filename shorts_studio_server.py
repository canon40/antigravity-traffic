# -*- coding: utf-8 -*-
"""쇼츠 공장 스튜디오 UI — 포트 8766."""

from __future__ import annotations

import asyncio
import io
import json
import os
import re
import socket
import zipfile
import sys
import time
import threading
import webbrowser
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, unquote, urlparse

_ROOT = Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

SHORTS_DIR = _ROOT / "docs" / "shorts"
DETAIL_PAGE_DIR = _ROOT / "docs" / "detail_page"
SHOPPING_SHORTS_DIR = _ROOT / "docs" / "shopping_shorts"
VIDEO_EVOLUTION_DIR = _ROOT / "docs" / "video_evolution"
MV_GUIDE_DIR = _ROOT / "docs" / "guides" / "lV9UzdYkT20-google-flow-mv"
SUPER_AGENTS_GUIDE_DIR = _ROOT / "docs" / "guides" / "Ovj5f0ajDww-super-agents"
PLAYBOOK_MV_PATH = _ROOT / "data" / "shorts_factory" / "playbooks" / "lV9UzdYkT20_google_flow_mv.json"
PLAYBOOK_SUPER_AGENTS_PATH = _ROOT / "data" / "shorts_factory" / "playbooks" / "Ovj5f0ajDww_super_agents.json"
SANGSEO_DIR = _ROOT / "sangseopage" / "ui"
PLANNING_PATH = _ROOT / "data" / "shorts_factory" / "detail_planning.json"
PRODUCTS_PATH = _ROOT / "data" / "shorts_factory" / "products.json"
BRAND_PATH = _ROOT / "data" / "shorts_factory" / "brand.json"
VIDEO_STUDIOS_PATH = _ROOT / "data" / "shorts_factory" / "video_studios.json"
MALVA_HUB_PATH = _ROOT / "data" / "shorts_factory" / "malva_ai_hub.json"
SHOPPING_SHORTS_HUB_PATH = _ROOT / "data" / "shorts_factory" / "shopping_shorts_hub.json"
FREE_STOCK_PATH = _ROOT / "data" / "shorts_factory" / "free_stock_sources.json"
DEFAULT_PORT = 8766

_gen_lock = threading.Lock()
_gen_busy = False
_video_lock = threading.Lock()
_video_busy = False

_FABLE_CACHE_TTL = 30.0
_fable_cache: dict | None = None
_fable_cache_at = 0.0
_fable_lock = threading.Lock()

_BOOTSTRAP_CACHE_TTL = 120.0
_bootstrap_cache: dict | None = None
_bootstrap_cache_at = 0.0
_bootstrap_lock = threading.Lock()
_bootstrap_refreshing = False


def _get_fable_status() -> dict:
    """Ollama ping은 느릴 수 있어 TTL 캐시 + lock으로 /api/status 병목 완화."""
    global _fable_cache, _fable_cache_at
    now = time.monotonic()
    if _fable_cache is not None and (now - _fable_cache_at) < _FABLE_CACHE_TTL:
        return _fable_cache
    with _fable_lock:
        now = time.monotonic()
        if _fable_cache is not None and (now - _fable_cache_at) < _FABLE_CACHE_TTL:
            return _fable_cache
        loop = asyncio.new_event_loop()
        try:
            from shorts_factory.fable_loop import check_local_fable_ready

            info = loop.run_until_complete(check_local_fable_ready())
        finally:
            loop.close()
        _fable_cache = info
        _fable_cache_at = now
        return info


def _warm_fable_cache() -> None:
    try:
        _get_fable_status()
    except Exception as e:
        print(f"[fable] 캐시 워밍 실패 (무시): {e}")


def _build_bootstrap_payload() -> dict:
    from shorts_factory.stock_video import api_key_status, load_sources

    stock = load_sources()
    stock["api_keys"] = api_key_status()
    return {
        "ok": True,
        "products": _load_products_data(),
        "brand": _load_brand_data(),
        "video_studios": _load_video_studios_data(),
        "malva_hub": _load_malva_hub_data(),
        "shopping_shorts_hub": _load_shopping_shorts_hub_data(),
        "stock": stock,
    }


def _store_bootstrap_payload(payload: dict) -> None:
    global _bootstrap_cache, _bootstrap_cache_at
    _bootstrap_cache = payload
    _bootstrap_cache_at = time.monotonic()


def _refresh_bootstrap_cache_async() -> None:
    """만료된 캐시를 백그라운드에서 갱신 — 요청 스레드는 stale 캐시를 즉시 반환."""
    global _bootstrap_refreshing

    def _run() -> None:
        global _bootstrap_refreshing
        try:
            with _bootstrap_lock:
                payload = _build_bootstrap_payload()
                _store_bootstrap_payload(payload)
        except Exception as e:
            print(f"[bootstrap] 백그라운드 갱신 실패 (무시): {e}")
        finally:
            _bootstrap_refreshing = False

    _bootstrap_refreshing = True
    threading.Thread(target=_run, daemon=True).start()


def _get_bootstrap_payload() -> dict:
    """Studio 부트 API — TTL 캐시 + stale-while-revalidate로 요청 블로킹 방지."""
    global _bootstrap_refreshing
    now = time.monotonic()
    cached = _bootstrap_cache
    if cached is not None:
        if (now - _bootstrap_cache_at) < _BOOTSTRAP_CACHE_TTL:
            return cached
        if not _bootstrap_refreshing:
            _refresh_bootstrap_cache_async()
        return cached

    with _bootstrap_lock:
        now = time.monotonic()
        cached = _bootstrap_cache
        if cached is not None:
            if (now - _bootstrap_cache_at) < _BOOTSTRAP_CACHE_TTL:
                return cached
            if not _bootstrap_refreshing:
                _refresh_bootstrap_cache_async()
            return cached
        payload = _build_bootstrap_payload()
        _store_bootstrap_payload(payload)
        return payload


def _warm_bootstrap_cache() -> None:
    try:
        _get_bootstrap_payload()
        print("[bootstrap] 캐시 준비 완료")
    except Exception as e:
        print(f"[bootstrap] 캐시 워밍 실패 (무시): {e}")


def _slug(product_id: str, topic: str) -> str:
    base = re.sub(r"[^\w가-힣]+", "_", (topic or product_id).strip())[:36].strip("_")
    day = datetime.now().strftime("%Y%m%d_%H%M")
    return f"{product_id}_{day}_{base or 'shorts'}"


def _load_products_raw() -> dict:
    if not PRODUCTS_PATH.is_file():
        return {}
    return json.loads(PRODUCTS_PATH.read_text(encoding="utf-8"))


def _load_products_data() -> dict:
    from shorts_factory.products_loader import load_products_data

    return load_products_data()


def _load_brand_data() -> dict:
    if not BRAND_PATH.is_file():
        return {"name": "루프릴", "name_en": "LoopReel"}
    return json.loads(BRAND_PATH.read_text(encoding="utf-8"))


def _load_video_studios_data() -> dict:
    if not VIDEO_STUDIOS_PATH.is_file():
        return {"studios": [], "workflow": []}
    return json.loads(VIDEO_STUDIOS_PATH.read_text(encoding="utf-8"))


def _load_malva_hub_data() -> dict:
    if not MALVA_HUB_PATH.is_file():
        return {}
    return json.loads(MALVA_HUB_PATH.read_text(encoding="utf-8"))


def _load_shopping_shorts_hub_data() -> dict:
    if not SHOPPING_SHORTS_HUB_PATH.is_file():
        return {}
    return json.loads(SHOPPING_SHORTS_HUB_PATH.read_text(encoding="utf-8"))


def _load_free_stock_data() -> dict:
    if not FREE_STOCK_PATH.is_file():
        return {"api_sources": [], "browse_sources": [], "editors": []}
    return json.loads(FREE_STOCK_PATH.read_text(encoding="utf-8"))


def _save_products_data(data: dict) -> None:
    PRODUCTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    PRODUCTS_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _new_product_id(label: str, existing: dict) -> str:
    base = re.sub(r"[^\w가-힣]+", "_", (label or "product").strip().lower())[:28].strip("_")
    if not base:
        base = "product"
    if base[0].isdigit():
        base = f"p_{base}"
    cand = base
    n = 2
    while cand in existing:
        cand = f"{base}_{n}"
        n += 1
    return cand


def _add_product(body: dict) -> dict:
    raw = _load_products_raw()
    label = str(body.get("label") or "").strip()
    if not label:
        raise ValueError("제품명(label)이 필요합니다.")
    full_name = str(body.get("full_name") or label).strip()
    raw_kw = body.get("preset_keywords") or []
    if isinstance(raw_kw, str):
        kws = [p.strip() for p in re.split(r"[,，\n]+", raw_kw) if p.strip()]
    else:
        kws = [str(x).strip() for x in raw_kw if str(x).strip()]
    if not kws:
        raise ValueError("프리셋 키워드 1개 이상 필요합니다.")

    pid = str(body.get("id") or "").strip().lower()
    if pid:
        pid = re.sub(r"[^\w가-힣0-9_-]+", "_", pid)[:32].strip("_")
    if not pid:
        pid = _new_product_id(label, raw)
    if pid in raw and not body.get("overwrite"):
        raise ValueError(f"이미 있는 제품 ID: {pid}")

    forbidden = body.get("forbidden") or []
    if isinstance(forbidden, str):
        forbidden = [p.strip() for p in re.split(r"[,，\n]+", forbidden) if p.strip()]

    raw[pid] = {
        "id": pid,
        "label": label,
        "brand": str(body.get("brand") or "듀라코트").strip(),
        "product_line": str(body.get("product_line") or label).strip(),
        "full_name": full_name,
        "variants": body.get("variants") or [label],
        "style": str(body.get("style") or "home_lifestyle").strip(),
        "settings": body.get("settings") or [],
        "preset_keywords": kws,
        "forbidden": forbidden,
        "truth": str(body.get("truth") or "").strip(),
        "smartstore": str(body.get("smartstore") or "").strip(),
    }
    _save_products_data(raw)
    return {"ok": True, "product_id": pid, "products": _load_products_data()}


_detail_lock = threading.Lock()
_detail_busy = False


def _enrich_plan_detail(slug: str, plan: dict) -> dict:
    root = SHORTS_DIR / slug
    enriched = dict(plan)
    if (root / "detail_preview.html").is_file():
        enriched["detail_ready"] = True
        enriched["detail_file"] = "detail_preview.html"
        enriched["detail_smartstore_file"] = "detail_smartstore.html"
    if (root / "detail_analysis.json").is_file():
        enriched["detail_analysis_file"] = "detail_analysis.json"
        enriched["detail_analyzed"] = True
    return enriched


def _enrich_plan(slug: str, plan: dict) -> dict:
    plan = _enrich_plan_video(slug, plan)
    plan = _enrich_plan_detail(slug, plan)
    return plan


def _enrich_plan_video(slug: str, plan: dict) -> dict:
    """plan.json에 video_file이 없어도 디스크에 MP4가 있으면 표시."""
    if plan.get("video_file"):
        return plan
    root = SHORTS_DIR / slug
    for name in ("shorts.mp4", "video.mp4"):
        if (root / name).is_file():
            enriched = dict(plan)
            enriched["video_file"] = name
            enriched["video_ready"] = True
            return enriched
    return plan


def _list_projects(*, product_id: str | None = None) -> list[dict]:
    items = []
    if not SHORTS_DIR.is_dir():
        return items
    pid_filter = (product_id or "").strip().lower()
    for d in sorted(SHORTS_DIR.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
        if not d.is_dir():
            continue
        plan_path = d / "plan.json"
        if not plan_path.is_file():
            continue
        try:
            plan = json.loads(plan_path.read_text(encoding="utf-8"))
            plan = _enrich_plan_detail(d.name, plan)
            row = {
                "slug": d.name,
                "title": plan.get("video_title") or d.name,
                "topic": plan.get("video_title") or d.name,
                "product_id": plan.get("product_id", ""),
                "keywords": plan.get("input_keywords") or [],
                "scenes": len(plan.get("scenes") or []),
                "fallback": bool(plan.get("_fallback")),
                "detail_ready": bool(plan.get("detail_ready")),
                "detail_analyzed": bool(plan.get("detail_analyzed")),
            }
            if pid_filter and str(row["product_id"]).lower() != pid_filter:
                continue
            items.append(row)
        except Exception:
            row = {"slug": d.name, "title": d.name, "product_id": "", "keywords": [], "scenes": 0}
            if pid_filter and str(row["product_id"]).lower() != pid_filter:
                continue
            items.append(row)
    return items


def _run_generate_images(slug: str) -> dict:
    plan_path = SHORTS_DIR / slug / "plan.json"
    if not plan_path.is_file():
        raise FileNotFoundError(f"프로젝트 없음: {slug}")
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    out_dir = SHORTS_DIR / slug

    def _log(msg: str) -> None:
        print(msg, flush=True)

    loop = asyncio.new_event_loop()
    try:
        from shorts_factory.images import attach_storyboard_images
        from shorts_factory.render import write_outputs

        plan = loop.run_until_complete(
            attach_storyboard_images(plan, out_dir, log=_log, force=True)
        )
        write_outputs(plan, slug)
    finally:
        loop.close()
    return {"ok": True, "slug": slug, "plan": plan}


def _run_resize_scenes(slug: str, scenes: int) -> dict:
    """슬라이더로 장면 수만 바꿀 때 plan.json 을 패딩/트림 후 보드에 반영."""
    from shorts_factory.generator import SCENE_MAX, SCENE_MIN, _ensure_scene_count, load_products

    plan_path = SHORTS_DIR / slug / "plan.json"
    if not plan_path.is_file():
        raise FileNotFoundError(f"프로젝트 없음: {slug}")
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    product_id = str(plan.get("product_id") or "living").lower()
    product = load_products().get(product_id)
    if not product:
        raise ValueError(f"알 수 없는 제품: {product_id}")

    kw = plan.get("input_keywords") or []
    if isinstance(kw, str):
        kw = [p.strip() for p in kw.split(",") if p.strip()]
    elif not isinstance(kw, list):
        kw = []

    scene_n = max(SCENE_MIN, min(SCENE_MAX, int(scenes)))
    plan = _ensure_scene_count(
        plan,
        product,
        kw,
        scene_n,
        topic=str(plan.get("topic") or ""),
        hook=str(plan.get("hook") or plan.get("hook_line") or ""),
    )
    plan_path.write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
    plan = _enrich_plan(slug, plan)
    return {"ok": True, "slug": slug, "plan": plan}


def _run_detail(
    slug: str,
    *,
    use_llm: bool = False,
    strategy: str | None = None,
    competitor_notes: str = "",
    selected_hook: str | None = None,
) -> dict:
    global _detail_busy
    with _detail_lock:
        if _detail_busy:
            raise RuntimeError("이미 상세페이지 생성 중입니다. 잠시 후 다시 시도하세요.")
        _detail_busy = True
    try:
        plan_path = SHORTS_DIR / slug / "plan.json"
        if not plan_path.is_file():
            raise FileNotFoundError(f"프로젝트 없음: {slug}")
        plan = json.loads(plan_path.read_text(encoding="utf-8"))
        out_dir = SHORTS_DIR / slug

        def _log(msg: str) -> None:
            print(msg, flush=True)

        from shorts_factory.detail import write_detail_outputs_async

        loop = asyncio.new_event_loop()
        try:
            result = loop.run_until_complete(
                write_detail_outputs_async(
                    plan,
                    slug,
                    out_dir,
                    use_llm=use_llm,
                    strategy=strategy,
                    competitor_notes=competitor_notes,
                    selected_hook=selected_hook,
                    log=_log,
                )
            )
        finally:
            loop.close()
        return {
            "ok": True,
            "slug": slug,
            "plan": _enrich_plan(slug, result.get("plan") or plan),
            "images_used": result.get("images_used", 0),
            "analysis": result.get("analysis"),
            "applied": True,
        }
    finally:
        with _detail_lock:
            _detail_busy = False


def _run_render_video(slug: str) -> dict:
    global _video_busy
    with _video_lock:
        if _video_busy:
            raise RuntimeError("이미 영상 렌더 중입니다. 잠시 후 다시 시도하세요.")
        _video_busy = True
    try:
        def _log(msg: str) -> None:
            print(msg, flush=True)

        from shorts_factory.video import render_slug_video

        result = render_slug_video(slug, shorts_root=SHORTS_DIR, log=_log)
        if not result.get("ok"):
            raise RuntimeError(result.get("error") or "영상 렌더 실패")
        plan = _enrich_plan(slug, result.get("plan") or {})
        return {
            "ok": True,
            "slug": slug,
            "plan": plan,
            "video_file": plan.get("video_file") or result.get("video_file"),
        }
    finally:
        with _video_lock:
            _video_busy = False


def _run_generate(body: dict) -> dict:
    global _gen_busy
    with _gen_lock:
        if _gen_busy:
            raise RuntimeError("이미 생성 중입니다. 잠시 후 다시 시도하세요.")
        _gen_busy = True
    try:
        product_id = (body.get("product") or "living").strip().lower()
        keywords = body.get("keywords") or ""
        if isinstance(keywords, list):
            kw_str = ", ".join(keywords)
        else:
            kw_str = str(keywords)
        scenes = int(body.get("scenes") or 4)
        # 기본: 빠른 템플릿 콘티 (체크 시에만 LLM / Fable)
        use_llm = body.get("use_llm", False)
        if isinstance(use_llm, str):
            use_llm = use_llm.lower() not in ("0", "false", "no")
        else:
            use_llm = bool(use_llm)
        use_fable_loop = body.get("use_fable_loop", False)
        if isinstance(use_fable_loop, str):
            use_fable_loop = use_fable_loop.lower() not in ("0", "false", "no")
        else:
            use_fable_loop = bool(use_fable_loop)
        max_fable_iterations = int(
            body.get("max_fable_iterations")
            or os.environ.get("SHORTS_STUDIO_FABLE_ITERS", "2")
        )
        use_images = body.get("use_images", False)
        if isinstance(use_images, str):
            use_images = use_images.lower() not in ("0", "false", "no")
        else:
            use_images = bool(use_images)
        use_video = body.get("use_video", False)
        if isinstance(use_video, str):
            use_video = use_video.lower() not in ("0", "false", "no")
        else:
            use_video = bool(use_video)
        topic = (body.get("topic") or "").strip()
        hook = (body.get("hook") or "").strip()
        shopping_shorts = body.get("shopping_shorts", False)
        if isinstance(shopping_shorts, str):
            shopping_shorts = shopping_shorts.lower() not in ("0", "false", "no")
        else:
            shopping_shorts = bool(shopping_shorts)

        from shorts_factory.generator import generate_shorts_plan
        from shorts_factory.render import write_outputs_async

        def _log(msg: str) -> None:
            print(msg, flush=True)

        loop = asyncio.new_event_loop()
        try:
            plan = loop.run_until_complete(
                generate_shorts_plan(
                    product_id=product_id,
                    keywords=kw_str,
                    topic=topic,
                    hook=hook,
                    scenes=scenes,
                    use_llm=use_llm,
                    use_fable_loop=use_fable_loop,
                    max_fable_iterations=max_fable_iterations,
                    shopping_shorts_mode=shopping_shorts,
                    log=_log,
                )
            )
            slug = (body.get("slug") or "").strip() or _slug(
                product_id, plan.get("video_title") or topic
            )
            out = loop.run_until_complete(
                write_outputs_async(plan, slug, use_images=use_images, log=_log)
            )
            plan = json.loads((out / "plan.json").read_text(encoding="utf-8"))
            if use_video:
                from shorts_factory.video import render_plan_video

                _log("MP4 영상 합성 시작…")
                vr = render_plan_video(plan, out, log=_log)
                if vr.get("ok"):
                    plan = vr.get("plan") or plan
                    (out / "plan.json").write_text(
                        json.dumps(plan, ensure_ascii=False, indent=2),
                        encoding="utf-8",
                    )
                else:
                    plan["_video_error"] = vr.get("error", "영상 렌더 실패")
        finally:
            loop.close()
        return {"ok": True, "slug": slug, "plan": plan, "path": str(out)}
    finally:
        with _gen_lock:
            _gen_busy = False


def _run_shopping_pipeline(body: dict) -> dict:
    """쇼핑쇼츠 전용 — 콘티(쇼핑 모드) → 스토리보드 → 상세 HTML."""
    payload = dict(body or {})
    payload["shopping_shorts"] = True
    steps: list[str] = []
    gen = _run_generate(payload)
    slug = gen["slug"]
    plan = gen["plan"]
    steps.append("conti")

    img = _run_generate_images(slug)
    plan = img.get("plan") or plan
    steps.append("board")

    raw_md = payload.get("make_detail", True)
    if isinstance(raw_md, str):
        make_detail = raw_md.lower() not in ("0", "false", "no")
    else:
        make_detail = bool(raw_md) if raw_md is not None else True

    detail_result = None
    if make_detail:
        detail_result = _run_detail(
            slug,
            use_llm=bool(payload.get("use_llm_detail", False)),
            strategy=(payload.get("strategy") or "").strip() or None,
            competitor_notes=str(payload.get("competitor_notes") or ""),
            selected_hook=(payload.get("hook") or payload.get("selected_hook") or "").strip() or None,
        )
        plan = detail_result.get("plan") or plan
        steps.append("detail")

    return {
        "ok": True,
        "slug": slug,
        "plan": plan,
        "steps": steps,
        "shopping_shorts": True,
        "detail": detail_result if detail_result else None,
        "preview_url": f"http://127.0.0.1:{DEFAULT_PORT}/{slug}/detail_preview.html"
        if (plan.get("detail_ready") or (detail_result and detail_result.get("plan", {}).get("detail_ready")))
        else None,
    }


def _resolve_slug_dir(slug: str) -> Path | None:
    slug = (slug or "").strip().strip("/")
    if not slug or ".." in slug.replace("\\", "/"):
        return None
    root = SHORTS_DIR.resolve()
    target = (SHORTS_DIR / slug).resolve()
    if not str(target).startswith(str(root)) or not target.is_dir():
        return None
    return target


def _safe_attachment_name(name: str) -> str:
    ascii_name = re.sub(r"[^\x20-\x7E]+", "_", name).strip("._") or "download"
    return ascii_name


def _build_detail_zip(slug_dir: Path) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name in (
            "detail_preview.html",
            "detail_smartstore.html",
            "detail.json",
            "detail_analysis.json",
        ):
            p = slug_dir / name
            if p.is_file():
                zf.write(p, name)
        images_dir = slug_dir / "images"
        if images_dir.is_dir():
            for img in sorted(images_dir.rglob("*")):
                if img.is_file():
                    arc = img.relative_to(slug_dir).as_posix()
                    zf.write(img, arc)
    return buf.getvalue()


def _inject_detail_download_nav(html: str, slug: str) -> str:
    if not slug or "data-detail-download" in html:
        return html
    enc = quote(slug, safe="")
    btn = "margin-left:8px;padding:4px 10px;background:#1e40af;border-radius:6px;color:#fff;font-size:13px;text-decoration:none;"
    links = (
        f'<span class="dl-actions" data-detail-download>'
        f'<a style="{btn}" href="/api/detail/download?slug={enc}&amp;kind=zip">ZIP 다운로드</a>'
        f'<a style="{btn}" href="/api/detail/download?slug={enc}&amp;kind=html">HTML 저장</a>'
        f"</span>"
    )
    return re.sub(r"</strong>\s*</nav>", f"</strong>{links}</nav>", html, count=1)


class ExclusiveThreadingHTTPServer(ThreadingHTTPServer):
    """Windows에서 SO_REUSEADDR로 동일 포트 이중 LISTEN 되는 문제 방지."""

    allow_reuse_address = False

    def server_bind(self) -> None:
        if sys.platform == "win32":
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass

    def _send_json(self, data: dict, status: int = 200) -> None:
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self) -> dict:
        n = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(n) if n else b"{}"
        return json.loads(raw.decode("utf-8") or "{}")

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        qs = parse_qs(urlparse(self.path).query)

        if path == "/api/detail/download":
            slug = (qs.get("slug") or [""])[0].strip()
            slug_dir = _resolve_slug_dir(slug)
            if not slug_dir or not (slug_dir / "detail_preview.html").is_file():
                self.send_error(404)
                return
            kind = (qs.get("kind") or ["zip"])[0].lower()
            base = slug_dir.name
            if kind == "html":
                data = (slug_dir / "detail_preview.html").read_bytes()
                self._serve_attachment(data, f"{base}_detail_preview.html", "text/html; charset=utf-8")
                return
            data = _build_detail_zip(slug_dir)
            self._serve_attachment(data, f"{base}_detail.zip", "application/zip")
            return
        if path == "/api/status":
            lite = (qs.get("lite") or [""])[0].lower() in ("1", "true", "yes")
            if lite:
                self._send_json(
                    {
                        "busy": _gen_busy,
                        "video_busy": _video_busy,
                        "detail_busy": _detail_busy,
                        "bootstrap_v": 1 if _bootstrap_cache is not None else 0,
                    }
                )
                return
            self._send_json(
                {
                    "busy": _gen_busy,
                    "video_busy": _video_busy,
                    "detail_busy": _detail_busy,
                    "fable_local": _get_fable_status(),
                }
            )
            return
        if path == "/api/bootstrap":
            try:
                self._send_json(_get_bootstrap_payload())
            except Exception as e:
                import traceback

                traceback.print_exc()
                self._send_json({"ok": False, "error": str(e)}, 500)
            return

        if path in ("/", "/studio", "/studio.html", "/index.html"):
            self._serve_file(
                SHORTS_DIR / "studio.html",
                "text/html; charset=utf-8",
                no_cache=True,
            )
            return
        if path in ("/detail", "/detail/", "/detail/index.html"):
            target = DETAIL_PAGE_DIR / "index.html"
            if target.is_file():
                self._serve_file(target, "text/html; charset=utf-8", no_cache=True)
                return
            self.send_error(404)
            return
        if path in ("/shopping", "/shopping/", "/shopping/index.html"):
            target = SHOPPING_SHORTS_DIR / "index.html"
            if target.is_file():
                self._serve_file(target, "text/html; charset=utf-8")
                return
            self.send_error(404)
            return
        if path in ("/evolution", "/evolution/", "/evolution/index.html"):
            target = VIDEO_EVOLUTION_DIR / "index.html"
            if target.is_file():
                self._serve_file(target, "text/html; charset=utf-8")
                return
            self.send_error(404)
            return
        if path in ("/guide/mv-flow", "/guide/mv-flow/", "/guide/mv-flow/index.html"):
            target = MV_GUIDE_DIR / "index.html"
            if target.is_file():
                self._serve_file(target, "text/html; charset=utf-8")
                return
            self.send_error(404)
            return
        if path in ("/guide/super-agents", "/guide/super-agents/", "/guide/super-agents/index.html"):
            target = SUPER_AGENTS_GUIDE_DIR / "index.html"
            if target.is_file():
                self._serve_file(target, "text/html; charset=utf-8")
                return
            self.send_error(404)
            return
        if path in ("/sangseopage", "/sangseopage/", "/detail-architect", "/detail-architect.html"):
            loc = "/detail/"
            q = urlparse(self.path).query
            if q:
                loc += "?" + q
            self.send_response(302)
            self.send_header("Location", loc)
            self.end_headers()
            return
        if path == "/api/detail/planning":
            if PLANNING_PATH.is_file():
                self._send_json(json.loads(PLANNING_PATH.read_text(encoding="utf-8")))
            else:
                self._send_json({"pillars": [], "strategies": []})
            return
        if path == "/api/detail/analyze":
            slug = (qs.get("slug") or [""])[0].strip()
            if not slug:
                self._send_json({"error": "slug 필요"}, 400)
                return
            plan_path = SHORTS_DIR / slug / "plan.json"
            if not plan_path.is_file():
                self._send_json({"error": "not found"}, 404)
                return
            plan = json.loads(plan_path.read_text(encoding="utf-8"))
            strategy = (qs.get("strategy") or [""])[0].strip() or None
            notes = (qs.get("competitor_notes") or [""])[0]
            hook = (qs.get("selected_hook") or [""])[0].strip() or None
            from shorts_factory.competitor_analyzer import load_competitor_benchmark
            from shorts_factory.detail_analyzer import analyze_detail_plan, save_analysis

            benchmark = load_competitor_benchmark(SHORTS_DIR / slug)
            analysis = analyze_detail_plan(
                plan,
                strategy_override=strategy,
                competitor_notes=notes,
                competitor_benchmark=benchmark,
                selected_hook=hook,
            )
            save_analysis(SHORTS_DIR / slug, analysis)
            self._send_json({"ok": True, "slug": slug, "analysis": analysis})
            return
        if path == "/api/products":
            self._send_json({"products": _load_products_data()})
            return
        if path == "/api/brand":
            self._send_json({"brand": _load_brand_data()})
            return
        if path == "/api/video-studios":
            self._send_json({"video_studios": _load_video_studios_data()})
            return
        if path == "/api/malva-hub":
            self._send_json({"malva_hub": _load_malva_hub_data()})
            return
        if path == "/api/shopping-shorts-hub":
            self._send_json({"shopping_shorts_hub": _load_shopping_shorts_hub_data()})
            return
        if path == "/api/youtube/evolution":
            from shorts_factory.youtube_learner import load_evolution

            self._send_json({"ok": True, "evolution": load_evolution()})
            return
        if path in ("/api/playbooks/mv-flow", "/api/playbooks/lV9UzdYkT20"):
            if PLAYBOOK_MV_PATH.is_file():
                self._send_json({"ok": True, "playbook": json.loads(PLAYBOOK_MV_PATH.read_text(encoding="utf-8"))})
            else:
                self._send_json({"ok": False, "error": "playbook not found"}, 404)
            return
        if path in ("/api/playbooks/super-agents", "/api/playbooks/Ovj5f0ajDww"):
            if PLAYBOOK_SUPER_AGENTS_PATH.is_file():
                self._send_json({
                    "ok": True,
                    "playbook": json.loads(PLAYBOOK_SUPER_AGENTS_PATH.read_text(encoding="utf-8")),
                })
            else:
                self._send_json({"ok": False, "error": "playbook not found"}, 404)
            return
        if path == "/api/stock/sources":
            from shorts_factory.stock_video import api_key_status, load_sources

            data = load_sources()
            data["api_keys"] = api_key_status()
            self._send_json({"ok": True, "stock": data})
            return
        if path == "/api/stock/search":
            q = (qs.get("q") or qs.get("query") or [""])[0].strip()
            source = (qs.get("source") or ["pexels"])[0].strip().lower()
            if not q:
                self._send_json({"error": "q(검색어) 필요"}, 400)
                return
            from shorts_factory.stock_video import browse_links, search_stock

            result = search_stock(source, q)
            result["browse_links"] = browse_links(q)
            self._send_json(result)
            return
        if path == "/api/stock/clips":
            slug = (qs.get("slug") or [""])[0].strip()
            if not slug:
                self._send_json({"error": "slug 필요"}, 400)
                return
            from shorts_factory.stock_video import list_local_clips

            self._send_json(list_local_clips(slug, SHORTS_DIR))
            return
        if path == "/api/stock/browse":
            q = (qs.get("q") or [""])[0].strip() or "lifestyle"
            from shorts_factory.stock_video import browse_links

            self._send_json({"ok": True, "query": q, "links": browse_links(q)})
            return
        if path == "/api/projects":
            product = (qs.get("product") or [""])[0].strip().lower()
            try:
                self._send_json(
                    {"projects": _list_projects(product_id=product or None)}
                )
            except Exception as e:
                import traceback

                traceback.print_exc()
                self._send_json({"error": str(e), "projects": []}, 500)
            return
        if path == "/api/plan":
            slug = (qs.get("slug") or [""])[0]
            plan_path = SHORTS_DIR / slug / "plan.json"
            if not plan_path.is_file():
                self._send_json({"error": "not found"}, 404)
                return
            plan = json.loads(plan_path.read_text(encoding="utf-8"))
            plan = _enrich_plan(slug, plan)
            self._send_json({"slug": slug, "plan": plan})
            return
        if path == "/api/javis/health":
            self._send_json(
                {
                    "ok": True,
                    "service": "loopreel_detail_studio",
                    "port": DEFAULT_PORT,
                    "detail_ui": "/detail/",
                }
            )
            return
        if path == "/api/javis/voice-help":
            from shorts_factory.jarvis_detail_voice import voice_help

            self._send_json(voice_help())
            return
        if path == "/api/javis/projects":
            from shorts_factory.jarvis_detail_voice import (
                _list_projects as javis_list_projects,
            )

            self._send_json({"ok": True, "projects": javis_list_projects()})
            return
        if path == "/api/fable":
            self._send_json(_get_fable_status())
            return
        rel = unquote(path.lstrip("/"))
        target = (SHORTS_DIR / rel).resolve()
        if not str(target).startswith(str(SHORTS_DIR.resolve())):
            self.send_error(403)
            return
        if target.is_file():
            ctype = "application/octet-stream"
            if target.suffix == ".html":
                ctype = "text/html; charset=utf-8"
            elif target.suffix == ".json":
                ctype = "application/json; charset=utf-8"
            elif target.suffix == ".md":
                ctype = "text/plain; charset=utf-8"
            elif target.suffix == ".mp4":
                ctype = "video/mp4"
            force_dl = (qs.get("download") or [""])[0].lower() in ("1", "true", "yes")
            if target.name == "detail_preview.html":
                slug_part = rel.rsplit("/", 1)[0] if "/" in rel else ""
                if force_dl:
                    self._serve_attachment(
                        target.read_bytes(),
                        f"{Path(rel).parent.name or 'detail'}_detail_preview.html",
                        "text/html; charset=utf-8",
                    )
                    return
                text = target.read_text(encoding="utf-8")
                injected = _inject_detail_download_nav(text, slug_part)
                if injected != text:
                    self._serve_bytes(injected.encode("utf-8"), ctype, no_cache=True)
                    return
            self._serve_file(target, ctype, no_cache=target.suffix in (".html", ".json"))
            return

        self.send_error(404)

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        if path == "/api/javis/start":
            try:
                body = self._read_json()
                from shorts_factory.jarvis_detail_voice import handle_javis_start

                result = handle_javis_start(body)
                if result.get("open_browser") and result.get("url"):
                    import webbrowser

                    webbrowser.open(result["url"])
                self._send_json(result)
            except Exception as e:
                self._send_json({"ok": False, "error": str(e), "speech": str(e)}, 500)
            return
        if path == "/api/shopping/pipeline":
            try:
                body = self._read_json()
                result = _run_shopping_pipeline(body)
                self._send_json(result)
            except Exception as e:
                self._send_json({"ok": False, "error": str(e)}, 500)
            return
        if path == "/api/youtube/learn":
            try:
                body = self._read_json()
                url = (body.get("url") or "").strip()
                if not url:
                    raise ValueError("url 필요")
                from shorts_factory.youtube_learner import learn_from_url

                result = learn_from_url(url)
                self._send_json(result)
            except Exception as e:
                self._send_json({"ok": False, "error": str(e)}, 500)
            return
        if path == "/api/youtube/evolve-seed":
            try:
                from shorts_factory.youtube_learner import seed_from_brand

                result = seed_from_brand()
                self._send_json(result)
            except Exception as e:
                self._send_json({"ok": False, "error": str(e)}, 500)
            return
        if path == "/api/generate":
            try:
                body = self._read_json()
                result = _run_generate(body)
                self._send_json(result)
            except Exception as e:
                self._send_json({"ok": False, "error": str(e)}, 500)
            return
        if path == "/api/resize-scenes":
            try:
                body = self._read_json()
                slug = (body.get("slug") or "").strip()
                if not slug:
                    raise ValueError("slug 필요")
                scenes = int(body.get("scenes") or 4)
                result = _run_resize_scenes(slug, scenes)
                self._send_json(result)
            except Exception as e:
                self._send_json({"ok": False, "error": str(e)}, 500)
            return
        if path == "/api/images":
            try:
                body = self._read_json()
                slug = (body.get("slug") or "").strip()
                if not slug:
                    raise ValueError("slug 필요")
                result = _run_generate_images(slug)
                self._send_json(result)
            except Exception as e:
                self._send_json({"ok": False, "error": str(e)}, 500)
            return
        if path == "/api/detail":
            try:
                body = self._read_json()
                slug = (body.get("slug") or "").strip()
                if not slug:
                    raise ValueError("slug 필요")
                use_llm = body.get("use_llm", False)
                if isinstance(use_llm, str):
                    use_llm = use_llm.lower() not in ("0", "false", "no")
                else:
                    use_llm = bool(use_llm)
                strategy = (body.get("strategy") or "").strip() or None
                competitor_notes = str(body.get("competitor_notes") or "")
                selected_hook = (body.get("selected_hook") or "").strip() or None
                result = _run_detail(
                    slug,
                    use_llm=use_llm,
                    strategy=strategy,
                    competitor_notes=competitor_notes,
                    selected_hook=selected_hook,
                )
                self._send_json(result)
            except Exception as e:
                self._send_json({"ok": False, "error": str(e)}, 500)
            return
        if path == "/api/detail/analyze":
            try:
                body = self._read_json()
                slug = (body.get("slug") or "").strip()
                if not slug:
                    raise ValueError("slug 필요")
                plan_path = SHORTS_DIR / slug / "plan.json"
                if not plan_path.is_file():
                    raise FileNotFoundError(f"프로젝트 없음: {slug}")
                plan = json.loads(plan_path.read_text(encoding="utf-8"))
                strategy = (body.get("strategy") or "").strip() or None
                notes = str(body.get("competitor_notes") or "")
                selected_hook = (body.get("selected_hook") or "").strip() or None
                from shorts_factory.competitor_analyzer import (
                    analyze_competitor_urls,
                    load_competitor_benchmark,
                    save_competitor_benchmark,
                )
                from shorts_factory.detail_analyzer import analyze_detail_plan, save_analysis

                out_dir = SHORTS_DIR / slug
                benchmark = load_competitor_benchmark(out_dir)
                urls = body.get("competitor_urls") or []
                own_url = (body.get("own_product_url") or "").strip()
                manual_by_url = body.get("manual_by_url") or {}
                manual_texts = body.get("manual_texts") or []
                own_manual = (body.get("own_manual_text") or "").strip() or None
                if urls or own_url or own_manual:
                    benchmark = analyze_competitor_urls(
                        urls,
                        manual_by_url=manual_by_url,
                        manual_texts=manual_texts,
                        own_product_url=own_url or None,
                        own_manual_text=own_manual,
                    )
                    save_competitor_benchmark(out_dir, benchmark)

                analysis = analyze_detail_plan(
                    plan,
                    strategy_override=strategy,
                    competitor_notes=notes,
                    competitor_benchmark=benchmark,
                    selected_hook=selected_hook,
                )
                save_analysis(out_dir, analysis)
                self._send_json({"ok": True, "slug": slug, "analysis": analysis, "benchmark": benchmark, "applied": False})
            except Exception as e:
                self._send_json({"ok": False, "error": str(e)}, 500)
            return
        if path == "/api/detail/competitors":
            try:
                body = self._read_json()
                slug = (body.get("slug") or "").strip()
                urls = body.get("urls") or []
                own_url = (body.get("own_product_url") or "").strip()
                manual_by_url = body.get("manual_by_url") or {}
                manual_texts = body.get("manual_texts") or []
                own_manual = (body.get("own_manual_text") or "").strip() or None
                if not urls and not own_url and not own_manual:
                    raise ValueError("타사 URL 또는 우리 제품 URL·수동 텍스트를 1개 이상 입력하세요")
                from shorts_factory.competitor_analyzer import (
                    analyze_competitor_urls,
                    load_competitor_benchmark,
                    merge_competitor_benchmark,
                    save_competitor_benchmark,
                )

                scope = (body.get("scope") or "all").strip().lower()
                existing = load_competitor_benchmark(SHORTS_DIR / slug) if slug else None
                if scope == "own":
                    urls = []
                elif scope == "competitors":
                    own_url = ""
                    own_manual = None

                benchmark = analyze_competitor_urls(
                    urls,
                    manual_by_url=manual_by_url,
                    manual_texts=manual_texts,
                    own_product_url=own_url or None,
                    own_manual_text=own_manual,
                )
                if existing and scope in ("own", "competitors"):
                    benchmark = merge_competitor_benchmark(existing, benchmark, scope=scope)
                if slug:
                    save_competitor_benchmark(SHORTS_DIR / slug, benchmark)
                self._send_json({"ok": True, "slug": slug or None, "benchmark": benchmark})
            except Exception as e:
                self._send_json({"ok": False, "error": str(e)}, 500)
            return
        if path == "/api/video":
            try:
                body = self._read_json()
                slug = (body.get("slug") or "").strip()
                if not slug:
                    raise ValueError("slug 필요")
                result = _run_render_video(slug)
                self._send_json(result)
            except Exception as e:
                self._send_json({"ok": False, "error": str(e)}, 500)
            return
        if path == "/api/stock/download":
            try:
                body = self._read_json()
                slug = (body.get("slug") or "").strip()
                if not slug:
                    raise ValueError("slug 필요")
                from shorts_factory.stock_video import download_clip

                result = download_clip(
                    slug,
                    source=str(body.get("source") or "pexels"),
                    download_url=str(body.get("download_url") or ""),
                    scene_no=body.get("scene_no"),
                    title=str(body.get("title") or ""),
                    video_id=body.get("video_id"),
                    shorts_root=SHORTS_DIR,
                )
                self._send_json(result)
            except Exception as e:
                self._send_json({"ok": False, "error": str(e)}, 500)
            return
        if path == "/api/stock/assign":
            try:
                body = self._read_json()
                slug = (body.get("slug") or "").strip()
                scene_no = int(body.get("scene_no") or 0)
                filename = str(body.get("filename") or "").strip()
                if not slug or not scene_no or not filename:
                    raise ValueError("slug, scene_no, filename 필요")
                from shorts_factory.stock_video import assign_scene

                self._send_json(assign_scene(slug, scene_no, filename, SHORTS_DIR))
            except Exception as e:
                self._send_json({"ok": False, "error": str(e)}, 500)
            return
        if path == "/api/products":
            try:
                body = self._read_json()
                result = _add_product(body)
                self._send_json(result)
            except Exception as e:
                self._send_json({"ok": False, "error": str(e)}, 500)
            return
        self.send_error(404)

    def _serve_bytes(self, data: bytes, ctype: str, *, no_cache: bool = False) -> None:
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        if no_cache:
            self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
            self.send_header("Pragma", "no-cache")
        self.end_headers()
        self.wfile.write(data)

    def _serve_file(self, path: Path, ctype: str, *, no_cache: bool = False) -> None:
        self._serve_bytes(path.read_bytes(), ctype, no_cache=no_cache)

    def _serve_attachment(self, data: bytes, filename: str, ctype: str) -> None:
        ascii_name = _safe_attachment_name(filename)
        disp = f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(filename)}"
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Content-Disposition", disp)
        self.end_headers()
        self.wfile.write(data)


def main() -> None:
    port = DEFAULT_PORT
    if len(sys.argv) > 1:
        try:
            port = int(sys.argv[1])
        except ValueError:
            pass
    SHORTS_DIR.mkdir(parents=True, exist_ok=True)
    url = f"http://127.0.0.1:{port}/"
    # 포트 바인딩 전에 bootstrap 캐시를 준비 — 바인딩 후 serve_forever() 전 워밍 시 HTTP가 응답하지 않음
    try:
        _warm_bootstrap_cache()
    except Exception as e:
        print(f"[bootstrap] 초기 캐시 준비 실패: {e}", file=sys.stderr)
    try:
        httpd = ExclusiveThreadingHTTPServer(("", port), Handler)
    except OSError as e:
        win_busy = getattr(e, "winerror", None) == 10048
        posix_busy = getattr(e, "errno", None) in (98, 48)
        if win_busy or posix_busy:
            print(f"포트 {port} 사용 중: {url}", file=sys.stderr)
            if not os.environ.get("SHORTS_STUDIO_NO_AUTO_BROWSER"):
                webbrowser.open(url)
            sys.exit(1)
        raise
    brand = _load_brand_data()
    print(f"{brand.get('name', '루프릴')} LoopReel: {url}")
    print("종료: 이 창을 닫거나 Ctrl+C")
    threading.Thread(target=_warm_fable_cache, daemon=True).start()
    if not os.environ.get("SHORTS_STUDIO_NO_AUTO_BROWSER"):
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n서버 종료")


if __name__ == "__main__":
    main()
