# -*- coding: utf-8 -*-
"""네이버 블로그 해시태그 30개 준비."""

from __future__ import annotations

import json
import re
from typing import Any


def _cfg_naver_tag_count() -> int:
    try:
        from pathlib import Path

        cfg = json.loads(
            (Path(__file__).resolve().parent.parent / "config" / "blog_automation.json").read_text(
                encoding="utf-8"
            )
        )
        naver = (cfg.get("platforms") or {}).get("naver") or {}
        media = cfg.get("media") or {}
        return int(naver.get("tag_count") or media.get("naver_tag_count") or 30)
    except Exception:
        return 30


def expand_naver_tags(
    keyword: str,
    seeds: list[str] | None = None,
    *,
    title: str = "",
    count: int | None = None,
) -> list[str]:
    """네이버 발행용 태그 count개 (# 없이)."""
    n = count if count is not None else _cfg_naver_tag_count()
    n = max(1, min(30, n))
    out: list[str] = []
    for s in seeds or []:
        t = re.sub(r"^#+", "", (s or "").strip())
        if t and t not in out:
            out.append(t[:30])
    if len(out) >= n:
        return out[:n]

    need = n - len(out)
    kw = (keyword or "").strip()
    title_s = (title or "").strip()
    try:
        from integrations.blog_content_factory import _gemini

        prompt = f"""네이버 블로그 해시태그 {need}개 추가 (JSON만).
키워드: {kw}
제목: {title_s}
이미 태그: {", ".join(out[:15])}

규칙: # 없음, 2~20자, 중복 금지, 검색에 유리한 한국어
{{"tags": ["태그1", ...]}}"""
        raw = _gemini(prompt, system="JSON만 출력.")
        m = re.search(r"\{[\s\S]*\}", raw)
        if m:
            data = json.loads(m.group(0))
            for t in data.get("tags") or []:
                t = re.sub(r"^#+", "", str(t).strip())
                if t and t not in out:
                    out.append(t[:30])
                if len(out) >= n:
                    return out[:n]
    except Exception:
        pass

    # 키워드 파생으로 채우기
    parts = re.split(r"[\s,·/]+", kw)
    for p in parts + [kw, title_s]:
        p = re.sub(r"[^\w가-힣]", "", (p or "").strip())
        if len(p) >= 2 and p not in out:
            out.append(p[:30])
        if len(out) >= n:
            break
    i = 1
    while len(out) < n and kw:
        cand = f"{kw}{i}" if i > 1 else f"{kw}후기"
        if cand not in out:
            out.append(cand[:30])
        i += 1
    return out[:n]
