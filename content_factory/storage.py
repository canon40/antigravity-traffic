# -*- coding: utf-8 -*-
"""블로그 콘텐츠·이미지 로컬 저장 (n8n Docker 볼륨 대체)."""

from __future__ import annotations

import os
import re
import uuid
from datetime import datetime
from pathlib import Path

_BASE = Path(__file__).resolve().parent.parent


def content_root() -> Path:
    custom = os.environ.get("CONTENT_FACTORY_DIR", "").strip()
    root = Path(custom) if custom else _BASE / "blog_content"
    root.mkdir(parents=True, exist_ok=True)
    (root / "images").mkdir(parents=True, exist_ok=True)
    return root


def _slug(text: str, max_len: int = 40) -> str:
    s = re.sub(r"[^\w가-힣\-]+", "_", (text or "post").strip())
    s = re.sub(r"_+", "_", s).strip("_")[:max_len]
    return s or "post"


def save_html(topic: str, html: str, *, suffix: str = "") -> Path:
    root = content_root()
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    name = f"{_slug(topic)}{('_' + suffix) if suffix else ''}_{stamp}.html"
    path = root / name
    path.write_text(html, encoding="utf-8")
    return path


def save_text(topic: str, text: str, *, suffix: str = "") -> Path:
    root = content_root()
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    name = f"{_slug(topic)}{('_' + suffix) if suffix else ''}_{stamp}.md"
    path = root / name
    path.write_text(text, encoding="utf-8")
    return path


def save_image_bytes(data: bytes, *, ext: str = "jpg", keyword: str = "") -> Path:
    root = content_root() / "images"
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    kw = _slug(keyword, 20)
    name = f"{kw}_{stamp}_{uuid.uuid4().hex[:6]}.{ext.lstrip('.')}"
    path = root / name
    path.write_bytes(data)
    return path
