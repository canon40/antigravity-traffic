# -*- coding: utf-8 -*-
"""
키워드 → 제목·개요·본문·이미지(키워드 맞춤) 생성 후 drafts/ 에 저장.
네이버 로그인·Playwright 없이 원고만 뽑을 때 사용.

  python draft_blog.py --keyword "자동차 유리막 코팅"
  python draft_blog.py --keyword "욕실 타일 코팅" --post-type "제품 홍보"
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import shutil
import sys
from datetime import datetime

_ROOT = os.path.dirname(os.path.abspath(__file__))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

os.environ.setdefault("BLOG_API_SPARING", "0")
os.environ.setdefault("BLOG_TEXT_PROVIDER", os.environ.get("BLOG_TEXT_PROVIDER", "gemini"))
os.environ.setdefault("BLOG_IMAGE_PROVIDER", os.environ.get("BLOG_IMAGE_PROVIDER", "genai"))

_TEXT_MAP = {
    "Gemini API (유료)": "gemini",
    "Gemini API (유료·현재 기본)": "gemini",
    "로컬 Ollama (무료)": "ollama",
    "클로드 코드 (Claude Code)": "claude",
    "자동 (Ollama → Gemini)": "auto",
}
_IMAGE_MAP = {
    "Gen AI (Gemini 이미지)": "genai",
    "Gen AI": "genai",
    "자동 (Gen AI → Vertex → 무료)": "auto",
    "자동 (Gen AI → Vertex)": "auto",
    "로컬 무료 (Pollinations)": "free",
    "로컬 무료 (Pollinations → Pillow)": "free",
    "Pillow 플레이스홀더 (테스트용)": "pillow",
    "Pillow 플레이스홀더": "pillow",
    "Vertex AI": "vertex",
}


def _log(msg: str) -> None:
    line = str(msg)
    if sys.platform == "win32":
        enc = sys.stdout.encoding or "utf-8"
        try:
            print(line.encode(enc, errors="replace").decode(enc, errors="replace"), flush=True)
        except Exception:
            print(line, flush=True)
    else:
        print(line, flush=True)


def _slug(s: str, max_len: int = 40) -> str:
    s = re.sub(r"[^\w가-힣]+", "_", (s or "").strip())
    return (s[:max_len] or "draft").strip("_")


def load_preset() -> dict:
    path = os.path.join(_ROOT, "accounts.json")
    data = {}
    if os.path.isfile(path):
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    tp_label = data.get("text_provider") or "로컬 Ollama (무료)"
    ip_label = data.get("image_provider") or "Gen AI (Gemini 이미지)"
    keywords_raw = data.get("keywords") or data.get("keyword") or ""
    if isinstance(keywords_raw, str):
        keywords = [k.strip() for k in keywords_raw.split(",") if k.strip()]
    else:
        keywords = list(keywords_raw or [])
    return {
        "gemini_key": (data.get("gemini_key") or "").strip(),
        "vertex_api_key": (data.get("vertex_api_key") or "").strip(),
        "vertex_project_id": (data.get("vertex_project_id") or "").strip(),
        "vertex_json": data.get("vertex_json") or "",
        "master_guidelines": (data.get("master_guidelines") or "").strip(),
        "post_type": (data.get("post_type") or "자동차 정보").strip(),
        "product_choice": (data.get("product_choice") or "none").strip(),
        "keywords": keywords,
        "text_provider": _TEXT_MAP.get(tp_label, tp_label if tp_label in _TEXT_MAP.values() else "ollama"),
        "image_provider": _IMAGE_MAP.get(ip_label, ip_label if ip_label in _IMAGE_MAP.values() else "genai"),
        "writing_guidelines": "",
    }


def build_config(preset: dict, *, keyword: str, post_type: str | None) -> dict:
    cfg = dict(preset)
    cfg["post_type"] = (post_type or preset.get("post_type") or "자동차 정보").strip()
    cfg["keywords"] = [keyword]
    return cfg


def save_draft(
    *,
    keyword: str,
    title: str,
    outline: str,
    body: str,
    tags: str,
    image_desc: str,
    image_paths: list[str],
) -> str:
    drafts_dir = os.path.join(_ROOT, "drafts")
    os.makedirs(drafts_dir, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    base = f"{stamp}_{_slug(keyword)}"
    draft_img_dir = os.path.join(drafts_dir, base)
    os.makedirs(draft_img_dir, exist_ok=True)

    copied: list[str] = []
    for i, src in enumerate(image_paths or []):
        if not src or not os.path.isfile(src):
            continue
        ext = os.path.splitext(src)[1] or ".png"
        dest = os.path.join(draft_img_dir, f"image_{i + 1}{ext}")
        shutil.copy2(src, dest)
        copied.append(dest)

    md_path = os.path.join(drafts_dir, f"{base}.md")
    img_lines = "\n".join(f"![image_{i + 1}]({os.path.relpath(p, drafts_dir).replace(chr(92), '/')})" for i, p in enumerate(copied))
    content = f"""---
