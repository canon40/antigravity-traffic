# -*- coding: utf-8 -*-
"""plan.json → 콘티.md · story.md · FLOW 보드 HTML."""

from __future__ import annotations

import html
import json
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
OUT_ROOT = _ROOT / "docs" / "shorts"
VIDEO_STUDIOS_PATH = _ROOT / "data" / "shorts_factory" / "video_studios.json"


def _load_video_studios() -> dict:
    if VIDEO_STUDIOS_PATH.is_file():
        try:
            return json.loads(VIDEO_STUDIOS_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def _flow_board_studio_links() -> str:
    vs = _load_video_studios()
    rec_id = vs.get("recommended", "google_flow")
    studios = vs.get("studios") or []
    ordered = []
    for s in studios:
        if s.get("id") == rec_id:
            ordered.insert(0, s)
        else:
            ordered.append(s)
    btns = []
    for s in ordered[:5]:
        sid = _esc(s.get("id", ""))
        name = _esc(s.get("name_ko") or s.get("name") or sid)
        url = _esc(s.get("url", "#"))
        cls = " primary" if s.get("id") == rec_id else ""
        btns.append(
            f'<a class="studio-link{cls}" href="{url}" target="_blank" rel="noopener" '
            f'data-studio="{sid}">{name} ↗</a>'
        )
    wf = "".join(f"<li>{_esc(x)}</li>" for x in (vs.get("workflow") or [])[:4])
    return f"""<section class="studios">
  <h2>실사 AI 영상 만들기</h2>
  <p class="sub">아래 버튼으로 Google FLOW · Meta AI 등을 열고, 장면별 FLOW 프롬프트를 붙여넣으세요. (클릭 시 해당 프롬프트가 클립보드에 복사됩니다)</p>
  <div class="studio-bar">{"".join(btns)}</div>
  <ol class="wf">{wf}</ol>
</section>"""


def _esc(s: str) -> str:
    return html.escape(str(s or ""))


def render_conti_md(plan: dict) -> str:
    title = plan.get("video_title") or plan.get("topic") or "쇼츠"
    lines = [
        f"# 콘티 — {title}",
        "",
        f"**주제:** {plan.get('topic', '')}",
        f"**스타일:** {plan.get('style', '')}",
        f"**후킹:** {plan.get('hook_line', '')}",
        "",
        "## 마스터 프롬프트 (FLOW)",
        plan.get("master_prompt", ""),
        "",
        "## FLOW Master (English)",
        plan.get("flow_master_prompt_en", ""),
        "",
        "## 입력 키워드",
        ", ".join(plan.get("input_keywords") or []),
        "",
        "## 장면별 콘티",
        "| # | 연출(콘티) | 배경/촬영 | 화자 | 나레이션 | 자막 | 제품 노출 | FLOW 키워드 |",
        "|---|-----------|-----------|------|----------|------|-----------|-------------|",
    ]
    for sc in plan.get("scenes") or []:
        lines.append(
            f"| {sc.get('scene_no')} | {sc.get('conti','')} | {sc.get('background_desc','')} "
            f"| {sc.get('speaker','')} | {sc.get('narration','')} | {sc.get('subtitle','')} "
            f"| {sc.get('product_mention','')} | `{sc.get('search_keyword','')}` |"
        )
    return "\n".join(lines) + "\n"


def render_story_md(plan: dict) -> str:
    title = plan.get("video_title") or plan.get("topic") or "쇼츠"
    lines = [
        f"# 스토리보드 — {title}",
        "",
        f"## 한 줄 요약",
        plan.get("hook_line", ""),
        "",
        f"## 전체 흐름",
        plan.get("master_prompt", ""),
        "",
        f"## 입력 키워드",
        ", ".join(plan.get("input_keywords") or []),
        "",
        "## 장면별 스토리 (FLOW 복사용)",
        "",
    ]
    for sc in plan.get("scenes") or []:
        n = sc.get("scene_no")
        dur = sc.get("duration_sec", 4)
        lines += [
            f"### 장면 {n} · {sc.get('speaker','')} · 약 {dur}초",
            f"**콘티:** {sc.get('conti','')}",
            f"**화면:** {sc.get('visual_desc','')}",
            f"**배경:** {sc.get('background_desc','')}",
            f"**대사:** {sc.get('narration','')}",
            f"**자막:** {sc.get('subtitle','')}",
            f"**제품 노출:** {sc.get('product_mention','')}",
            "",
            "**FLOW 영상 프롬프트 (영어):**",
            "```",
            sc.get("flow_prompt", ""),
            "```",
            "",
            "**스토리보드 정지화면 (영어):**",
            "```",
            sc.get("storyboard_image_prompt", ""),
            "```",
            "",
            f"**검색 키워드:** `{sc.get('search_keyword','')}`",
            "",
        ]
    lines += [
        "## FLOW 마스터 (한 번에 붙여넣기)",
        "```",
        plan.get("flow_master_prompt_en") or plan.get("master_prompt", ""),
        "```",
        "",
        "## YouTube 메타",
        f"- 제목: {plan.get('video_title','')}",
        f"- 설명: {plan.get('youtube_description','')}",
        f"- 태그: {', '.join(plan.get('youtube_tags') or [])}",
        "",
    ]
    return "\n".join(lines)


def render_flow_board_html(plan: dict) -> str:
    title = _esc(plan.get("video_title") or plan.get("topic"))
    cards = []
    for sc in plan.get("scenes") or []:
        n = sc.get("scene_no")
        fp = _esc(sc.get("flow_prompt", ""))
        img = sc.get("image_file") or ""
        img_tag = (
            f'<img src="{_esc(img)}" alt="scene {n}" style="width:100%;max-width:280px;border-radius:10px;margin-bottom:10px;display:block"/>'
            if img
            else ""
        )
        cards.append(
            f"""<article class="card" id="scene-{n}">
  {img_tag}
  <header><span class="num">{n}</span> { _esc(sc.get('subtitle') or sc.get('narration','')) }</header>
  <p class="conti">{_esc(sc.get('conti',''))}</p>
  <p class="meta">화자: {_esc(sc.get('speaker',''))} · {_esc(sc.get('duration_sec',''))}초 · 제품: {_esc(sc.get('product_mention',''))}</p>
  <label>FLOW 프롬프트 (영어)</label>
  <pre class="prompt" id="flow-{n}">{fp}</pre>
  <div class="actions">
    <button type="button" onclick="copyId('flow-{n}')">FLOW 복사</button>
    <button type="button" class="secondary" onclick="openStudioScene({n})">Google FLOW ↗</button>
    <button type="button" class="secondary" onclick="copyId('nar-{n}')">나레이션 복사</button>
  </div>
  <pre class="nar hide" id="nar-{n}">{_esc(sc.get('narration',''))}</pre>
</article>"""
        )
    master = _esc(plan.get("flow_master_prompt_en") or plan.get("master_prompt", ""))
    studio_bar = _flow_board_studio_links()
    studios_js = json.dumps(_load_video_studios(), ensure_ascii=False)
    return f"""<!DOCTYPE html>
<html lang="ko"><head><meta charset="utf-8"/><meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>FLOW 스토리보드 — {title}</title>
<style>
body{{font-family:'Malgun Gothic',sans-serif;background:#0f172a;color:#e2e8f0;margin:0;padding:20px;max-width:960px;}}
h1{{font-size:22px;}} .sub{{color:#94a3b8;font-size:14px;margin-bottom:20px;}}
.studios{{background:#1e293b;border-radius:12px;padding:16px;margin-bottom:24px;border:1px solid rgba(52,211,153,.35);}}
.studios h2{{font-size:18px;color:#6ee7b7;margin:0 0 8px;}}
.studio-bar{{display:flex;flex-wrap:wrap;gap:8px;margin:12px 0;}}
.studio-link{{display:inline-block;padding:8px 14px;border-radius:8px;font-weight:700;font-size:13px;text-decoration:none;
  background:#334155;color:#e2e8f0;border:1px solid #475569;}}
.studio-link.primary{{background:#059669;color:#ecfdf5;border-color:#34d399;}}
.studio-link:hover{{filter:brightness(1.08);}}
.wf{{font-size:13px;color:#94a3b8;line-height:1.5;padding-left:18px;margin:0;}}
.master{{background:#1e293b;border-radius:12px;padding:16px;margin-bottom:24px;border:1px solid #334155;}}
.card{{background:#1e293b;border-radius:12px;padding:16px;margin-bottom:16px;border:1px solid #334155;}}
.num{{background:#2563eb;color:#fff;padding:2px 10px;border-radius:99px;font-size:13px;margin-right:8px;}}
.conti{{font-size:15px;line-height:1.6;}} .meta{{font-size:13px;color:#94a3b8;}}
label{{font-size:12px;color:#64748b;display:block;margin-top:12px;}}
pre.prompt{{background:#020617;padding:12px;border-radius:8px;font-size:13px;white-space:pre-wrap;line-height:1.5;}}
.hide{{display:none;}}
button{{background:#22c55e;color:#052e16;border:none;padding:8px 14px;border-radius:8px;font-weight:700;cursor:pointer;margin-right:8px;margin-top:8px;}}
button.secondary{{background:#334155;color:#e2e8f0;}}
.nav a{{color:#93c5fd;margin-right:12px;}}
</style></head>
<body>
<div class="nav"><a href="index.html">목록</a><a href="conti.md">콘티.md</a><a href="story.md">story.md</a></div>
<h1>FLOW 스토리보드</h1>
<p class="sub">{title}</p>
{studio_bar}
<div class="master">
  <strong>FLOW 마스터</strong>
  <pre class="prompt" id="flow-master">{master}</pre>
  <button type="button" onclick="copyId('flow-master')">마스터 복사</button>
  <button type="button" class="secondary" onclick="openStudioMaster()">Google FLOW ↗</button>
</div>
{"".join(cards)}
<script>
const VIDEO_STUDIOS = {studios_js};
function copyId(id) {{
  const t = document.getElementById(id).innerText;
  navigator.clipboard.writeText(t).then(() => alert('복사됨'));
}}
function studioById(id) {{
  return (VIDEO_STUDIOS.studios || []).find(s => s.id === id);
}}
function openStudioMaster() {{
  const rec = VIDEO_STUDIOS.recommended || 'google_flow';
  const s = studioById(rec);
  if (!s) return;
  copyId('flow-master');
  window.open(s.url, '_blank', 'noopener');
}}
function openStudioScene(n) {{
  const rec = VIDEO_STUDIOS.recommended || 'google_flow';
  const s = studioById(rec);
  if (!s) return;
  copyId('flow-' + n);
  window.open(s.url, '_blank', 'noopener');
}}
document.querySelectorAll('.studio-link').forEach(a => {{
  a.addEventListener('click', e => {{
    e.preventDefault();
    const id = a.dataset.studio;
    const s = studioById(id);
    if (!s) return;
    copyId('flow-master');
    window.open(s.url, '_blank', 'noopener');
  }});
}});
</script>
</body></html>"""


async def write_outputs_async(
    plan: dict,
    slug: str,
    *,
    use_images: bool = True,
    log=None,
) -> Path:
    out_dir = OUT_ROOT / slug
    out_dir.mkdir(parents=True, exist_ok=True)
    if use_images:
        from shorts_factory.images import attach_storyboard_images

        plan = await attach_storyboard_images(plan, out_dir, log=log)
    return write_outputs(plan, slug)


def write_outputs(plan: dict, slug: str) -> Path:
    out_dir = OUT_ROOT / slug
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "plan.json").write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
    (out_dir / "conti.md").write_text(render_conti_md(plan), encoding="utf-8")
    (out_dir / "story.md").write_text(render_story_md(plan), encoding="utf-8")
    (out_dir / "flow_board.html").write_text(render_flow_board_html(plan), encoding="utf-8")
    _write_index(slug, plan)
    return out_dir


