# -*- coding: utf-8
"""키워드 → 고유 블로그 글 (JSON) 생성."""

from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path
from typing import Any

from integrations.blog_duplicate_guard import check_duplicate

_ROOT = Path(__file__).resolve().parent.parent
_CFG = _ROOT / "config" / "blog_automation.json"


def _load_cfg() -> dict[str, Any]:
    if _CFG.is_file():
        return json.loads(_CFG.read_text(encoding="utf-8"))
    return {}


_GUIDELINE_FILE = _ROOT / "config" / "blog_writing_guideline.txt"


def load_writing_guideline(extra: str = "") -> str:
    """config/blog_writing_guideline.txt + CLI/액션에서 넘긴 지침."""
    parts: list[str] = []
    if _GUIDELINE_FILE.is_file():
        try:
            t = _GUIDELINE_FILE.read_text(encoding="utf-8").strip()
            if t:
                parts.append(t)
        except Exception:
            pass
    env_g = (os.environ.get("JARVIS_BLOG_GUIDELINE") or "").strip()
    if env_g:
        parts.append(env_g)
    if (extra or "").strip():
        parts.append(extra.strip())
    return "\n\n".join(parts)


def _api_sparing() -> bool:
    return os.environ.get("JARVIS_API_SPARING", os.environ.get("BLOG_API_SPARING", "1")).strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def _gemini(prompt: str, *, system: str = "") -> str:
    try:
        from llm.router import _ollama_ping, ollama_chat

        if _ollama_ping():
            ollama_raw = ollama_chat(prompt, system=system, json_mode=True)
            if ollama_raw and re.search(r"\{[\s\S]*\}", ollama_raw):
                return ollama_raw
    except Exception as e:
        print(f"[블로그] Ollama 우선 시도: {e}")

    if _api_sparing():
        return ""

    from jarvis_ultimate_system import JarvisUltimateDirector

    d = JarvisUltimateDirector()
    full = f"{system}\n\n{prompt}" if system else prompt
    raw = d._gemini_generate(full, flash=False)
    if raw and re.search(r"\{[\s\S]*\}", raw):
        return raw
    return raw or ""


def _build_fallback_article(keyword: str, *, variation: int = 0) -> dict[str, Any]:
    """LLM 응답이 없을 때 최소 품질 글 패키지를 생성한다."""
    kw = (keyword or "").strip()
    base_tags = [
        kw,
        "자동차코팅제",
        "세라믹코팅",
        "유리막코팅",
        "차량관리",
        "셀프코팅",
        "코팅유지관리",
        "발수코팅",
        "광택관리",
        "내구성테스트",
        "브레이크클리너",
        "도장면보호",
        "오염방지",
        "세차루틴",
        "자동차디테일링",
        "코팅효과",
        "코팅비교",
        "코팅팁",
        "자동차관리팁",
        "초보자코팅",
        "주행환경관리",
        "차량외장관리",
        "코팅관리법",
        "코팅전처리",
        "코팅후관리",
        "실사용후기",
        "자동차생활",
        "DIY코팅",
        "세차정보",
        "차량보호",
    ]
    # 태그는 네이버 업로드 호환을 위해 30개를 맞춘다.
    tags = [t[:20] for t in base_tags if t][:30]
    while len(tags) < 30:
        tags.append(f"{kw[:12]}팁{len(tags)+1}")

    sections = [
        ("왜 이 조합이 중요한가", "세라믹 코팅과 브레이크 클리너는 각각 보호와 세정 역할을 담당합니다. 핵심은 세정 직후 표면 상태를 안정화하고, 코팅제를 얇고 균일하게 도포해 초기 경화를 지켜내는 순서입니다."),
        ("실사용 기준 체크리스트", "실내 주차 여부, 주행 거리, 주 1회 세차 가능 여부를 먼저 점검하세요. 동일 제품이라도 관리 루틴이 다르면 체감 내구성 차이가 크게 벌어집니다."),
        ("오래 가는 적용 순서", "세정 후 완전 건조, 탈지, 소량 도포, 분할 버핑, 24시간 초기 보호 순으로 진행하세요. 특히 분할 버핑을 지키면 얼룩·잔사 문제를 크게 줄일 수 있습니다."),
        ("유지관리와 재도포 타이밍", "주행 환경이 거칠수록 점검 주기를 짧게 잡아야 합니다. 발수 저하, 오염 부착 증가, 광택 저하가 동시에 보이면 부분 보강 또는 재도포를 고려하세요."),
    ]
    idx = variation % 3
    title = f"{kw} 내구성 높이는 관리 가이드 {idx + 1}"
    body_blocks: list[str] = []
    plain_blocks: list[str] = []
    for h2, p in sections:
        body_blocks.append(f"<h2>{h2}</h2><p>{p}</p>")
        plain_blocks.append(f"{h2}\n{p}")
    body_html = "".join(body_blocks)
    body_plain = "\n\n".join(plain_blocks)
    return {
        "title": title,
        "meta_description": f"{kw} 사용 시 내구성을 높이기 위한 적용 순서와 유지관리 포인트를 정리했습니다.",
        "unique_angle_ko": "실사용 루틴 기준으로 도포 순서와 유지관리 타이밍을 함께 제시합니다.",
        "body_html": body_html,
        "body_plain": body_plain,
        "tags": tags,
        "image_prompts": [
            "close-up ceramic coating on car paint, studio lighting, high detail",
            "car detailing process with microfiber towel, clean garage, realistic",
            "water beading on coated car surface, macro photography, cinematic",
        ],
        "internal_links_ko": ["세차 전처리 체크리스트", "코팅 후 유지관리 루틴"],
    }


