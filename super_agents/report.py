# -*- coding: utf-8 -*-
"""스타일 HTML 브리핑 리포트 (브라우저 인쇄 → PDF)."""

from __future__ import annotations

import html
import re
from datetime import datetime, timezone
from pathlib import Path


def _runs_dir(root: Path) -> Path:
    d = root / "data" / "super_agents" / "runs"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _slug(text: str) -> str:
    s = re.sub(r"[^\w가-힣]+", "_", (text or "briefing").strip())[:40].strip("_")
    return s or "briefing"


def save_html_report(
    *,
    title: str,
    briefing_md: str,
    script_md: str,
    sources: list[str],
    root: Path,
) -> Path:
    runs = _runs_dir(root)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M")
    path = runs / f"{stamp}_{_slug(title)}.html"

    src_items = "".join(
        f'<li><a href="{html.escape(u)}" target="_blank" rel="noopener">{html.escape(u)}</a></li>'
        for u in sources[:20]
        if u.strip()
    )
    body_b = _md_to_html(briefing_md)
    body_s = _md_to_html(script_md)

    doc = f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>{html.escape(title)}</title>
<style>
body{{font-family:'Pretendard',system-ui,sans-serif;background:#0f172a;color:#e2e8f0;line-height:1.65;max-width:820px;margin:0 auto;padding:28px}}
h1{{font-size:22px;color:#38bdf8;margin-bottom:4px}}
.meta{{color:#94a3b8;font-size:13px;margin-bottom:24px}}
section{{background:#1e293b;border:1px solid #334155;border-radius:12px;padding:18px 20px;margin-bottom:16px}}
h2{{font-size:15px;color:#34d399;margin-bottom:10px}}
p,li{{font-size:14px;color:#cbd5e1}}
ul{{margin:8px 0 0 18px}}
.score{{display:inline-block;background:rgba(56,189,248,.15);color:#7dd3fc;padding:2px 8px;border-radius:6px;font-size:12px;font-weight:700}}
@media print{{body{{background:#fff;color:#111}}section{{border-color:#ccc}}}}
</style>
</head>
<body>
<h1>{html.escape(title)}</h1>
<p class="meta">Super Agent Daily Briefing · {stamp} UTC · Ctrl+P 로 PDF 저장</p>
<section><h2>딥 리서치 브리핑</h2>{body_b}</section>
<section><h2>영상·블로그 스크립트</h2>{body_s}</section>
<section><h2>출처</h2><ul>{src_items or '<li>수집된 링크 없음</li>'}</ul></section>
</body>
</html>"""
    path.write_text(doc, encoding="utf-8")
    return path


def _md_to_html(text: str) -> str:
    lines = (text or "").strip().splitlines()
    out: list[str] = []
    in_ul = False
    for line in lines:
        line = line.rstrip()
        if re.match(r"^##\s+", line):
            if in_ul:
                out.append("</ul>")
                in_ul = False
            out.append(f"<h3>{html.escape(line[3:].strip())}</h3>")
        elif re.match(r"^[-*]\s+", line):
            if not in_ul:
                out.append("<ul>")
                in_ul = True
            out.append(f"<li>{html.escape(line[2:].strip())}</li>")
        elif re.match(r"^\[신뢰도", line, re.I) or re.match(r"^신뢰도", line):
            if in_ul:
                out.append("</ul>")
                in_ul = False
            out.append(f'<p><span class="score">{html.escape(line)}</span></p>')
        elif line.strip():
            if in_ul:
                out.append("</ul>")
                in_ul = False
            out.append(f"<p>{html.escape(line)}</p>")
    if in_ul:
        out.append("</ul>")
    return "\n".join(out) if out else "<p>(내용 없음)</p>"