def _write_index(slug: str, plan: dict) -> None:
    entries = []
    if OUT_ROOT.is_dir():
        for d in sorted(OUT_ROOT.iterdir()):
            if d.is_dir() and (d / "plan.json").is_file():
                try:
                    p = json.loads((d / "plan.json").read_text(encoding="utf-8"))
                    t = p.get("video_title") or d.name
                except Exception:
                    t = d.name
                entries.append((d.name, t))
    items = "".join(
        f'<a class="item" href="{s}/flow_board.html"><strong>{_esc(t)}</strong><span>{_esc(s)}</span></a>'
        for s, t in entries
    )
    html_doc = f"""<!DOCTYPE html>
<html lang="ko"><head><meta charset="utf-8"/><meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>쇼츠 공장</title>
<style>
body{{font-family:'Malgun Gothic',sans-serif;background:#f1f5f9;padding:24px;max-width:640px;}}
h1{{font-size:22px;}} .item{{display:block;background:#fff;padding:16px;border-radius:10px;margin:10px 0;text-decoration:none;color:#1e293b;border:1px solid #e2e8f0;}}
.item span{{display:block;font-size:13px;color:#64748b;margin-top:4px;}}
</style></head>
<body>
<h1>쇼츠 공장 — 콘티·스토리보드</h1>
<p>키워드 입력 → FLOW용 프롬프트 자동 생성</p>
{items or '<p>아직 없음. run_shorts_factory.bat 실행</p>'}
</body></html>"""
    OUT_ROOT.mkdir(parents=True, exist_ok=True)
    (OUT_ROOT / "index.html").write_text(html_doc, encoding="utf-8")