keyword: {keyword}
title: {title}
tags: {tags}
images: {len(copied)}
created: {datetime.now().isoformat(timespec='seconds')}
image_desc: {image_desc[:200]}
---

# {title}

**태그:** {tags}

## 개요

{outline}

## 본문

{body}

## 이미지 (키워드·개요 기반)

{img_lines or '(이미지 생성 실패 — GUI에서 Gemini API 키·이미지 엔진 확인)'}
"""
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(content)
    return md_path


async def run_draft(keyword: str, post_type: str | None) -> str:
    from drawer.registry import get_content_gen
    from drawer.wiki import load_guidelines_for_task

    gen = get_content_gen()
    preset = load_preset()
    config = build_config(preset, keyword=keyword, post_type=post_type)

    master = preset.get("master_guidelines") or ""
    if not master:
        master = load_guidelines_for_task(config.get("post_type") or "")

    _log(f"=== 원고+이미지 생성: '{keyword}' ===")
    _log(f"   글 유형: {config.get('post_type')}")
    _log(f"   텍스트: {config.get('text_provider')} | 이미지: {config.get('image_provider')}")

    if config.get("text_provider") == "ollama":
        await gen.ollama_warmup(_log)

    _log("   [1/3] 제목·개요·이미지 장면 설명...")
    title, outline, image_desc = await gen.generate_outline(config, keyword, keyword, _log, master)
    _log(f"   제목: {title}")
    _log(f"   이미지 장면: {image_desc[:120]}...")

    _log("   [2/3] 본문 작성...")
    body, tags = await gen.generate_body_from_outline(
        config, title, outline, keyword, keyword, _log, master
    )
    _log(f"   본문 길이: {len(body)}자")

    _log("   [3/3] 키워드·개요 맞춤 AI 이미지...")
    img_dir = os.path.join(_ROOT, "generated_images")
    os.makedirs(img_dir, exist_ok=True)
    paths = await gen.generate_images(
        config, keyword, keyword, _log, img_dir, title=title, image_desc=image_desc
    )
    if paths:
        _log(f"   이미지 저장: {paths[0]}")
    else:
        _log("   ⚠️ 이미지 없음 — Gemini API 키 또는 BLOG_IMAGE_PROVIDER=free 로 재시도")

    md_path = save_draft(
        keyword=keyword,
        title=title,
        outline=outline,
        body=body,
        tags=tags,
        image_desc=image_desc,
        image_paths=paths,
    )
    _log(f"✅ 초안 저장: {md_path}")
    return md_path


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="블로그 원고+키워드 맞춤 이미지 생성 (발행 없음)")
    p.add_argument("--keyword", "-k", required=True, help="포스팅 키워드 (예: 자동차 유리막 코팅)")
    p.add_argument("--post-type", "-t", default="", help="글 유형 (예: 자동차 정보, 제품 홍보)")
    args = p.parse_args(argv)
    post_type = args.post_type.strip() or None
    try:
        asyncio.run(run_draft(args.keyword.strip(), post_type))
        return 0
    except KeyboardInterrupt:
        _log("중단됨")
        return 130
    except Exception as e:
        _log(f"❌ 오류: {e}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
