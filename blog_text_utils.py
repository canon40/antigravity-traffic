# -*- coding: utf-8 -*-
"""경량 텍스트 유틸 — 무거운 AI/이미지 모듈 없이 import 가능."""

import re


def strip_strikethrough_markers(text: str) -> str:
    """마크다운·HTML 취소선 표기 제거 — 네이버 에디터 가운데 줄 방지."""
    if not text:
        return text
    body = str(text)
    for _ in range(6):
        prev = body
        body = re.sub(r"~~(.+?)~~", r"\1", body, flags=re.DOTALL)
        if body == prev:
            break
    body = body.replace("~~", "")
    body = re.sub(r"<del>(.*?)</del>", r"\1", body, flags=re.I | re.DOTALL)
    body = re.sub(r"<s>(.*?)</s>", r"\1", body, flags=re.I | re.DOTALL)
    body = re.sub(r"<strike>(.*?)</strike>", r"\1", body, flags=re.I | re.DOTALL)
    body = re.sub(r"</?s\b[^>]*>", "", body, flags=re.I)
    body = re.sub(r"</?strike\b[^>]*>", "", body, flags=re.I)
    body = re.sub(r"</?del\b[^>]*>", "", body, flags=re.I)

    def _strip_line_through_style(m):
        s = m.group(1)
        s = re.sub(r"text-decoration\s*:\s*line-through\s*;?\s*", "", s, flags=re.I)
        s = re.sub(r";\s*;", ";", s).strip("; ")
        return f' style="{s}"' if s else ""

    def _strip_line_through_style_sq(m):
        s = m.group(1)
        s = re.sub(r"text-decoration\s*:\s*line-through\s*;?\s*", "", s, flags=re.I)
        s = re.sub(r";\s*;", ";", s).strip("; ")
        return f" style='{s}'" if s else ""

    body = re.sub(
        r'\s+style="([^"]*)"',
        lambda m: _strip_line_through_style(m) if "line-through" in m.group(1).lower() else m.group(0),
        body,
        flags=re.I,
    )
    body = re.sub(
        r"\s+style='([^']*)'",
        lambda m: _strip_line_through_style_sq(m) if "line-through" in m.group(1).lower() else m.group(0),
        body,
        flags=re.I,
    )
    body = body.replace("\u0336", "").replace("\u0335", "")
    return body
