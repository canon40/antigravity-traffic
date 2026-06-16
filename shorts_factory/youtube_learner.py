# -*- coding: utf-8 -*-
"""YouTube 자막·메타데이터 학습 → 동영상 제작 플레이북 진화 (API 불필요)."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from urllib.parse import parse_qs, urlparse

_ROOT = Path(__file__).resolve().parent.parent
EVOLUTION_PATH = _ROOT / "data" / "shorts_factory" / "youtube_evolution.json"
BRAND_PATH = _ROOT / "data" / "shorts_factory" / "brand.json"
SHOPPING_HUB_PATH = _ROOT / "data" / "shorts_factory" / "shopping_shorts_hub.json"
LEARN_CACHE_DIR = _ROOT / "data" / "shorts_factory" / "youtube_learned"

LogFn = Callable[[str], None]

_TOOL_KEYWORDS = (
    "capcut", "캡컷", "premiere", "프리미어", "flow", "veo", "runway",
    "higgsfield", "틱톡", "tiktok", "유튜브", "youtube", "스마트스토어",
    "망고보드", "피그마", "figma", "canva", "쿠팡", "인스타", "instagram",
    "gemini", "chatgpt", "claude", "remotion", "tapnow", "meta ai",
)
_HOOK_MARKERS = (
    "?", "아직도", "모르면", "방법", "비밀", "꿀팁", "충격", "이거",
    "왜", "진짜", "솔직히", "몰랐", "놓치", "실수",
)
_AVOID_MARKERS = (
    "금지", "하지 마", "하지마", "피하", "안 됩니다", "안돼", "삭제",
    "댓글 달면", "dm", "복붙", "그대로",
)
_STEP_RE = re.compile(
    r"(?:^|\s)(?:[①②③④⑤⑥⑦⑧⑨⑩]|(?:\d{1,2})[\.\)]\s*)([^\n。]{4,80})",
    re.M,
)


def _log_default(msg: str) -> None:
    try:
        print(msg, flush=True)
    except UnicodeEncodeError:
        enc = getattr(sys.stdout, "encoding", None) or "utf-8"
        print(msg.encode(enc, errors="replace").decode(enc, errors="replace"), flush=True)


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def parse_youtube_id(url: str) -> str | None:
    raw = (url or "").strip()
    if not raw:
        return None
    if re.fullmatch(r"[A-Za-z0-9_-]{11}", raw):
        return raw
    parsed = urlparse(raw)
    host = (parsed.netloc or "").lower()
    if "youtu.be" in host:
        vid = parsed.path.strip("/").split("/")[0]
        return vid if len(vid) == 11 else None
    if "youtube.com" in host:
        qs = parse_qs(parsed.query)
        if qs.get("v"):
            return qs["v"][0]
        m = re.match(r"^/(?:embed|shorts|live)/([A-Za-z0-9_-]{11})", parsed.path or "")
        if m:
            return m.group(1)
    return None


def _find_yt_dlp() -> str | None:
    for name in ("yt-dlp", "yt-dlp.exe"):
        p = shutil.which(name)
        if p:
            return p
    return None


def _run_yt_dlp(args: list[str], log: LogFn) -> subprocess.CompletedProcess[str]:
    exe = _find_yt_dlp()
    if not exe:
        raise RuntimeError("yt-dlp가 설치되어 있지 않습니다. pip install yt-dlp")
    cmd = [exe, *args]
    log(f"   yt-dlp: {' '.join(cmd[:6])}...")
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=120,
    )


def fetch_video_info(url: str, log: LogFn = _log_default) -> dict[str, Any]:
    vid = parse_youtube_id(url)
    if not vid:
        raise ValueError(f"YouTube URL/ID를 인식할 수 없습니다: {url}")
    proc = _run_yt_dlp(["--dump-single-json", "--skip-download", url], log)
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "").strip()
        raise RuntimeError(err or "yt-dlp 메타데이터 실패")
    meta = json.loads(proc.stdout)
    return {
        "video_id": vid,
        "title": meta.get("title") or "",
        "channel": meta.get("channel") or meta.get("uploader") or "",
        "duration_sec": meta.get("duration"),
        "url": f"https://www.youtube.com/watch?v={vid}",
        "description": (meta.get("description") or "")[:2000],
    }


def _clean_vtt(raw: str) -> str:
    lines: list[str] = []
    seen: set[str] = set()
    for line in raw.splitlines():
        line = line.strip()
        if not line or line.startswith("WEBVTT") or "-->" in line:
            continue
        if line.startswith("Kind:") or line.startswith("Language:"):
            continue
        line = re.sub(r"<[^>]+>", "", line)
        line = re.sub(r"\s+", " ", line).strip()
        if len(line) < 4:
            continue
        if line in seen:
            continue
        seen.add(line)
        lines.append(line)
    return "\n".join(lines)


def fetch_transcript(url: str, log: LogFn = _log_default) -> str:
    vid = parse_youtube_id(url)
    if not vid:
        raise ValueError("YouTube ID 필요")
    LEARN_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    out_tpl = str(LEARN_CACHE_DIR / f"{vid}.%(ext)s")
    proc = _run_yt_dlp(
        [
            "--skip-download",
            "--write-auto-sub",
            "--write-sub",
            "--sub-langs", "ko,ko.*,en",
            "--sub-format", "vtt",
            "-o", out_tpl,
            url,
        ],
        log,
    )
    candidates = sorted(LEARN_CACHE_DIR.glob(f"{vid}.*.vtt")) + sorted(
        LEARN_CACHE_DIR.glob(f"{vid}.vtt")
    )
    ko_first = sorted(candidates, key=lambda p: (0 if ".ko" in p.name else 1, p.name))
    for path in ko_first:
        try:
            text = _clean_vtt(path.read_text(encoding="utf-8", errors="replace"))
            if len(text) >= 80:
                return text
        except OSError:
            continue
    if proc.returncode != 0 and not candidates:
        err = (proc.stderr or "").strip()
        if "429" in err:
            log("   자막 요청 제한(429) - 제목/설명만 사용")
        elif err:
            log(f"   자막 실패: {err[:180]}")
        return ""
    if candidates:
        return _clean_vtt(candidates[0].read_text(encoding="utf-8", errors="replace"))
    return ""


def _is_workflow_step(text: str) -> bool:
    s = (text or "").strip()
    if len(s) < 8 or len(s) > 100:
        return False
    keys = (
        "벤치", "촬영", "편집", "업로드", "만들", "제작", "콘텐츠", "쇼츠", "틱톡",
        "스마트", "상세", "장면", "후킹", "멘트", "패러", "링크", "프로필", "분석",
        "flow", "capcut", "캡컷", "이미지", "클립", "자막", "스토어", "쿠팡",
    )
    return any(k in s.lower() or k in s for k in keys)


def _is_hook_line(text: str) -> bool:
    s = (text or "").strip()
    if len(s) < 12 or len(s) > 80:
        return False
    if not any(m in s for m in _HOOK_MARKERS):
        return False
    bad = ("렛츠", "강의", "알려 드릴", "독수리 타자", "하나?")
    return not any(b in s for b in bad)


def extract_patterns(transcript: str, *, title: str = "", description: str = "") -> dict[str, Any]:
    blob = f"{title}\n{description}\n{transcript}"
    lower = blob.lower()

    tools = sorted({t for t in _TOOL_KEYWORDS if t.lower() in lower or t in blob})

    steps: list[str] = []
    for m in _STEP_RE.finditer(transcript):
        step = m.group(1).strip(" ·-—")
        if _is_workflow_step(step) and step not in steps:
            steps.append(step)
    if not steps:
        for kw in ("먼저", "그다음", "그 다음", "마지막", "두 번째", "세 번째"):
            for line in transcript.splitlines():
                if kw in line and _is_workflow_step(line):
                    s = line.strip()
                    if s not in steps:
                        steps.append(s)
                    if len(steps) >= 8:
                        break
            if len(steps) >= 8:
                break

    hooks: list[str] = []
    for line in transcript.splitlines()[:60]:
        line = line.strip()
        if _is_hook_line(line) and line not in hooks:
            hooks.append(line)

    avoid: list[str] = []
    follow: list[str] = []
    for line in transcript.splitlines():
        line = line.strip()
        if len(line) < 10 or len(line) > 120:
            continue
        if any(m in line for m in _AVOID_MARKERS):
            if line not in avoid:
                avoid.append(line)
        if any(w in line for w in ("추천", "이렇게", "벤치마킹", "패러프레이즈", "9:16", "세로")):
            if line not in follow:
                follow.append(line)

    scene_flow: list[str] = []
    for pat in (
        r"후킹[^\n。]{0,40}",
        r"오프닝[^\n。]{0,40}",
        r"전후[^\n。]{0,40}",
        r"CTA[^\n。]{0,40}",
        r"마지막[^\n。]{0,50}",
    ):
        for m in re.finditer(pat, blob, re.I):
            s = m.group(0).strip()
            if s not in scene_flow:
                scene_flow.append(s)

    tips = [ln.strip() for ln in transcript.splitlines() if "팁" in ln or "꿀" in ln][:6]

    return {
        "steps": steps[:12],
        "tools": tools[:20],
        "hooks": hooks[:8],
        "rules_follow": follow[:10],
        "rules_avoid": avoid[:10],
        "scene_flow": scene_flow[:8],
        "tips": tips,
        "transcript_chars": len(transcript),
        "excerpt": transcript[:1200],
    }


def default_evolution() -> dict[str, Any]:
    seed: dict[str, Any] = {
        "generation": 0,
        "updated_at": _now_iso(),
        "tagline": "YouTube 학습 → 콘티·FLOW·편집 플레이북 자동 진화",
        "playbook": {
            "workflow": [
                "① 벤치마크 영상 분석 (구조·템포·후킹)",
                "② 멘트 패러프레이즈 + 장면별 콘티",
                "③ FLOW/Higgsfield로 9:16 클립",
                "④ CapCut 합성 · 자막 · 업로드",
            ],
            "tools": ["Google FLOW", "CapCut", "틱톡"],
            "hooks": [],
            "rules_follow": [],
            "rules_avoid": ["멘트 100% 동일 복붙", "댓글/DM 유도형"],
            "scene_flow": ["후킹 → 고민 → 제품/효과 → CTA"],
            "tips": [],
        },
        "learned_videos": [],
        "sources": [],
    }
    if SHOPPING_HUB_PATH.is_file():
        hub = json.loads(SHOPPING_HUB_PATH.read_text(encoding="utf-8"))
        pb = seed["playbook"]
        pb["workflow"] = hub.get("creation_workflow") or pb["workflow"]
        pb["hooks"] = list(hub.get("hook_templates") or [])[:8]
        rr = hub.get("reference_rules") or {}
        pb["rules_follow"] = list(rr.get("follow") or [])
        pb["rules_avoid"] = list(rr.get("avoid") or [])
        seed["sources"].append("shopping_shorts_hub.json")
    return seed


def load_evolution() -> dict[str, Any]:
    if not EVOLUTION_PATH.is_file():
        data = default_evolution()
        save_evolution(data)
        return data
    return json.loads(EVOLUTION_PATH.read_text(encoding="utf-8"))


def save_evolution(data: dict[str, Any]) -> None:
    EVOLUTION_PATH.parent.mkdir(parents=True, exist_ok=True)
    data["updated_at"] = _now_iso()
    EVOLUTION_PATH.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _merge_unique(existing: list[str], new: list[str], *, limit: int = 24) -> list[str]:
    out = list(existing)
    for item in new:
        item = (item or "").strip()
        if not item:
            continue
        if item not in out:
            out.append(item)
    return out[:limit]


def merge_playbook(playbook: dict[str, Any], patterns: dict[str, Any]) -> dict[str, Any]:
    pb = dict(playbook)
    base_wf = [s for s in (pb.get("workflow") or []) if s.startswith("①") or s.startswith("②") or _is_workflow_step(s)]
    pb["workflow"] = _merge_unique(
        base_wf,
        [s for s in (patterns.get("steps") or []) if _is_workflow_step(s)],
        limit=16,
    )
    pb["tools"] = _merge_unique(list(pb.get("tools") or []), list(patterns.get("tools") or []))
    pb["hooks"] = _merge_unique(list(pb.get("hooks") or []), list(patterns.get("hooks") or []))
    pb["rules_follow"] = _merge_unique(
        list(pb.get("rules_follow") or []),
        list(patterns.get("rules_follow") or []),
    )
    pb["rules_avoid"] = _merge_unique(
        list(pb.get("rules_avoid") or []),
        list(patterns.get("rules_avoid") or []),
    )
    pb["scene_flow"] = _merge_unique(
        list(pb.get("scene_flow") or []),
        list(patterns.get("scene_flow") or []),
    )
    pb["tips"] = _merge_unique(list(pb.get("tips") or []), list(patterns.get("tips") or []))
    return pb


def learn_from_url(url: str, log: LogFn = _log_default) -> dict[str, Any]:
    vid = parse_youtube_id(url)
    if not vid:
        raise ValueError("유효한 YouTube URL이 필요합니다.")

    evo = load_evolution()
    for entry in evo.get("learned_videos") or []:
        if entry.get("video_id") == vid:
            log(f"   이미 학습됨: {vid}")
            return {"ok": True, "skipped": True, "video_id": vid, "evolution": evo}

    log(f">> YouTube 학습: {url}")
    info = fetch_video_info(url, log)
    transcript = ""
    try:
        transcript = fetch_transcript(url, log)
    except Exception as e:
        log(f"   자막 없음/실패 - 설명/제목만 사용: {e}")

    patterns = extract_patterns(
        transcript,
        title=info.get("title") or "",
        description=info.get("description") or "",
    )
    entry = {
        "video_id": vid,
        "title": info.get("title"),
        "channel": info.get("channel"),
        "url": info.get("url"),
        "learned_at": _now_iso(),
        "duration_sec": info.get("duration_sec"),
        "patterns": patterns,
    }
    learned = list(evo.get("learned_videos") or [])
    learned.append(entry)
    evo["learned_videos"] = learned[-40:]
    evo["playbook"] = merge_playbook(evo.get("playbook") or {}, patterns)
    evo["generation"] = int(evo.get("generation") or 0) + 1
    save_evolution(evo)
    log(f"   OK gen={evo['generation']} hooks={len(patterns.get('hooks') or [])} steps={len(patterns.get('steps') or [])}")
    return {"ok": True, "video_id": vid, "entry": entry, "evolution": evo}


def seed_from_brand(log: LogFn = _log_default) -> dict[str, Any]:
    if not BRAND_PATH.is_file():
        raise FileNotFoundError(str(BRAND_PATH))
    brand = json.loads(BRAND_PATH.read_text(encoding="utf-8"))
    urls = [
        r["url"]
        for r in (brand.get("references") or [])
        if r.get("type") == "video" and r.get("url")
    ]
    results = []
    for i, url in enumerate(urls):
        if i:
            time.sleep(4)
        try:
            results.append(learn_from_url(url, log))
        except Exception as e:
            log(f"   [FAIL] {url}: {e}")
            results.append({"ok": False, "url": url, "error": str(e)})
    evo = load_evolution()
    return {"ok": True, "learned_count": sum(1 for r in results if r.get("ok")), "results": results, "evolution": evo}


def evolution_prompt_block(*, shopping: bool = False) -> str:
    evo = load_evolution()
    pb = evo.get("playbook") or {}
    gen = evo.get("generation") or 0
    if gen < 1 and not pb.get("hooks"):
        return ""

    lines = [
        f"【YouTube 학습 플레이북 · 진화 gen={gen}】",
        "아래는 실제 가이드 영상 자막·워크플로에서 축적된 패턴입니다. 콘티·FLOW·나레이션에 반영하세요.",
    ]
    if pb.get("workflow"):
        lines.append("- 워크플로: " + " → ".join(str(x) for x in pb["workflow"][:6]))
    if pb.get("scene_flow"):
        lines.append("- 장면 흐름: " + " / ".join(str(x) for x in pb["scene_flow"][:5]))
    if pb.get("hooks"):
        lines.append("- 후킹 참고: " + " | ".join(str(x) for x in pb["hooks"][:4]))
    if pb.get("rules_follow"):
        lines.append("- 따라할 것: " + "; ".join(str(x) for x in pb["rules_follow"][:4]))
    if pb.get("rules_avoid"):
        lines.append("- 피할 것: " + "; ".join(str(x) for x in pb["rules_avoid"][:4]))
    if pb.get("tools"):
        lines.append("- 도구: " + ", ".join(str(x) for x in pb["tools"][:8]))
    if shopping and pb.get("tips"):
        lines.append("- 팁: " + "; ".join(str(x) for x in pb["tips"][:3]))
    return "\n".join(lines) + "\n"
