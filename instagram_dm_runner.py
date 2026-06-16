# -*- coding: utf-8 -*-
"""인스타그램 DM 일일 팩 생성 — 대상 로테이션·문구·발송 체크리스트."""

from __future__ import annotations

import json
import random
import webbrowser
from datetime import datetime
from pathlib import Path

_ROOT = Path(__file__).resolve().parent
OPS_DIR = _ROOT / "data" / "ops"


def _load(path: Path) -> dict:
    if not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _save(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _normalize_username(raw: str) -> str:
    u = (raw or "").strip().lstrip("@")
    if "instagram.com/" in u:
        u = u.split("instagram.com/")[-1].split("/")[0].split("?")[0]
    return u


def _pick_targets(targets: list[str], sent: dict, today: str, count: int) -> list[str]:
    pool = [_normalize_username(t) for t in targets if _normalize_username(t)]
    if not pool:
        return []
    random.shuffle(pool)
    out: list[str] = []
    for u in pool:
        last = (sent.get(u) or {}).get("last_sent")
        if last == today:
            continue
        out.append(u)
        if len(out) >= count:
            break
    if len(out) < count:
        for u in pool:
            if u not in out:
                out.append(u)
            if len(out) >= count:
                break
    return out[:count]


def build_daily_pack(
    config_path: Path | None = None,
    per_category: int = 3,
    *,
    log=print,
) -> dict:
    cfg_path = config_path or (_ROOT / "data" / "instagram_dm_config.json")
    cfg = _load(cfg_path)
    if not cfg.get("enabled", True):
        log("인스타 DM 팩 비활성화 (instagram_dm_config.json)")
        return {}

    sent_path = _ROOT / (cfg.get("sent_log") or "data/instagram_dm_sent.json")
    sent = _load(sent_path)
    today = datetime.now().strftime("%Y-%m-%d")
    limit = int(cfg.get("daily_limit_total") or 12)
    per_cat = max(1, int(per_category or 3))

    items: list[dict] = []
    for cat_id, cat in (cfg.get("categories") or {}).items():
        label = cat.get("label") or cat_id
        targets = cat.get("targets") or []
        templates = [t.strip() for t in (cat.get("templates") or []) if str(t).strip()]
        if not targets:
            log(f"  ⚠️ [{label}] 대상 없음 — instagram_dm_config.json 에 targets 추가")
            continue
        picked = _pick_targets(targets, sent, today, per_cat)
        for user in picked:
            msg = random.choice(templates) if templates else ""
            items.append(
                {
                    "category": cat_id,
                    "category_label": label,
                    "username": user,
                    "message": msg,
                    "ig_profile": f"https://www.instagram.com/{user}/",
                    "ig_dm": f"https://ig.me/m/{user}",
                }
            )
            if len(items) >= limit:
                break
        if len(items) >= limit:
            break

    pack = {
        "date": today,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "total": len(items),
        "items": items,
    }
    OPS_DIR.mkdir(parents=True, exist_ok=True)
    _save(OPS_DIR / "dm_today.json", pack)
    _save(OPS_DIR / "dm_today.html", _render_dm_html(pack))
    log(f"📩 인스타 DM 오늘 팩: {len(items)}건 → data/ops/dm_today.html")
    return pack


def _render_dm_html(pack: dict) -> str:
    rows = []
    for i, it in enumerate(pack.get("items") or [], start=1):
        msg_esc = (it.get("message") or "").replace("&", "&amp;").replace("<", "&lt;")
        rows.append(
            f"""<section class="card" id="dm-{i}">
  <div class="meta"><span class="badge">{it.get('category_label','')}</span> @{it.get('username','')}</div>
  <pre class="msg" id="msg-{i}">{msg_esc}</pre>
  <div class="actions">
    <button type="button" onclick="copyMsg({i})">문구 복사</button>
    <a class="btn" href="{it.get('ig_dm','')}" target="_blank" rel="noopener">DM 열기</a>
    <a class="link" href="{it.get('ig_profile','')}" target="_blank" rel="noopener">프로필</a>
  </div>
</section>"""
        )
    body = (
        "\n".join(rows)
        if rows
        else '<p class="empty">대상이 없습니다. <code>data/instagram_dm_config.json</code> 의 targets 에 인스타 아이디를 추가하세요.</p>'
    )
    return f"""<!DOCTYPE html>
<html lang="ko"><head><meta charset="utf-8"/><meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>오늘 인스타 DM — {pack.get('date','')}</title>
<style>
body{{font-family:'Malgun Gothic',sans-serif;background:#0f172a;color:#e2e8f0;margin:0;padding:24px;max-width:720px;}}
h1{{font-size:22px;}} .sub{{color:#94a3b8;font-size:14px;margin-bottom:24px;}}
.card{{background:#1e293b;border-radius:12px;padding:16px;margin-bottom:16px;border:1px solid #334155;}}
.badge{{background:#2563eb;color:#fff;font-size:12px;padding:4px 10px;border-radius:99px;}}
.msg{{white-space:pre-wrap;background:#020617;padding:12px;border-radius:8px;font-size:14px;line-height:1.6;}}
.actions{{margin-top:12px;display:flex;gap:8px;flex-wrap:wrap;}}
button,.btn{{background:#22c55e;color:#052e16;border:none;padding:10px 16px;border-radius:8px;cursor:pointer;font-weight:700;text-decoration:none;font-size:14px;}}
.link{{color:#93c5fd;align-self:center;font-size:14px;}}
.empty{{color:#fbbf24;}}
</style></head>
<body>
<h1>오늘 인스타 DM ({pack.get('total',0)}건)</h1>
<p class="sub">문구 복사 → DM 열기 → 붙여넣기 후 발송. 완료 후 체크리스트에서 표시하세요.</p>
{body}
<script>
function copyMsg(i) {{
  const t = document.getElementById('msg-'+i).innerText;
  navigator.clipboard.writeText(t).then(() => alert('복사됨'));
}}
</script>
</body></html>"""


def mark_sent(usernames: list[str], log=print) -> None:
    cfg = _load(_ROOT / "data" / "instagram_dm_config.json")
    sent_path = _ROOT / (cfg.get("sent_log") or "data/instagram_dm_sent.json")
    sent = _load(sent_path)
    today = datetime.now().strftime("%Y-%m-%d")
    for raw in usernames:
        u = _normalize_username(raw)
        if u:
            sent[u] = {"last_sent": today}
    _save(sent_path, sent)
    log(f"발송 기록 저장: {len(usernames)}건")


def open_dm_links(pack: dict, max_open: int = 5, log=print) -> None:
    items = pack.get("items") or []
    for it in items[:max_open]:
        url = it.get("ig_dm") or ""
        if url:
            webbrowser.open(url)
            log(f"  브라우저: @{it.get('username')}")
    if len(items) > max_open:
        log(f"  (나머지 {len(items) - max_open}건은 dm_today.html 에서 열기)")


def _cli_log(msg: str) -> None:
    try:
        print(msg, flush=True)
    except UnicodeEncodeError:
        print(msg.encode("cp949", errors="replace").decode("cp949"), flush=True)


if __name__ == "__main__":
    import argparse

    p = argparse.ArgumentParser()
    p.add_argument("--open-links", action="store_true")
    p.add_argument("--per-category", type=int, default=3)
    args = p.parse_args()
    pack = build_daily_pack(per_category=args.per_category, log=_cli_log)
    if args.open_links and pack:
        open_dm_links(pack, log=_cli_log)