def create_blog_article(
    keyword: str,
    *,
    variation: int = 0,
    avoid_titles: list[str] | None = None,
    guideline: str = "",
    bypass_duplicate: bool = False,
) -> dict[str, Any]:
    """키워드 기반 고유 블로그 패키지. HTML에 밑줄 태그 금지."""
    kw = (keyword or "").strip()
    if not kw:
        return {"ok": False, "error": "keyword 필요"}

    cfg = _load_cfg().get("content") or {}
    tone = cfg.get("tone") or "전문적·신뢰·독창적"
    avoid = "\n".join(f"- {t}" for t in (avoid_titles or [])[:10])
    angle_hints = [
        "실사용 후기·체험담 각도",
        "2026년 최신 트렌드·비교표 각도",
        "초보자 가이드·단계별 튜토리얼 각도",
        "전문가 Q&A·FAQ 중심 각도",
        "사례 연구·Before/After 각도",
    ]
    angle = angle_hints[variation % len(angle_hints)]
    user_guideline = load_writing_guideline(guideline)
    try:
        from integrations.blog_evolution import blog_evolution_context_for_prompt

        evo_ctx = blog_evolution_context_for_prompt(kw)
    except Exception:
        evo_ctx = ""
    guideline_block = "\n\n".join(
        x for x in (user_guideline, evo_ctx) if x
    ) or "(없음 — 키워드·톤만 반영)"

    prompt = f"""블로그 자동 발행용 고유 원고 (한국어 JSON만).

타깃 키워드: {kw}
톤: {tone}
독창 각도 (반드시 반영): {angle}
변형 번호: {variation}

★ 사용자 지침 (최우선 반영):
{guideline_block}

금지:
- 다른 글과 동일한 제목·도입·본문 구조
- <u> 태그, text-decoration: underline, 밑줄 서식
- 표절·복붙 느낌

피해야 할 기존 제목:
{avoid or '(없음)'}

JSON 키:
- title (검색 최적화, 40자 내외)
- meta_description (120자)
- unique_angle_ko (이 글만의 차별점 1문장)
- body_html (1500~2500자, H2 3~5, <p><h2><ul><li>만 사용, 밑줄 금지)
- body_plain (HTML 없는 본문)
- tags (정확히 30개 — 네이버 해시태그, # 없이, 2~20자)
- image_prompts (3개 — 본문 섹션별 영어 이미지 생성 프롬프트)
- internal_links_ko (2개 제안)
"""
    system = (
        "SEO 블로그 카피라이터. JSON만 출력. "
        "매번 완전히 다른 구조·표현·사례로 작성."
    )
    raw = _gemini(prompt, system=system)
    m = re.search(r"\{[\s\S]*\}", raw)
    if not m:
        if not raw:
            data = _build_fallback_article(kw, variation=variation)
            data["fallback"] = True
            data["fallback_reason"] = "llm_no_response"
            data["keyword"] = kw
            data["variation"] = variation
            data["created_at"] = time.time()
            dup = check_duplicate(
                keyword=kw,
                title=data.get("title") or "",
                body=data.get("body_plain") or data.get("body_html") or "",
            )
            data["duplicate_check"] = dup
            return {"ok": dup.get("ok", True), "article": data, "duplicate_check": dup}
        return {"ok": False, "error": "JSON 파싱 실패", "raw": raw[:1500]}
    try:
        data: dict[str, Any] = json.loads(m.group(0))
    except Exception:
        data = _build_fallback_article(kw, variation=variation)
        data["fallback"] = True
        data["fallback_reason"] = "json_parse_error"
    data["body_html"] = re.sub(r"</?u>", "", data.get("body_html") or "", flags=re.I)
    data["keyword"] = kw
    data["variation"] = variation
    data["created_at"] = time.time()

    dup = (
        {"ok": True, "skipped": True, "reason": "dry_run_bypass"}
        if bypass_duplicate
        else check_duplicate(
            keyword=kw,
            title=data.get("title") or "",
            body=data.get("body_plain") or data.get("body_html") or "",
        )
    )
    data["duplicate_check"] = dup
    return {"ok": dup.get("ok", True), "article": data, "duplicate_check": dup}


def create_unique_article(keyword: str, *, guideline: str = "") -> dict[str, Any]:
    """중복 시 자동 재생성 (최대 N회)."""
    cfg = _load_cfg().get("duplicate") or {}
    max_attempts = int(cfg.get("max_regenerate_attempts") or 3)
    titles: list[str] = []
    last: dict[str, Any] = {}

    for i in range(max_attempts):
        r = create_blog_article(keyword, variation=i, avoid_titles=titles, guideline=guideline)
        last = r
        art = r.get("article") or {}
        titles.append(str(art.get("title") or ""))
        if r.get("ok") and (r.get("duplicate_check") or {}).get("ok", True):
            return r
    return last


def create_preview_article(keyword: str, *, guideline: str = "") -> dict[str, Any]:
    """미리보기 전용 글 생성: 중복 검사 우회."""
    return create_blog_article(
        keyword,
        variation=int(time.time()) % 7,
        avoid_titles=None,
        guideline=guideline,
        bypass_duplicate=True,
    )
