# -*- coding: utf-8 -*-
"""블로그 원고·이미지 생성 (Gemini/Vertex). SDK 가용성 체크 및 독립 async 함수."""

"""
[지침 고정 — 변경 시 주의]
- DEFAULT_MASTER_GUIDELINES: 글 유형별 제품 매핑, Truth Table, 비교 로직, 키워드 우선순위의 단일 기준.
- generate_content() 내 keyword_instruction(글 유형별 키워드 무시/필터) 및 scope_instruction(유형별 범위)는
  위 마스터 지침 및 아래 POST_TYPES와 일치해야 함. 지침 수정 시 두 곳 모두 맞출 것.
- GUI 글 유형 드롭다운 값은 POST_TYPES와 동일한 문자열 사용 권장.
"""
import asyncio
import io
import os
import random
import re
import threading
from datetime import datetime

import config as cfg
from blog_constants import POST_TYPES, PRODUCT_KEYWORDS, PRODUCT_LABELS, PRODUCT_POST_TYPE
from blog_naeo import (
    NAEO_POST_TYPE,
    default_keyword,
    is_naeo_post_type,
    outline_for_prompt,
    template_outline as naeo_template_outline,
    template_tags as naeo_template_tags,
)
from blog_text_utils import strip_strikethrough_markers

# --- SDK: 필요할 때만 import (GUI 시작 시 Vertex/PIL 로드 방지) ---
GENAI_CLIENT_AVAILABLE = False
VERTEX_AVAILABLE = False
_GenAIClient = None
_genai_types = None
_genai_tried = False
_vertexai = None
_vertex_tried = False
_GenerativeModel = None
_Part = None
_ImageGenerationModel = None


def _lazy_genai():
    global GENAI_CLIENT_AVAILABLE, _GenAIClient, _genai_types, _genai_tried
    if _genai_tried:
        return GENAI_CLIENT_AVAILABLE
    _genai_tried = True
    try:
        from google.genai import Client as GenAIClient
        from google.genai import types as genai_types

        _GenAIClient = GenAIClient
        _genai_types = genai_types
        GENAI_CLIENT_AVAILABLE = True
    except ImportError:
        GENAI_CLIENT_AVAILABLE = False
    return GENAI_CLIENT_AVAILABLE


def _lazy_vertex():
    global VERTEX_AVAILABLE, _vertexai, _GenerativeModel, _Part, _ImageGenerationModel, _vertex_tried
    if _vertex_tried:
        return VERTEX_AVAILABLE
    _vertex_tried = True
    try:
        import vertexai
        from vertexai.generative_models import GenerativeModel, Part
        from vertexai.preview.vision_models import ImageGenerationModel

        _vertexai = vertexai
        _GenerativeModel = GenerativeModel
        _Part = Part
        _ImageGenerationModel = ImageGenerationModel
        VERTEX_AVAILABLE = True
    except ImportError:
        VERTEX_AVAILABLE = False
    return VERTEX_AVAILABLE


def _pil_image():
    from PIL import Image

    return Image

GEMINI_TEXT_MODEL = os.environ.get("BLOG_GEMINI_TEXT_MODEL", "gemini-2.5-flash")
OLLAMA_TEXT_MODEL = os.environ.get("BLOG_OLLAMA_MODEL", "qwen3:4b")
OLLAMA_BASE_URL = os.environ.get("BLOG_OLLAMA_URL", "http://localhost:11434").rstrip("/")
OLLAMA_READ_TIMEOUT = int(os.environ.get("BLOG_OLLAMA_TIMEOUT", "120"))
CLAUDE_CODE_CMD = os.environ.get("BLOG_CLAUDE_CMD", "claude").strip() or "claude"
CLAUDE_CODE_MODEL = (
    os.environ.get("BLOG_CLAUDE_MODEL", "claude-fable-5").strip() or "claude-fable-5"
)
CLAUDE_CODE_TIMEOUT = int(os.environ.get("BLOG_CLAUDE_TIMEOUT", "600"))
_OLLAMA_FAST_MODELS = (
    "qwen3:4b",
    "deepseek-r1:1.5b",
    "hermes3:latest",
    "gemma2:2b",
    "qwen3:8b",
)
_OLLAMA_HEAVY_HINTS = ("qwen3:8b", "deepseek-r1:8b", "qwen3.6", ":31b", ":20b", "gpt-oss")
_OLLAMA_DEGRADED = False
TEXT_PROVIDER_DEFAULT = os.environ.get("BLOG_TEXT_PROVIDER", "gemini").strip().lower()


def _api_sparing_enabled() -> bool:
    """1이면 Gemini/Vertex 등 유료 API 폴백·자동 호출을 막고 로컬 엔진만 사용."""
    return os.environ.get("BLOG_API_SPARING", "1").strip().lower() in ("1", "true", "yes", "on")


def _safe_log(log_func, message: str) -> None:
    """콘솔 cp949 등에서 이모지 로그가 실패해도 원고 생성 결과는 유지."""
    if not log_func:
        return
    try:
        log_func(message)
    except Exception:
        try:
            log_func(str(message).encode("ascii", errors="replace").decode("ascii"))
        except Exception:
            pass

_OLLAMA_SYSTEM = (
    "너는 한국어 네이버 블로그 원고 작가다. "
    "요청한 출력 형식([TITLE], [OUTLINE], [BODY], [TAGS], [IMAGE_DESC] 등)을 정확히 따른다. "
    "네이버 AI 브리핑 5원칙(직접경험·일관주제·진정성·구조·최신성)과 "
    "7:2:1 비율, 글 유형별 제품 매핑, Truth Table, 금지어를 반드시 준수한다. "
    "AI가 쓴 티가 나는 상투문·판매 멘트 대신 현장 경험·구체 수치·질문형 마무리로 쓴다. "
    "영어·추론 과정 없이 최종 한국어 결과만 출력한다. "
    "취소선(~~, <s>, <del>)은 절대 쓰지 않는다."
)

_OLLAMA_TYPE_RULES = {
    "자동차 정보": (
        "【이 유형만】 퀵(14%), 티탄(28% 원액), 레진(60% 원액+30% 레진), 전용 건식 관리제. "
        "【절대 금지】 리빙코트, 싱크대, 수전, 욕실, 가구, 주방."
    ),
    "바이크 정보": (
        "【이 유형만】 바이크 유리막·퀵/티탄/레진·전용 건식 관리제. "
        "【절대 금지】 리빙코트, 싱크대, 수전, 욕실, 승용차 위주 서술."
    ),
    "코팅제 정보": (
        "【이 유형만】 코팅 원리·퀵/티탄/레진·전용 건식 관리제. "
        "【절대 금지】 리빙코트, 생활용(주방·욕실·가구)."
    ),
    "제품 홍보": (
        "【이 유형만】 듀라코트 리빙코트(주방·욕실·가구). "
        "【절대 금지】 퀵·티탄·레진 %, 자동차/바이크 코팅 스펙."
    ),
    "맛집/일상": (
        "【이 유형만】 맛집·일상 에세이. 키워드·제품명 무시. "
        "【절대 금지】 듀라코트·코팅제·퀵·티탄·레진·판매 유도."
    ),
    "취미글": (
        "【이 유형만】 낚시·바이크 투어·시승·취미 에세이. 키워드·제품명 무시. "
        "【절대 금지】 코팅제 홍보·제품 스펙."
    ),
    "정보성 팁": (
        "【이 유형만】 10년 경력 시공·관리 노하우, 천연 비누 팁. 제품 언급 최소. "
        "【절대 금지】 근거 없는 수치·허위 스펙."
    ),
    NAEO_POST_TYPE: (
        "【이 유형만】 NAEO, SEO·AEO·GEO, 네이버 AI·블로그 유입·검색 변화. "
        "【절대 금지】 코팅제·듀라코트·퍼마코트·스마트스토어 판매 유도."
    ),
}

_BANNED_BLOG_PHRASES = (
    "안녕하세요",
    "알아보겠습니다",
    "도움이 되었으면 합니다",
    "짜증 나시죠",
    "지금 바로 구매",
    "지금만",
    "한정 수량",
    "최저가",
    "무조건 추천",
    "강력 추천",
    "필수템",
    "압도적",
    "혁신적인 성능",
    "최고의 성능",
    "판매 중",
    "특가",
    "카페에서 나와 집으로 향하는",
    "오래도록 새것처럼",
    "숨겨진 공간의 코팅",
    "온몸으로 느낄 수 있습니다",
    "이 지킴이 결국",
    "연장선상에는 우리 일상",
)

_CONVERSION_SOFT_SELL_BLOCK = (
    "【전환형 글쓰기 — 홍보가 아닌 판매】\n"
    "- 한 글 = 독자 고민 1개 해결. 제목에 제품명·'최고'·'강력 추천'·'판매' 금지.\n"
    "- 본문 70%: 증상→원인→체크리스트→실패 사례. 20%: 원리·성분(Truth Table만). "
    "10%: '이런 조건이면 퀵/티탄/레진 중 ~' 선택 가이드.\n"
    "- 스펙·가격 나열표 금지. 대신 '선택 기준표'(DIY vs 전문 시공, 왁스 vs 유리막) 1개.\n"
    "- 솔직한 제외 조건 1문장 필수: '이런 분께는 굳이 필요 없습니다'.\n"
    "- CTA는 마지막 1문단만: '직접 하기 어렵다면 ~ 함량·시공 난이도 기준으로 비교' 톤. "
    "'지금 구매'·링크 남발 금지.\n"
)

# 감성 에세이·주제 이탈 서사 (탐지 시 재생성 또는 삭제)
_NARRATIVE_ESSAY_PATTERNS = (
    r"오랫동안\s+타다\s+보면",
    r"미세한\s+진동",
    r"노면의\s+작은\s+충격",
    r"거친\s+주행\s+환경",
    r"진정한\s*['\"]?\s*보호\s*['\"]?\s*라고",
    r"카페에서\s+나와",
    r"집으로\s+향하는\s+길",
    r"괜스레\s+집안",
    r"지키는\s+취미",
    r"우리\s+집을\s+오래도록",
    r"숨겨진\s+공간",
    r"리빙\s*코팅의\s+중요성",
    r"일상\s+공간을",
    r"한\s+가지\s+장면.*?길게\s+끌고",
)

_ANTI_ESSAY_WRITING_BLOCK = (
    "【에세이·서사 금지】\n"
    "- '바이크를 오랫동안 타다 보면…온몸으로 느낄 수 있습니다' 같은 장문 감성·철학 독백 도입 금지.\n"
    "- '카페에서 나와 집으로 향하는 길', '지키는 취미'처럼 무관한 일상 장면으로 주제를 넘기는 전개 금지.\n"
    "- 바이크/자동차/코팅제 글에서 리빙·주방·욕실·가구·'우리 집을 오래도록 새것처럼' 소제목·본문 절대 금지.\n"
    "- 제품 라인 교차 홍보 금지(바이크 글→리빙코트, 자동차 글→주방 코팅 등).\n"
    "- 도입은 키워드 관련 질문·체크리스트·팁 1~2문장으로 바로 시작. 스토리텔링 에세이 형식 금지.\n"
)

# 네이버 검색 공식 가이드(2026.05) + Autoblog 강점(7:2:1·Truth Table·현장 페르소나) 통합
_NAVER_MATE_FIVE_PRINCIPLES = (
    "【네이버 AI 브리핑·메이트 5원칙】\n"
    "1.직접 경험: 본인 시공·실패·현장 일화·구체 수치를 2문장 이상 반드시 포함.\n"
    "2.일관된 주제: 선택한 글 유형·키워드 범위만. 잡주제·짜깁기 금지.\n"
    "3.거짓 없는 진정성: 협찬·내돈내산·체험 관계를 본문 상단에 한 줄 표기. 확인 안 된 사실 단정 금지.\n"
    "4.읽기 쉬운 구조: ## 소제목, 짧은 문단, 표·이미지 핵심은 텍스트로도 서술.\n"
    "5.최신성: '최근 시공', '이번 달', '올해 장마' 등 시점을 구체적으로.\n"
    "【Autoblog 강점 반영】 7:2:1 해결 중심, Truth Table 수치만, 계정별 말투, 영국 수출 신뢰, 금지어·그래핀 오류 차단."
)

_EXPERIENCE_OPENERS = {
    "자동차 정보": (
        "지난주 시공 현장에서 고객이 물어본 게 '{kw}' 관련이었습니다.",
        "10년 넘게 광택기를 잡으며 '{kw}' 작업할 때마다 느끼는 건 표면 준비가 절반이라는 점입니다.",
    ),
    "바이크 정보": (
        "주말 라이딩 전 체인·도장면을 점검하다 '{kw}' 문의가 또 들어왔습니다.",
        "할리/스포츠 바이크 현장에서 '{kw}'는 날씨·보관 환경에 따라 체감이 크게 달라집니다.",
    ),
    "코팅제 정보": (
        "제조 라인에서 '{kw}' 배합을 테스트할 때마다 도포 간격이 결과를 갈라놓습니다.",
        "현장에서 '{kw}' 성분 문의가 많아, Truth Table 기준으로만 정리했습니다.",
    ),
    "제품 홍보": (
        "주방·욕실 상담에서 '{kw}' 때문에 찾아오시는 분이 많아 직접 써 본 기준으로 적습니다.",
        "리빙코트 시공 후 일주일·한 달 사용감을 기준으로 '{kw}'를 정리했습니다.",
    ),
    "맛집/일상": (
        "영업·시공 일정 사이에 들른 곳이라 '{kw}' 기억을 짧게 남깁니다.",
        "발로 뛰다 우연히 찾은 '{kw}' — 주차와 동선 위주로 적습니다.",
    ),
    "취미글": (
        "'{kw}' 하면서 느낀 건 장비보다 준비가 체감을 좌우한다는 점입니다.",
        "취미 일정 중 '{kw}' 경험을 기록해 둡니다.",
    ),
    "정보성 팁": (
        "10년 현장에서 '{kw}' 관련으로 가장 많이 받는 질문부터 정리했습니다.",
        "천연 비누·코팅 제조를 오래 하며 '{kw}'에 대해 지키는 원칙이 있습니다.",
    ),
    NAEO_POST_TYPE: (
        "최근 블로그 유입을 보며 '{kw}'를 정리해 봤습니다.",
        "네이버 검색·AI 변화를 따라가며 '{kw}'에 대해 글로 남깁니다.",
    ),
}


def _extract_user_experience_notes(config: dict) -> str:
    """GUI 추가 지침·experience_notes에서 사람 경험 메모만 추출."""
    if not isinstance(config, dict):
        return ""
    raw = (config.get("experience_notes") or "").strip()
    if raw:
        return raw[:800]
    wg = (config.get("writing_guidelines") or "")
    m = re.search(r"\[경험[^\]]*\](.*?)(?:\n\[|\Z)", wg, re.S | re.I)
    if m:
        return m.group(1).strip()[:800]
    return ""


def _build_authenticity_notice(config: dict, post_type: str) -> str:
    """네이버 5원칙 '진정성' — 협찬·체험 관계 고지."""
    if not isinstance(config, dict):
        return ""
    custom = (config.get("sponsorship_label") or config.get("ad_disclosure") or "").strip()
    if custom:
        return custom
    pt = (post_type or "").strip()
    choice = (config.get("product_choice") or "none").strip().lower()
    if pt in ("맛집/일상", "취미글", "알림글"):
        return ""
    if pt == "제품 홍보" or choice not in ("", "none"):
        return "※ 본 글은 나눔랩 제품 사용·시공 경험을 바탕으로 작성했으며, 상업적 이해관계가 있을 수 있습니다."
    return ""


def _build_experience_brief(
    config: dict,
    post_type: str,
    keyword: str,
    account_id: str | None,
) -> str:
    """AI 초안에 주입할 '사람 경험 패킷' — 네이버 직접 경험 원칙."""
    kw = (keyword or "이 주제").strip() or "이 주제"
    pt = (post_type or "").strip() or "자동(매번 랜덤)"
    lines = []
    user_notes = _extract_user_experience_notes(config)
    if user_notes:
        lines.append(f"【작성자 경험 메모 — 반드시 본문에 반영】\n{user_notes}")
    pool = _EXPERIENCE_OPENERS.get(pt) or _EXPERIENCE_OPENERS.get("정보성 팁", ())
    if pool:
        lines.append(f"【도입 참고】 {random.choice(pool).format(kw=kw)}")
    lines.append(f"【이번 앵글】 {random.choice(_VIVID_ANGLES)}")
    if account_id == "hymini1":
        lines.append("【말투】 10년 경력 제조 이사, 신뢰감 있는 ~입니다. 현장·수치 중심.")
    elif account_id == "hymini11":
        lines.append("【말투】 라이더 시선, 친근한 ~해요. 관리·시공·보관 팁 중심. 감성 에세이·철학 독백·카페·집 풍경 묘사 금지.")
    return "\n".join(lines)


def _perfect_blog_writing_block(
    *,
    post_type: str,
    account_id: str | None,
    config: dict,
    keyword: str = "",
    min_body_len: int | None = None,
    for_outline: bool = False,
) -> str:
    """네이버 정책 + Autoblog 강점을 한 블록으로 — Ollama/Gemini 공통."""
    parts = [_NAVER_MATE_FIVE_PRINCIPLES, _CONVERSION_SOFT_SELL_BLOCK]
    notice = _build_authenticity_notice(config, post_type)
    if notice:
        parts.append(f"【고지 문구】 본문 맨 앞에 다음 문장을 그대로 넣을 것:\n{notice}")
    if not for_outline:
        parts.append(_build_experience_brief(config, post_type, keyword, account_id))
        parts.append(_ANTI_ESSAY_WRITING_BLOCK)
    if for_outline:
        parts.append(
            "【개요 설계】 제목=검색 의도+경험 신호(판매 문구 금지). "
            "개요=##소제목 4~6개, 각 줄 '## 제목 → 한 줄 설명'. AI 브리핑이 인용하기 쉬운 구조."
        )
    elif min_body_len and min_body_len > 0:
        parts.append(
            f"【본문 구조】 공감(상황·질문) → 해결(원리·팁·표) → 입증(현장 경험·Before/After). "
            f"최소 {min_body_len}자. 마무리는 독자 질문 1문장."
        )
        parts.append(
            "【가독성】 ## 소제목 아래 빈 줄 1개. 문단은 2~3문장(120자 내외)으로 짧게. "
            "핵심 팁은 - 불릿 또는 1. 2. 3. 번호 목록. 한 문단에 정보를 과하게 몰아넣지 말 것. "
            "본문 중간(전반부 끝)과 마지막 소제목 직전에 [IMAGE] 마커를 각각 한 줄로 넣을 것."
        )
    return "\n\n".join(parts)


def _improve_body_readability(body: str) -> str:
    """짧은 문단·소제목 간격으로 읽기 쉽게 정리."""
    text = (body or "").strip()
    if not text:
        return text
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"^(##\s+.+)$", r"\1\n", text, flags=re.M)
    out_lines: list[str] = []
    for block in re.split(r"\n\s*\n", text):
        block = block.strip()
        if not block:
            continue
        if block.startswith("##") or block.startswith("[IMAGE") or block.startswith("|"):
            out_lines.append(block)
            continue
        if block.startswith("- ") or re.match(r"^\d+\.\s", block):
            out_lines.append(block)
            continue
        sentences = re.split(r"(?<=[.!?…])\s+", block)
        chunk: list[str] = []
        chunk_len = 0
        for sent in sentences:
            sent = sent.strip()
            if not sent:
                continue
            if chunk_len + len(sent) > 130 and chunk:
                out_lines.append(" ".join(chunk))
                chunk = [sent]
                chunk_len = len(sent)
            else:
                chunk.append(sent)
                chunk_len += len(sent)
        if chunk:
            out_lines.append(" ".join(chunk))
    return "\n\n".join(out_lines)


def _inject_image_markers_middle_end(body: str) -> str:
    """이미지 2장: 본문 중간·끝에 [IMAGE] 마커 삽입."""
    text = (body or "").strip()
    if not text:
        return text
    if text.count("[IMAGE]") >= 2:
        return text
    text = re.sub(r"\[IMAGE\d*\]|\[이미지\d*\]", "", text, flags=re.I)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()

    sections = re.split(r"(?=^##\s+)", text, flags=re.M)
    sections = [s for s in sections if s.strip()]
    if len(sections) >= 3:
        mid_idx = max(1, len(sections) // 2)
        sections[mid_idx] = sections[mid_idx].rstrip() + "\n\n[IMAGE]\n"
        sections[-1] = sections[-1].rstrip() + "\n\n[IMAGE]\n"
        return "".join(sections)

    paras = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    if len(paras) >= 4:
        mid = len(paras) // 2
        paras.insert(mid, "[IMAGE]")
        if paras[-1] != "[IMAGE]":
            paras.append("[IMAGE]")
        return "\n\n".join(paras)

    half = max(1, len(text) // 2)
    split_at = text.find("\n\n", half)
    if split_at < 0:
        split_at = half
    return text[:split_at].rstrip() + "\n\n[IMAGE]\n\n" + text[split_at:].lstrip() + "\n\n[IMAGE]\n"


def _finalize_blog_article(
    body: str,
    tags: str,
    *,
    config: dict,
    post_type: str,
    title: str,
    keyword: str,
    account_id: str | None,
) -> tuple[str, str]:
    """발행 직전 후처리: 진정성 고지, 이미지 텍스트 보조, 질문형 마무리."""
    text = strip_strikethrough_markers((body or "").strip())
    notice = _build_authenticity_notice(config, post_type)
    if notice and notice not in text:
        text = f"{notice}\n\n{text}"
    text = _improve_body_readability(text)
    text = _scrub_cross_topic_content(text, post_type)
    text = _inject_image_markers_middle_end(text)
    tail = text[-280:] if len(text) > 280 else text
    if "?" not in tail and "？" not in tail:
        if account_id == "hymini11":
            text = text.rstrip() + "\n\n비슷한 상황 겪어 보신 적 있어요? 댓글로 알려주세요.\n"
        else:
            text = text.rstrip() + "\n\n비슷한 고민이 있으시면 댓글로 상황을 알려주시면 참고해서 답드리겠습니다.\n"
    tags = _normalize_generated_tags(tags, keyword, "blog")
    return text, tags


def _ollama_type_rules(post_type: str) -> str:
    return _OLLAMA_TYPE_RULES.get(
        (post_type or "").strip(),
        "7:2:1 비율(정보70·전문20·홍보10). 해결 중심. 글 유형에 맞는 주제만.",
    )


def _ollama_async_deadline(num_predict: int) -> float:
    """HTTP read_timeout보다 여유 있게 asyncio 상한을 둔다."""
    return float(_ollama_read_timeout_for(num_predict)) + 90.0


def _parse_min_body_chars_from_text(*chunks: str) -> int | None:
    """마스터 지침·프롬프트에서 'N자 이상' 분량 요구를 추출(여러 개면 최댓값)."""
    found: list[int] = []
    for chunk in chunks:
        if not chunk:
            continue
        text = str(chunk)
        patterns = (
            r"(?:최소|minimum|본문|분량)[^\n]{0,30}?([\d]{1,2},?[\d]{3}|[\d]{3,5})\s*자",
            r"([\d]{1,2},?[\d]{3}|[\d]{3,5})\s*자\s*(?:이상|이상의|넘게|초과|분량)",
        )
        for pat in patterns:
            for m in re.finditer(pat, text, re.I):
                try:
                    n = int(m.group(1).replace(",", ""))
                except (ValueError, IndexError):
                    continue
                if 200 <= n <= 20000:
                    found.append(n)
    return max(found) if found else None


def _resolve_min_body_len(
    master_guidelines: str,
    extra_guidelines: str = "",
    *,
    ollama_mode: bool,
    config: dict | None = None,
) -> int:
    """지침·설정에서 본문 최소 글자 수를 결정."""
    explicit = None
    if isinstance(config, dict):
        raw = config.get("min_body_chars") or config.get("min_body_len")
        if raw is not None and str(raw).strip():
            try:
                explicit = int(str(raw).replace(",", "").strip())
            except ValueError:
                explicit = None
    wiki_min = None
    try:
        from drawer.wiki import parse_min_chars_from_wiki

        wiki_min = parse_min_chars_from_wiki()
    except Exception:
        wiki_min = None
    parsed = _parse_min_body_chars_from_text(
        master_guidelines,
        extra_guidelines,
        _default_guidelines(),
        DEFAULT_MASTER_GUIDELINES,
    )
    if wiki_min:
        parsed = max(parsed or 0, wiki_min)
    floor = 900 if ollama_mode else 1200
    candidates = [n for n in (explicit, parsed, floor) if isinstance(n, int) and n > 0]
    return max(candidates) if candidates else floor


def _ollama_body_num_predict(min_body_len: int) -> int:
    """한국어 본문 목표 글자 수에 맞춘 Ollama num_predict."""
    return min(3200, max(700, int(min_body_len * 2.2)))


def _pad_body_to_min_length(body: str, min_chars: int) -> str:
    """템플릿·폴백 본문을 최소 분량까지 보강."""
    if len(body or "") >= min_chars:
        return body
    extra_blocks = [
        "현장에서 자주 받는 질문은 '얼마나 자주 관리해야 하느냐'입니다. 사용 환경과 노출 정도에 따라 주기가 달라지지만, 발수가 약해지기 전에 가볍게 점검하는 편이 마감 유지에 유리합니다.\n\n",
        "셀프로 진행할 때는 표면 온도와 습도를 먼저 확인하는 것이 중요합니다. 직사광선 아래 뜨거운 상태에서 작업하면 마감이 들쭉날쭉해질 수 있습니다.\n\n",
        "완공 직후에는 물을 뿌려 발수 상태와 잔여물을 함께 점검해 보세요. 미세한 얼룩이 남아 있으면 그때 바로 정리하는 것이 이후 관리 시간을 크게 줄여 줍니다.\n\n",
        "같은 제품이라도 도포 두께와 건조 시간을 지키느냐에 따라 체감 내구성이 달라집니다. 한 번에 두껍게 바르기보다 얇게 여러 번 나눠 작업하는 편이 균일합니다.\n\n",
    ]
    out = (body or "").rstrip() + "\n\n"
    i = 0
    while len(out) < min_chars and i < 40:
        out += extra_blocks[i % len(extra_blocks)]
        i += 1
    return out


def _build_ollama_guidelines_block(
    master_guidelines: str,
    post_type: str,
    scope_instruction: str,
    keyword_instruction: str = "",
    *,
    account_id: str | None = None,
    config: dict | None = None,
    keyword: str = "",
    max_chars: int = 1200,
    min_body_len: int | None = None,
    for_outline: bool = False,
) -> str:
    """로컬 Ollama용 — 네이버 5원칙 + Autoblog 강점을 압축 주입."""
    cfg = config if isinstance(config, dict) else {}
    user_extra = _trim_guidelines_for_prompt(
        (master_guidelines or "").strip(),
        max_chars,
    )
    parts = [
        _perfect_blog_writing_block(
            post_type=post_type,
            account_id=account_id,
            config=cfg,
            keyword=keyword,
            min_body_len=min_body_len,
            for_outline=for_outline,
        ),
        f"【글 유형】 {post_type}",
        _ollama_type_rules(post_type),
        keyword_instruction.strip() if keyword_instruction else "",
        scope_instruction.strip() if scope_instruction else "",
        "【Truth Table】 퀵14%, 티탄28%원액, 레진60%+30%. 자동차/바이크=전용 건식 관리제. Living=리빙코트만.",
        "【비교】 자사 제품 간 비교 금지.",
    ]
    if user_extra:
        parts.append("【추가 지침】\n" + user_extra)
    return "\n\n".join(p for p in parts if p)


# strip_strikethrough_markers → blog_text_utils (re-export)


def _extract_body_from_ollama_text(text: str) -> str:
    """Ollama 응답에서 [BODY] 파싱 — 태그 누락·부분 출력도 복구."""
    raw = _trim_to_format_markers(text or "")
    if not raw:
        return ""
    m = re.search(r"\[BODY\](.*?)(?:\[TAGS\]|$)", raw, re.S | re.I)
    if m:
        body = m.group(1).strip()
        if len(body) >= 80:
            return body
    if re.search(r"\[BODY\]", raw, re.I):
        rest = re.split(r"\[BODY\]", raw, flags=re.I, maxsplit=1)[-1]
        rest = re.split(r"\[TAGS\]", rest, flags=re.I)[0].strip()
        if len(rest) >= 80:
            return rest
    if "##" in raw and not _looks_like_reasoning_leak(raw):
        return raw.strip()
    if len(raw) >= 150 and re.search(r"[가-힣]", raw) and not _looks_like_reasoning_leak(raw):
        return raw.strip()
    return ""


def _trim_to_format_markers(text: str) -> str:
    """모델의 영어 추론/잡담을 건너뛰고 [TITLE]/[BODY] 등 형식 블록부터 사용."""
    if not text:
        return text
    markers = ("[TITLE]", "[OUTLINE]", "[BODY]", "[TAGS]", "[IMAGE_DESC]")
    positions = [text.find(m) for m in markers if text.find(m) >= 0]
    if positions:
        return text[min(positions) :].strip()
    for marker in ("## ", "# "):
        idx = text.find(marker)
        if idx >= 0:
            return text[idx:].strip()
    return text.strip()


def _looks_like_reasoning_leak(s: str) -> bool:
    if not s:
        return True
    low = s.lower()
    leak_hints = (
        "let me ",
        "the user wants",
        "specified format",
        "i need to",
        "wait,",
        "character count",
    )
    if any(h in low for h in leak_hints):
        return True
    if len(s) > 80 and sum(1 for c in s if ord(c) < 128) / max(len(s), 1) > 0.55:
        return True
    return False


def _normalize_generated_title(raw: str, keyword: str, fallback: str) -> str:
    title = strip_strikethrough_markers(re.sub(r"\*\*([^*]+)\*\*", r"\1", (raw or "").strip()))
    title = re.sub(r"^[,.\-–—\s]+", "", title).strip()[:100]
    if len(title) < 4 or _looks_like_reasoning_leak(title):
        kw = (keyword or "").strip()
        return f"{kw} 활용 후기" if kw else fallback
    return title


def _normalize_generated_tags(raw: str, keyword: str, fallback: str = "blog") -> str:
    tags = (raw or "").strip()
    tags = tags.split("\n")[0].strip()
    tags = re.sub(r"^#+", "", tags).strip()
    if not tags or len(tags) > 120 or _looks_like_reasoning_leak(tags):
        kw = (keyword or "").strip()
        return f"{kw},블로그,후기" if kw else fallback
    return tags


def _extract_gemini_text(res) -> str:
    """google-genai / legacy generativeai 응답에서 텍스트 추출."""
    if res is None:
        return ""
    text = getattr(res, "text", None)
    if text:
        return str(text).strip()
    candidates = getattr(res, "candidates", None) or []
    parts = []
    for cand in candidates:
        content = getattr(cand, "content", None)
        if not content:
            continue
        for part in getattr(content, "parts", None) or []:
            t = getattr(part, "text", None)
            if t:
                parts.append(t)
    return "\n".join(parts).strip()


async def _gemini_generate(api_key: str, prompt: str):
    """텍스트 생성: google-genai 우선, 패키지 없을 때만 구 google.generativeai."""
    if _lazy_genai():
        client = _GenAIClient(api_key=api_key)

        def _call():
            return client.models.generate_content(
                model=GEMINI_TEXT_MODEL,
                contents=prompt,
            )

        return await asyncio.to_thread(_call)
    raise RuntimeError(
        "google-genai 패키지가 필요합니다. "
        "pip install google-genai  (구 google-generativeai는 더 이상 사용하지 않습니다)"
    )


def _is_quota_error(err_msg: str) -> bool:
    msg = (err_msg or "").lower()
    return (
        "429" in msg
        or "quota" in msg
        or "resource_exhausted" in msg
        or "depleted" in msg
        or "billing" in msg
    )


def _api_key_suffix(api_key: str) -> str:
    key = (api_key or "").strip()
    return f"...{key[-6:]}" if len(key) >= 6 else "(없음)"


def _collect_text_api_keys(source) -> list:
    """Gemini 텍스트용 API 키 목록 (중복 제거, gemini_key 우선)."""
    if isinstance(source, dict):
        keys = []
        for field in ("gemini_key", "vertex_api_key"):
            k = (source.get(field) or "").strip()
            if k and k not in keys:
                keys.append(k)
        return keys
    k = (source or "").strip()
    return [k] if k else []


def _log_quota_hint(log_func, api_key: str = ""):
    suffix = _api_key_suffix(api_key)
    log_func(
        f"      [중요] Gemini API 키({suffix})의 선불 크레딧이 소진되었습니다. "
        "같은 Google 프로젝트에서 만든 새 키는 크레딧을 공유하므로, "
        "https://aistudio.google.com 에서 충전하거나 다른 계정/프로젝트의 키를 입력 후 [저장 및 연동]을 눌러 주세요."
    )


def _normalize_text_provider(config) -> str:
    """claude | ollama(무료) | gemini(유료) | auto(구 설정 호환). GUI 한글 라벨도 인식."""
    raw = TEXT_PROVIDER_DEFAULT
    if isinstance(config, dict):
        raw = (config.get("text_provider") or TEXT_PROVIDER_DEFAULT).strip()
    s = raw.lower()
    if s in ("claude", "claude_code", "claude-code"):
        return "claude"
    if "클로드" in raw or ("claude" in s and "code" in s):
        return "claude"
    if s in ("ollama", "local", "free"):
        return "ollama"
    if s in ("auto", "hybrid"):
        return "ollama" if _api_sparing_enabled() else "auto"
    if "로컬" in raw and ("ollama" in s or "무료" in raw):
        return "ollama"
    if "ollama" in s and ("자동" in raw or "→" in raw or "->" in raw or "auto" in s):
        return "ollama" if _api_sparing_enabled() else "auto"
    if "gemini" in s and "ollama" not in s:
        return "gemini"
    if "ollama" in s:
        return "ollama"
    return "ollama" if _api_sparing_enabled() else "gemini"


def _normalize_image_provider(config) -> str:
    """pillow | pollinations | vertex | genai | auto. GUI 한글 라벨도 인식."""
    raw = os.environ.get("BLOG_IMAGE_PROVIDER", "auto").strip()
    if isinstance(config, dict):
        raw = (config.get("image_provider") or raw).strip()
    s = raw.lower()
    if "pillow" in s or "플레이스홀더" in raw:
        return "pillow"
    if s in ("free", "pollinations") or "pollinations" in s or "로컬 무료" in raw:
        return "pollinations"
    if "자동" in raw or s == "auto":
        return "auto"
    if raw.strip() == "Vertex AI" or (s == "vertex" and "자동" not in raw):
        return "vertex"
    if s in ("genai", "gen ai") or "Gen AI" in raw or "Gemini 이미지" in raw:
        return "genai"
    if _api_sparing_enabled():
        return "pollinations"
    return "auto"


def _trim_guidelines_for_prompt(text: str, max_chars: int = 8000) -> str:
    """본문 프롬프트가 과도하게 길어지지 않도록 지침을 축약."""
    t = (text or "").strip()
    if len(t) <= max_chars:
        return t
    head = max_chars // 2
    tail = max_chars - head - 40
    return t[:head] + "\n\n...[지침 중략]...\n\n" + t[-tail:]


def _shrink_prompt_for_ollama(prompt: str, max_chars: int = 14000) -> str:
    """로컬 LLM 컨텍스트·속도를 위해 지나치게 긴 프롬프트를 축약."""
    text = (prompt or "").strip()
    if len(text) <= max_chars:
        return text
    head = int(max_chars * 0.38)
    tail = int(max_chars * 0.58)
    return text[:head] + "\n\n...[중간 생략]...\n\n" + text[-tail:]


async def _ollama_ping() -> bool:
    import requests

    try:
        res = await asyncio.to_thread(requests.get, f"{OLLAMA_BASE_URL}/api/tags", timeout=4)
        return res.status_code == 200
    except Exception:
        return False


async def _ollama_ping_with_retry(log_func=None, attempts: int = 3) -> bool:
    for i in range(attempts):
        if await _ollama_ping():
            return True
        if i + 1 < attempts:
            if log_func:
                log_func(f"      Ollama 연결 재시도 ({i + 2}/{attempts})...")
            await asyncio.sleep(2)
        return False


def _is_heavy_ollama_model(name: str) -> bool:
    n = (name or "").lower()
    return any(h in n for h in _OLLAMA_HEAVY_HINTS)


async def _list_installed_ollama_models() -> set:
    import requests

    try:
        res = await asyncio.to_thread(
            requests.get, f"{OLLAMA_BASE_URL}/api/tags", timeout=5
        )
        if res.status_code == 200:
            return {m.get("name", "") for m in (res.json().get("models") or []) if m.get("name")}
    except Exception:
        pass
    return set()


async def _resolve_ollama_models(log_func) -> list:
    """BLOG_OLLAMA_MODEL 최우선, JARVIS 라우팅 시 Gemma2→Hermes→DeepSeek, 이후 가벼운 모델."""
    installed = await _list_installed_ollama_models()
    ordered = []
    env_model = (OLLAMA_TEXT_MODEL or "").strip()

    try:
        from drawer.model_router import (
            jarvis_routing_enabled,
            match_installed_ollama,
            ollama_candidates_for_task,
        )

        if jarvis_routing_enabled():
            routed = match_installed_ollama(installed, ollama_candidates_for_task("content"))
            for name in routed:
                if name not in ordered:
                    ordered.append(name)
            if routed:
                log_func(
                    f"      [모델 라우팅] 글쓰기 모델 순서: {', '.join(ordered[:4])}"
                )
    except Exception:
        pass

    if env_model:
        if env_model in installed and env_model not in ordered:
            ordered.insert(0, env_model)
        elif env_model not in ordered:
            base = env_model.split(":")[0] + ":latest"
            if base in installed:
                ordered.insert(0, base)

    for name in _OLLAMA_FAST_MODELS:
        if name in installed and name not in ordered:
            ordered.append(name)

    for name in sorted(installed):
        if name not in ordered:
            ordered.append(name)

    if not ordered:
        fallback = env_model or "qwen3:4b"
        log_func(f"      Ollama 모델 목록 확인 실패 — {fallback} 사용")
        return [fallback]
    log_func(f"      Ollama 모델 순서: {', '.join(ordered[:3])}")
    return ordered


async def _ollama_unload_all_models(log_func) -> None:
    """VRAM 점유 모델을 모두 내린다 — 여러 모델이 올라가 있으면 응답이 멈춘다."""
    import requests

    try:
        ps = await asyncio.to_thread(
            requests.get, f"{OLLAMA_BASE_URL}/api/ps", timeout=5
        )
        if ps.status_code != 200:
            return
        loaded = [m.get("name") for m in (ps.json().get("models") or []) if m.get("name")]
        if not loaded:
            return
        log_func(f"      Ollama VRAM 정리 ({len(loaded)}개 모델 언로드)...")
        for name in loaded:
            try:
                await asyncio.to_thread(
                    requests.post,
                    f"{OLLAMA_BASE_URL}/api/generate",
                    json={"model": name, "prompt": "", "keep_alive": 0},
                    timeout=15,
                )
            except Exception:
                pass
    except Exception:
        pass


async def _ollama_unload_other_models(keep_model: str, log_func) -> None:
    """VRAM에 여러 모델이 올라가 있으면 응답이 극단적으로 느려진다."""
    import requests

    try:
        ps = await asyncio.to_thread(
            requests.get, f"{OLLAMA_BASE_URL}/api/ps", timeout=5
        )
        if ps.status_code != 200:
            return
        loaded = [m.get("name") for m in (ps.json().get("models") or []) if m.get("name")]
        extras = [n for n in loaded if n != keep_model]
        if not extras:
            return
        log_func(f"      Ollama 메모리 정리 중 ({len(extras)}개 모델 언로드)...")
        for name in extras:
            try:
                await asyncio.to_thread(
                    requests.post,
                    f"{OLLAMA_BASE_URL}/api/generate",
                    json={"model": name, "prompt": "", "keep_alive": 0},
                    timeout=15,
                )
            except Exception:
                pass
    except Exception:
        pass


async def ollama_warmup(log_func) -> None:
    """자동화 시작 전 선택 모델을 미리 올려 둔다. 실패해도 원고 생성은 계속 시도."""
    global _OLLAMA_DEGRADED
    _OLLAMA_DEGRADED = False
    if not await _ollama_ping_with_retry(log_func, attempts=2):
        log_func("      ⚠️ Ollama 서버에 연결되지 않습니다. Ollama 앱을 실행해 주세요.")
        return
    models = await _resolve_ollama_models(log_func)
    target = models[0]
    await _ollama_unload_other_models(target, log_func)
    import requests

    try:
        await asyncio.to_thread(
            requests.post,
            f"{OLLAMA_BASE_URL}/api/generate",
            json={
                "model": target,
                "prompt": "OK",
                "stream": False,
                "think": False,
                "options": {"num_predict": 4},
                "keep_alive": "15m",
            },
            timeout=(10, 90),
        )
        log_func(f"      Ollama 준비 완료 (모델: {target})")
    except Exception as e:
        log_func(
            f"      Ollama 워밍업 지연({str(e)[:60]}) — 원고 생성 시 다시 시도합니다."
        )


async def _ollama_chat_once(model: str, prompt: str, log_func, num_predict: int, read_timeout: int) -> str:
    import requests

    compact = _shrink_prompt_for_ollama(
        prompt, max_chars=8000 if num_predict <= 900 else 12000
    )
    user_tail = "\n\n반드시 한국어로 작성하고, 요청한 형식 태그를 그대로 출력해."
    log_func(
        f"      로컬 Ollama({model}) 원고 생성 중... "
        f"(최대 {read_timeout}초, 완료 후 에디터로 이동)"
    )
    stop = threading.Event()

    def _heartbeat():
        tick = 0
        while not stop.wait(20):
            tick += 1
            log_func(f"      … Ollama({model}) 응답 대기 ({tick * 20}초)")

    hb = threading.Thread(target=_heartbeat, daemon=True)
    hb.start()

    def _extract(data: dict, via: str) -> str:
        fmt_markers = ("[TITLE]", "[OUTLINE]", "[BODY]", "[TAGS]", "[IMAGE_DESC]")
        if via == "chat":
            msg = data.get("message") or {}
            content = (msg.get("content") or "").strip()
            thinking = (msg.get("thinking") or "").strip()
            if content and any(m in content for m in fmt_markers):
                text = content
            elif thinking and any(m in thinking for m in fmt_markers):
                text = thinking
            else:
                text = content or thinking
        else:
            text = (data.get("response") or "").strip()
        if not text:
            raise Exception(f"빈 응답 ({via}, done_reason={data.get('done_reason')})")
        return _trim_to_format_markers(text)

    try:
        low = model.lower()
        chat_payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": _OLLAMA_SYSTEM},
                {"role": "user", "content": compact + user_tail},
            ],
            "stream": False,
            "keep_alive": "15m",
            "options": {"num_predict": num_predict, "temperature": 0.45, "top_p": 0.9},
        }
        generate_payload = {
            "model": model,
            "prompt": f"{_OLLAMA_SYSTEM}\n\n{compact}{user_tail}",
            "stream": False,
            "keep_alive": "15m",
            "options": {"num_predict": num_predict, "temperature": 0.45, "top_p": 0.9},
        }
        attempts = []
        if "qwen3" in low or "deepseek-r1" in low:
            attempts.append(("chat", f"{OLLAMA_BASE_URL}/api/chat", chat_payload))
        attempts.append(
            ("generate", f"{OLLAMA_BASE_URL}/api/generate", generate_payload)
        )
        if "qwen3" not in low and "deepseek-r1" not in low:
            attempts.insert(0, ("chat", f"{OLLAMA_BASE_URL}/api/chat", chat_payload))

        errors = []
        for via, url, payload in attempts:
            if "qwen3" in low or "deepseek-r1" in low:
                payload["think"] = False
            try:
                ollama_res = await asyncio.to_thread(
                    requests.post, url, json=payload, timeout=(10, read_timeout)
                )
                if ollama_res.status_code != 200:
                    raise Exception(f"HTTP {ollama_res.status_code}: {ollama_res.text[:80]}")
                text = _extract(ollama_res.json(), via)
                log_func(f"      로컬 Ollama({model}/{via}) 원고 생성 완료 ({len(text)}자)")
                return text
            except Exception as e:
                errors.append(f"{via}: {str(e)[:60]}")
        raise Exception(f"{model} 실패 ({'; '.join(errors)})")
    finally:
        stop.set()


def _ollama_read_timeout_for(num_predict: int) -> int:
    """출력 길이에 맞춘 모델당 읽기 타임아웃(초)."""
    env_cap = max(240, OLLAMA_READ_TIMEOUT)
    if num_predict <= 500:
        return min(env_cap, max(300, env_cap // 2))
    if num_predict <= 1200:
        return env_cap
    return min(env_cap + 120, 720)


async def _ollama_generate_text(prompt: str, log_func, num_predict: int = 4096):
    """지정·가벼운 모델 순으로 시도. 실패 시 상위에서 템플릿 폴백."""
    models = await _resolve_ollama_models(log_func)
    per_model_timeout = _ollama_read_timeout_for(num_predict)
    max_models = 3 if num_predict <= 450 else 1
    errors = []

    for idx, model in enumerate(models[:max_models]):
        try:
            return await _ollama_chat_once(
                model, prompt, log_func, num_predict, per_model_timeout
            )
        except Exception as e:
            err = str(e)
            errors.append(f"{model}: {err[:80]}")
            if idx + 1 < min(len(models), max_models):
                log_func(f"      Ollama({model}) 실패 → {models[idx + 1]} 시도...")

    raise Exception(
        "Ollama 원고 생성 실패. "
        + (" / ".join(errors[:3]) if errors else "모델 없음")
        + " — Ollama 앱 재시작 후 gemma2:2b 등 가벼운 모델을 권장합니다."
    )


async def _try_gemini_text(keys: list, prompt: str, log_func) -> str:
    last_err = None
    quota_hit = False
    for api_key in keys:
        log_func(f"      Gemini API 호출 (키 끝자리 {_api_key_suffix(api_key)})")
        try:
            res = await _gemini_generate(api_key, prompt)
            text = _extract_gemini_text(res)
            if text:
                return text
            raise Exception("Gemini 응답이 비어 있습니다.")
        except Exception as e:
            last_err = e
            err_msg = str(e)
            if _is_quota_error(err_msg):
                quota_hit = True
                _log_quota_hint(log_func, api_key)
            else:
                log_func(f"      Gemini 오류({err_msg[:80]})")
    if quota_hit and len(keys) > 1:
        log_func("      등록된 모든 Gemini API 키에서 크레딧/쿼터 오류가 발생했습니다.")
    if last_err:
        raise last_err
    raise Exception("Gemini API 키가 없습니다.")


async def verify_gemini_api_key(api_key: str) -> tuple:
    """API 키 1회 호출 검증. (성공 여부, 메시지)"""
    key = (api_key or "").strip()
    if not key:
        return False, "API 키가 비어 있습니다."
    try:
        res = await _gemini_generate(key, "Reply with exactly: OK")
        text = _extract_gemini_text(res)
        return True, f"Gemini 연동 성공 ({_api_key_suffix(key)}) — 응답: {text[:20]}"
    except Exception as e:
        return False, str(e)


async def verify_gemini_api_keys(api_keys: list[str]) -> tuple[bool, str]:
    """여러 키를 순서대로 검증. 하나라도 성공하면 연동 OK."""
    keys: list[str] = []
    for raw in api_keys or []:
        key = (raw or "").strip()
        if key and key not in keys:
            keys.append(key)
    if not keys:
        return False, "API 키가 비어 있습니다."
    errors: list[str] = []
    for key in keys:
        ok, msg = await verify_gemini_api_key(key)
        if ok:
            return True, msg
        errors.append(f"{_api_key_suffix(key)}: {msg[:80]}")
    return False, errors[0] if len(errors) == 1 else " / ".join(errors[:2])


async def _claude_code_ping(log_func=None) -> bool:
    """Claude Code CLI 로그인·실행 가능 여부."""
    try:
        proc = await asyncio.create_subprocess_exec(
            CLAUDE_CODE_CMD,
            "-p",
            "--bare",
            "--output-format",
            "text",
            "--no-session-persistence",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            stdin=asyncio.subprocess.PIPE,
        )
        out, err = await asyncio.wait_for(
            proc.communicate(input=b"Reply with exactly: OK"),
            timeout=90,
        )
        text = (out or b"").decode("utf-8", errors="replace")
        if proc.returncode != 0:
            err_s = (err or b"").decode("utf-8", errors="replace").strip()
            if log_func and err_s:
                _safe_log(log_func, f"      Claude Code 점검: {err_s[:120]}")
            return False
        return "OK" in text
    except FileNotFoundError:
        if log_func:
            _safe_log(log_func, f"      Claude Code CLI({CLAUDE_CODE_CMD})를 찾을 수 없습니다.")
        return False
    except Exception as e:
        if log_func:
            _safe_log(log_func, f"      Claude Code 점검 실패: {str(e)[:100]}")
        return False


async def verify_claude_code(log_func=None):
    """Claude Code CLI 연동 확인. 반환: (성공 여부, 메시지)."""
    if await _claude_code_ping(log_func):
        return True, "Claude Code 연동 확인됨"
    return (
        False,
        "Claude Code CLI에 로그인되지 않았거나 실행할 수 없습니다. "
        "터미널에서 claude 실행 후 /login 하세요.",
    )


async def _claude_code_generate_text(prompt: str, log_func, system_prompt: str = None) -> str:
    """Claude Code CLI(-p)로 원고 생성. 마스터 지침은 system prompt로 전달."""
    cmd = [
        CLAUDE_CODE_CMD,
        "-p",
        "--bare",
        "--output-format",
        "text",
        "--no-session-persistence",
    ]
    if CLAUDE_CODE_MODEL:
        cmd.extend(["--model", CLAUDE_CODE_MODEL])
    sys_p = (system_prompt or _OLLAMA_SYSTEM).strip()
    if len(sys_p) > 12000:
        sys_p = sys_p[:12000] + "\n…(지침 일부 생략)"
    cmd.extend(["--system-prompt", sys_p])

    _safe_log(log_func, "      Claude Code 원고 생성 중...")
    base_dir = os.path.dirname(os.path.abspath(__file__))
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        stdin=asyncio.subprocess.PIPE,
        cwd=base_dir,
    )
    try:
        out, err = await asyncio.wait_for(
            proc.communicate(input=prompt.encode("utf-8")),
            timeout=CLAUDE_CODE_TIMEOUT,
        )
    except asyncio.TimeoutError:
        try:
            proc.kill()
        except Exception:
            pass
        raise Exception(f"Claude Code 응답 시간 초과({CLAUDE_CODE_TIMEOUT}초)")

    text = (out or b"").decode("utf-8", errors="replace").strip()
    err_s = (err or b"").decode("utf-8", errors="replace").strip()
    if proc.returncode != 0:
        hint = err_s or text[:200]
        if "login" in hint.lower() or "not logged in" in hint.lower():
            raise Exception("Claude Code 미로그인 — 터미널에서 claude 실행 후 /login 하세요.")
        raise Exception(f"Claude Code 실패: {hint[:240]}")
    if not text:
        raise Exception("Claude Code 빈 응답")
    return _trim_to_format_markers(text)


async def _generate_text_with_fallback(api_key_or_config, prompt: str, log_func, num_predict: int = 4096):
    """text_provider에 따라 Claude / Gemini / Ollama. 반환: 생성 텍스트(str)."""
    provider = _normalize_text_provider(api_key_or_config)
    keys = _collect_text_api_keys(api_key_or_config)

    async def _ollama_or_raise():
        if not await _ollama_ping_with_retry(log_func, attempts=3):
            raise Exception("Ollama 서버에 연결할 수 없습니다. Ollama 앱을 실행한 뒤 다시 시도해 주세요.")
        return await _ollama_generate_text(prompt, log_func, num_predict=num_predict)

    if provider == "claude":
        try:
            return await _claude_code_generate_text(prompt, log_func)
        except Exception as claude_err:
            if not _api_sparing_enabled() and keys:
                _safe_log(log_func, f"      Claude Code 실패({str(claude_err)[:80]}), Gemini로 대체...")
                return await _try_gemini_text(keys, prompt, log_func)
            if await _ollama_ping():
                _safe_log(log_func, f"      Claude Code 실패({str(claude_err)[:80]}), Ollama로 대체...")
                return await _ollama_or_raise()
            raise

    if provider == "ollama":
        try:
            return await _ollama_or_raise()
        except Exception as ollama_err:
            if not _api_sparing_enabled() and keys:
                log_func(f"      Ollama 실패({str(ollama_err)[:80]}), Gemini로 대체...")
                return await _try_gemini_text(keys, prompt, log_func)
            raise

    if provider == "auto":
        if await _ollama_ping():
            try:
                return await _ollama_or_raise()
            except Exception as ollama_err:
                if _api_sparing_enabled():
                    raise
                log_func(f"      Ollama 실패({str(ollama_err)[:80]}), Gemini 시도...")
        elif _api_sparing_enabled():
            raise Exception("Ollama 서버에 연결할 수 없습니다. Ollama 앱을 실행한 뒤 다시 시도해 주세요.")
        elif keys:
            log_func("      Ollama 미실행 — Gemini API 사용")

    if keys and not _api_sparing_enabled():
        try:
            return await _try_gemini_text(keys, prompt, log_func)
        except Exception as gemini_err:
            if provider == "gemini" and await _ollama_ping():
                log_func(f"      Gemini 실패({str(gemini_err)[:80]}), Ollama로 우회...")
                return await _ollama_or_raise()
            raise

    if await _ollama_ping():
        return await _ollama_or_raise()
    raise Exception("Gemini API 키가 없고 Ollama도 사용할 수 없습니다.")


# POST_TYPES, PRODUCT_* → blog_constants (GUI·라우터 경량 import)
_PRESERVE_POST_TYPES = ("맛집/일상", "취미글", "알림글")
_LIVING_KW_MARKERS = ("리빙", "욕실", "타일", "싱크", "주방", "가구", "수전", "곰팡이", "거실", "인덕션", "가스레인지", "전자레인지", "식탁")
_AUTO_KW_MARKERS = ("자동차", "차량", "Permacoat", "퀵", "티탄", "레진", "보닛", "유리막", "발수")
_BIKE_KW_MARKERS = ("바이크", "오토바이", "머플러", "배기", "bike", "할리", "두카티", "라이더")


def _keyword_matches_product(keyword: str, choice: str) -> bool:
    kw = (keyword or "").strip()
    if not kw:
        return False
    if choice == "living":
        return any(m in kw for m in _LIVING_KW_MARKERS)
    if choice == "auto":
        return any(m in kw for m in _AUTO_KW_MARKERS) and not any(m in kw for m in _LIVING_KW_MARKERS)
    if choice == "bike":
        return any(m in kw for m in _BIKE_KW_MARKERS) and not any(m in kw for m in _LIVING_KW_MARKERS)
    return False


def apply_product_choice(config: dict) -> dict:
    """홍보 상품 선택을 글 유형·키워드에 반영. config dict를 그대로 수정해 반환."""
    choice = (config.get("product_choice") or "none").strip().lower()
    if choice not in PRODUCT_POST_TYPE:
        return config

    raw_post = (config.get("post_type") or "자동(매번 랜덤)").strip()
    # 사용자가 GUI에서 수동으로 선택한 글 유형(제품 홍보, 취미글 등)은 보존하고, "자동(매번 랜덤)"이거나 비어있을 때만 기본값 부여
    if raw_post == "자동(매번 랜덤)" or not raw_post:
        config["post_type"] = PRODUCT_POST_TYPE[choice]

    default_kws = PRODUCT_KEYWORDS.get(choice, [])
    raw_kw = config.get("keywords") or []
    if isinstance(raw_kw, str):
        existing = [k.strip() for k in raw_kw.split(",") if k.strip()]
    else:
        existing = [str(k).strip() for k in raw_kw if str(k).strip()]
    matched = [k for k in existing if _keyword_matches_product(k, choice)]
    config["keywords"] = matched if matched else default_kws
    return config


DEFAULT_MASTER_GUIDELINES = """
[콘텐츠 구성 비율 — 7:2:1 법칙]
모든 글이 제품 홍보일 필요는 없습니다. 독자가 정보를 얻으러 왔다가 "이 집 잘하네"라고 느끼게 만드는 비율을 지킵니다.
- 70% (정보·정보성 일상): 자동차/바이크 관리 꿀팁, 관련 업계 뉴스, 지역 맛집, 일상 이슈.
- 20% (전문 지식): 코팅의 원리, 가죽 관리법, 셀프 시공 시 주의사항. 제품 언급은 최소화.
- 10% (제품 홍보): 신제품 출시, 실제 시공 후기, 이벤트 안내.

[판매가 아닌 해결 중심 글쓰기]
글의 목적은 "이걸 사세요"가 아니라 "당신의 고민을 해결해 드릴게요"입니다.
- 제목: "듀라코트 최고 성능 판매 중" (X) → "주방 상판 얼룩, 락스 없이 지우는 3가지 방법" (O)
- 도입: "저희 제품은 이런 성분이 들어있어 좋습니다" (X) → "최근 비가 자주 와서 바이크 체인 녹 걱정되시죠?" (O)
- 전개: 제품 스펙·가격 나열 (X) → 관리 안 했을 때 문제점 제시 + 관리 팁 공유 (O)
- 결론: "지금 바로 구매하세요" (X) → "직접 하기 힘들다면 이런 성분의 코팅제를 찾아보세요" (O)

[세부 카테고리별 작성 가이드]
① 자동차/바이크 뉴스·이슈: 뉴스를 퍼오지 말고, 대표님의 한 줄 의견을 덧붙인다. 예) "이번에 나온 모델, 도장면이 특이하네요. 이런 차는 일반 왁스보다 OO 방식이 관리하기 편할 것 같습니다."
② 맛집·일상: "공장 근처 맛집", "영업 미팅 갔다가 발견한 곳"처럼 나눔랩의 활동 반경을 자연스럽게 노출해 "진짜 열심히 일하고 발로 뛰는 사람이구나"라는 신뢰를 준다.
③ 정보성 팁 (가장 중요): 제품을 전혀 언급하지 않고도 전문성을 보이는 영역. 예) "천연 가죽 시트, 물티슈로 닦으면 안 되는 이유", "장마철 바이크 야외 보관 시 필수 체크리스트".

[말투와 표현 지침]
- 전문 용어보다 쉬운 말: "폴리실라잔 함유량"보다 "유리막이 얼마나 단단하게 형성되는지"처럼 풀어서 설명한다.
- '나'의 이야기: 주제와 직접 관련된 현장 경험 1~2문장만. "바이크를 오랫동안 타다 보면…" 같은 장문 감성 독백·카페·집 풍경 묘사는 금지.
- 솔직함: 장점만 늘어놓지 말고, "이런 분들에게는 굳이 필요 없습니다"라고 말할 때 독자 신뢰가 커진다.

[콘텐츠 테마 구조]

1. 뉴스/이슈 테마 (정보 유입용)
- 자동차·바이크 신차 뉴스는 단순 출시 소식이 아니라, 디자인/스펙에 대한 내 개인 의견을 1~2문장씩 곁들인다.
- 교통법규·정책 변경(과태료, 전용도로 등)은 운전자/라이더가 꼭 알아야 할 핵심만 정리한다.
- 업계 이슈(전기차 화재, 급발진 등)는 공포감을 자극하기보다 사실과 대응 방법 위주로 정리한다.

2. 유지관리·꿀팁 테마 (신뢰 구축용)
- 계절별 관리법: 여름(고온), 겨울(염화칼슘) 등 계절별로 도장면·부품이 받는 스트레스를 설명하고 관리법을 제시한다.
- 부위별 셀프 케어: 한 포스팅당 한 부위(타이어, 휠, 가죽 시트 등)만 다뤄서 매우 구체적인 팁을 준다.
- 증상별 해결책: 워터스팟, 체인 소음 등 실제로 자주 겪는 문제를 사례+해결 순서로 정리한다.

3. 과학적 성능·원리 테마 (전문성 노출용)
- 성분 이야기: 폴리실라잔, 실리카 같은 용어를 "왜 비가 올 때 물방울이 튕기는지" 등 생활 상황과 연결해 쉽게 설명한다.
- 지속성 실험: 직접 시공 후 1주·1개월 등 시간 간격을 두고 상태를 비교해, 좋은 제품을 써야 하는 이유를 보여준다.
- 타사 방식 비교: 특정 브랜드를 저격하지 않고, 일반 왁스 vs 유리막 코팅제처럼 원리·내구성 차이를 설명한다.

4. 라이프스타일·맛집 테마 (친근감 형성용)
- 드라이브/투어 코스: 주말에 다녀오기 좋은 실제 코스를 지도·사진과 함께 소개한다.
- 카공/맛집: 음식보다 "주차 편의성, 라이더 모이기 좋은 곳" 같은 포인트를 강조한다.
- 차량용품·액세서리 리뷰: 거치대, 세차용품 등 가볍게 리뷰하되, 실제 사용 느낌 위주로 솔직하게 적는다.

5. 작업 비하인드·스토리 테마 (간접 홍보용)
- 실패 사례: 어설픈 작업으로 망가진 사례와 복구 과정을 보여주고, 어떤 점을 조심해야 하는지 알려준다.
- 제품 개발 일기: 코팅제 테스트 과정에서 나온 의외의 결과나 시행착오를 이야기처럼 풀어낸다.
- 고객과의 대화: 실제 상담에서 많이 나오는 질문을 Q&A 형식으로 정리한다.

[반복 방지 및 톤 지침]

- 같은 주제라도 타겟을 바꿔 쓴다: 초보 운전자용 / 바이크 매니아용 / 장거리 출퇴근러용 등으로 나눠서 쓴다.
- 질문으로 시작한다: "유리막 코팅, 꼭 해야 할까요?" 같은 질문으로 시작해 독자의 궁금증을 먼저 건드린다.
- 사진은 현장 중심: 제품 누끼컷보다 작업 중인 손, 빗방울 맺힌 모습, 주차장 전경 등 현장 사진을 다양하게 사용한다.
- 상업적 멘트는 최소화: "지금 사세요"보다 "이런 상황이라면 이런 선택이 더 좋다" 식의 안내·추천 톤을 유지한다.

[글 유형별 제품 매핑 규칙 — 절대 준수, 데이터 꼬임·거짓 방지]
드롭다운 선택값에 따라 아래 데이터만 호출한다. 엉뚱한 소리(예: 자동차 유형인데 수전·싱크대 코팅) 금지.
| 글 유형 | 사용 가능 제품·정보 | 금지 (Strictly Prohibited) |
| 자동차 정보 / 바이크 정보 / 코팅제 정보 | 퀵(14%), 티탄(28% 원액), 레진(28% 원액 60%+레진 30%), 전용 건식 관리제 | 리빙코트 언급 금지. 세면대·싱크대·욕실·가구 등 생활용 맥락 언급 금지 |
| 제품 홍보 (Living 중심) | 듀라코트 리빙코트 (주방, 욕실, 가구 등 생활 오염 방지) | 자동차/바이크 코팅제 스펙(퀵·티탄·레진 %) 언급 금지 |
| 맛집/일상 / 취미글 | 낚시(힐링), 전국 맛집, 할리/인디언/두카티 바이크 투어, 외제 신차 시승기 | 노골적인 제품 판매 유도 금지 |
| 정보성 팁 | 10년 경력 광택/유리막 시공 노하우, 아토피 안심 천연 비누 제작 팁 | 근거 없는 수치 제시 금지 |
| NAEO·AI 트렌드 | NAEO, SEO·AEO·GEO, 네이버 AI·블로그 유입·검색 변화 (고정 6단 개요) | 코팅제·듀라코트·스마트스토어 판매 유도 금지 |

[절대 불변의 제품 데이터 — Truth Table]
거짓 정보 방지. 텍스트 생성 시 아래 수치만 고정 사용.
- Quick (퀵): 폴리실라잔 14% 함유.
- Titan (티탄): 티탄 + 폴리실라잔 28% 원액 함유.
- Resin (레진): 폴리실라잔 28% 원액 60% + 레진 30% (최상위 전문가 라인).
- 관리제 구분: 자동차/바이크용은 '전용 건식 관리제'. '리빙코트'와는 완전히 다른 별개 제품임.

[비교 로직 — External Only]
- 비교 대상: 항상 '타사 제품' 또는 '기존의 잘못된 관리 방식'과만 비교한다.
- 자사 제품 간 비교 절대 금지: 듀라코트 리빙코트와 자동차용 듀라코트 코팅제를 비교하는 맥락은 절대 생성하지 않는다.

[10년 경력 전문가 페르소나]
- 문체: 10년 현장 실무자의 단단하고 신뢰감 있는 어조.
- 전문성 입증: "10년간 아토피 트러블 0건의 비누 제조 철학을 코팅제 제조에도 그대로 적용했다"는 점을 강조.
- 작성자 별명이나 아이디를 제품·브랜드명처럼 쓰지 않는다. 예를 들어, 별명을 붙여 "○○ 발수코팅제"처럼 쓰지 말고, 제품명은 듀라코트, 퍼마코트, 리빙코트, 퀵, 티탄, 레진만 사용한다.

[글쓰기 흐름 (맥락)]
- 자동차/바이크 포스팅: 유리막 코팅(퀵/티탄/레진) 성능·전용 건식 관리제만. 리빙코트·생활용(수전·싱크대·가구) 언급 금지.
- 제품 홍보(Living): 리빙코트(주방·욕실·가구)만. 퀵·티탄·레진 스펙 언급 금지.

[영국 수출 실적 — 글에 강조]
- 나눔랩 제품은 영국으로 수출된 실적이 있다. 듀라코트·퍼마코트, 퀵·티탄·레진(자동차/바이크용), 바이크 레진, 듀라코트 리빙코팅제 모두 영국 수출이 이루어졌다. 맥락에 맞을 때 '영국 수출', '해외(영국) 수출', '글로벌 품질 인정' 등을 자연스럽게 한두 문장으로 강조하여 신뢰도를 높인다.

[글 유형별 내용 범위 — 위 매핑 규칙과 동일]
- 자동차/바이크/코팅제 정보: 퀵·티탄·레진·전용 건식 관리제만. 리빙코트·세면대·싱크대·수전·욕실·가구 언급 금지.
- 제품 홍보: 듀라코트 리빙코트(Living)만. 자동차/바이크 코팅제 스펙(퀵·티탄·레진 %) 언급 금지.
- 맛집/일상·취미글: 낚시·맛집·바이크 투어·신차 시승기 등. 노골적 제품 판매 유도 금지.
- 정보성 팁: 10년 경력 노하우·비누 팁 등. 근거 없는 수치 금지.
- NAEO·AI 트렌드: SEO·AEO·GEO·네이버 AI·블로그 유입. 영상 챕터 6단 고정 개요. 코팅·판매 멘트 금지.
- 알림글: 공지·이벤트·안내만.

[글 유형 우선순위 — 키워드 처리]
- 맛집/일상·취미글 선택 시: 입력된 '포스팅 키워드'를 100% 무시. 낚시·맛집·바이크 투어 등 일상·취미 데이터만 사용. 제품 키워드 사용 금지(거짓 정보 방지).
- 자동차/바이크/코팅제 정보: 퀵·티탄·레진·전용 건식 관리제만. 리빙코트·수전·싱크대 등 생활용 키워드 금지.
- 제품 홍보: 리빙코트(주방·욕실·가구)만. 퀵·티탄·레진 스펙 키워드 금지.

[네이버 AI 브리핑·메이트 5원칙 — 공식 가이드 정렬]
- 직접 경험: AI 초안 위에 시공·실패·현장 일화·구체 수치를 반드시 녹인다. 프롬프트만 던져 나온 일반론 금지.
- 일관된 주제: 채널 핵심 주제(코팅·리빙·라이프)에 맞는 글만. 글 유형별 제품 매핑 규칙 준수.
- 거짓 없는 진정성: 협찬·내돈내산·체험 관계를 본문 상단에 표기. Truth Table 외 수치·허위 스펙 금지.
- 읽기 쉬운 구조: ## 소제목, 짧은 문단, 표 1개 이상(해당 시), 이미지 핵심은 텍스트로도 서술.
- 최신성: 구체적 시점·상황(최근 시공, 이번 계절 등)을 명시한다.

[금지어]
- AI스러운 상투적 도입부·광고 멘트 절대 금지: "안녕하세요", "알아보겠습니다", "도움이 되었으면 합니다", "짜증 나시죠?" 등 사용하지 않는다.
""".strip()

# 채널별 톤 (매 요청 시 랜덤 2개 조합)
CHANNEL_STYLES = [
    "Style A (hymini1): 10년 경력 제조 이사의 신뢰감 있는 톤 (~입니다).",
    "Style B (hymini11): 라이더 시선의 실용 팁 톤 (~해요). 감성 에세이·철학 독백 금지.",
    "Style C (티스토리): 수치(14%, 28%, 60%) 기반 기술 분석 톤 (~다).",
    "Style D (Blogger): 핵심 요약 중심의 미니멀 톤.",
]


# 매번 다른 구체적 글쓰기 앵글 (형식 단조로움 방지)
_VIVID_ANGLES = [
    "10년 넘게 광택기를 잡아온 손끝 감각을 살려, 시공 시 버핑 타이밍·표면 준비 포인트를 구체적으로 써줘.",
    "10년 경력자만 아는 디테일(약재 반응, 버핑 타이밍, 광택기 운용 시 감각)을 자연스럽게 녹여서 써줘.",
    "현장에서 자주 받는 질문 1개로 도입하고, 체크리스트·표로 답을 정리해줘.",
    "장마철 바이크 야외 보관 시 체크리스트를 구체적으로 써줘.",
    "천연 비누·향수 베이스 10년 관점에서 안전성과 품질 기준을 글에 녹여줘.",
    "Before/After 수치·관찰 포인트를 표로 정리해줘.",
    "듀라코트·퍼마코트, 퀵·티탄·레진·바이크 레진·리빙코팅제가 영국에 수출된 실적을 맥락에 맞게 한두 문장으로 자연스럽게 강조해줘.",
]


def _contains_fact_violation(text: str) -> bool:
    """치명적 사실 오류 패턴(현재는 그래핀 코팅 작용 오표현 중심) 탐지."""
    if not text:
        return False
    lowered = text.lower()
    # 그래핀은 첨가/보강 맥락은 가능하나, 단독 코팅 작용 주체로 단정하면 오류로 간주
    bad_patterns = [
        r"그래핀.{0,12}(이|은)?.{0,12}(코팅\s*작용|코팅을\s*한다|피막\s*형성)",
        r"그래핀.{0,12}(이|은)?.{0,12}(주성분|핵심\s*코팅\s*성분|코팅제\s*성분)",
        r"그래핀\s*코팅제.{0,12}(핵심|주요)\s*성분",
    ]
    return any(re.search(p, lowered) for p in bad_patterns)


def _contains_banned_phrases(text: str) -> bool:
    if not text:
        return False
    return any(p in text for p in _BANNED_BLOG_PHRASES)


def _contains_narrative_cliches(text: str) -> bool:
    if not text:
        return False
    return any(re.search(p, text) for p in _NARRATIVE_ESSAY_PATTERNS)


def _scrub_cross_topic_content(body: str, post_type: str) -> str:
    """바이크/자동차 글에 끼어든 리빙·에세이 문단·소제목 제거."""
    pt = (post_type or "").strip()
    if pt not in ("자동차 정보", "바이크 정보", "코팅제 정보"):
        return body
    text = (body or "").strip()
    if not text:
        return text
    section_markers = (
        "리빙", "우리 집", "주방", "욕실", "가구", "싱크", "타일", "원목", "샤워부스",
        "숨겨진 공간", "오래도록 새것처럼", "일상 공간", "리빙 코팅",
    )
    para_markers = section_markers + (
        "카페에서 나와", "집으로 향하는", "지키는 취미", "온몸으로 느낄", "이 지킴이 결국",
        "연장선상에는", "미세한 진동", "노면의 작은 충격",
    )
    sections = re.split(r"(?=^##\s+)", text, flags=re.M)
    kept: list[str] = []
    for sec in sections:
        sec = sec.strip()
        if not sec:
            continue
        if sec.startswith("##"):
            header = sec.split("\n", 1)[0]
            if any(m in header for m in section_markers):
                continue
            if "\n" in sec:
                head, rest = sec.split("\n", 1)
                paras = [p.strip() for p in re.split(r"\n\s*\n", rest) if p.strip()]
                paras = [
                    p for p in paras
                    if p == "[IMAGE]" or not any(m in p for m in para_markers)
                ]
                if paras:
                    kept.append(head + "\n\n" + "\n\n".join(paras))
            else:
                kept.append(sec)
        else:
            paras = [p.strip() for p in re.split(r"\n\s*\n", sec) if p.strip()]
            paras = [
                p for p in paras
                if p == "[IMAGE]" or not any(m in p for m in para_markers)
            ]
            if paras:
                kept.append("\n\n".join(paras))
    return "\n\n".join(kept).strip() or text


def _violates_post_type_scope(body: str, post_type: str) -> str | None:
    """글 유형과 본문 주제 불일치 시 재생성 사유."""
    if not body:
        return "빈 본문"
    pt = (post_type or "").strip()
    living = (
        "리빙코트", "리빙 코팅", "싱크대", "수전", "욕실 타일", "주방 상판", "가구 코팅", "샤워부스",
        "원목 가구", "주방 싱크", "우리 집", "오래도록 새것처럼", "숨겨진 공간", "일상 공간",
    )
    auto_specs = ("퀵 14", "14% 함유", "티탄 28", "28% 원액", "레진 60", "전용 건식 관리제")
    if pt in ("자동차 정보", "바이크 정보", "코팅제 정보"):
        for term in living:
            if term in body:
                return f"자동차/바이크 글에 생활용 '{term}' 포함"
        if _contains_narrative_cliches(body):
            return "감성 에세이·주제 이탈 서사 포함"
    elif pt == "제품 홍보":
        for term in auto_specs:
            if term in body:
                return f"리빙 홍보 글에 자동차 스펙 '{term}' 포함"
    elif pt in ("맛집/일상", "취미글"):
        promo = ("듀라코트 리빙", "퀵 코팅", "티탄 코팅", "레진 코팅", "지금 구매", "스마트스토어")
        for term in promo:
            if term in body:
                return f"맛집/취미 글에 제품 홍보 '{term}' 포함"
    elif is_naeo_post_type(pt):
        coating = ("듀라코트", "퍼마코트", "리빙코트", "퀵 코팅", "티탄 코팅", "레진 코팅", "유리막 코팅", "스마트스토어")
        for term in coating:
            if term in body:
                return f"NAEO 글에 코팅·판매 '{term}' 포함"
    return None


def _default_guidelines():
    return (
        "0. 글 유형 준수: 선택한 글 유형에 맞는 내용만 쓴다. 맛집이면 맛집 글(음식·맛집·방문 후기), 취미면 취미 글(낚시·드라이브·일상 취미)—제품(듀라코트 리빙코트)을 주제로 한 글이 아니다. 유형과 다른 주제를 본문 중심으로 쓰지 않는다.\n"
        "1. 페르소나: '자동차 코팅제, 바이크 코팅제, 리빙코팅제를 개발하고 있는 제조 이사입니다'라는 10년 경력 실무자의 시선으로 작성한다. 나눔랩 개발자라고 쓰지 말고, 자동차 코팅제·바이크 코팅제·리빙코팅제를 개발하는 제조 이사라고만 소개한다. "
        "필자는 나눔랩 제조 이사이며, (1) 10년 이상 자동차 광택·유리막 코팅 현장 경력, (2) 10년 경력 향수 베이스·천연 비누 제작(아토피 환우 10년 무사고), "
        "(3) 현대·기아 제외 글로벌 신차·할리/인디언/두카티 바이크·전국 맛집·낚시 등 라이프스타일을 가진 실무형 전문가이다. "
        "직접 테스트하고 현장에서 고객을 만나 본 경험을 전제로, '직접 써보니', '실제 시공해 보니'와 같은 표현을 자주 사용한다.\n"
        "1-2. 기술적 디테일: 코팅·광택 관련 글일 때 10년 경력자만 알 수 있는 디테일(약재 반응, 버핑 타이밍, 광택기 운용 감각 등)을 자연스럽게 녹여낸다. "
        "신뢰성 강조: '10년 동안 아토피 문제 한 건 없었다', '10년 넘게 직접 차 닦고 코팅해왔다'는 사실을 근거로 독자에게 강한 신뢰감을 준다.\n"
        "2. 말투: 친절하고 신뢰감 있는 구어체를 사용하며, 전문 용어는 쉽게 풀어서 설명한다. "
        "너무 딱딱한 비즈니스 문체, '사료됨', '함에 있어서'와 같은 표현은 사용하지 않는다.\n"
        "3. 네이버 블로그 관점: 브랜드 신뢰를 쌓은 뒤 자연스럽게 구매를 고민하게 한다. "
        "본문은 고객 사례·시공 과정·관리 팁 중심(7:2:1). 결론 1문단에만 스마트스토어 참고·댓글 질문을 넣는다. '지금 구매'류 문구 금지.\n"
        "4. 티스토리·구글 관점: 정보성과 전문성을 높여 구글 SEO와 애드센스를 고려한다. "
        "H2, H3 소제목을 활용해 정보의 위계를 분명히 나누고, 최소 1,500자 이상 분량으로 원리 설명(코팅의 과학, 성분 비교, 내구성 등)을 포함한다.\n"
        "5. 본문은 항상 3단계 구조를 따른다. "
        "[1] 공감(Hook): 독자가 겪는 불편을 구체적인 상황으로 풀어낸다. 예시는 주제에 맞게 골라 쓴다(물때·변색·기름때·스크래치 등). 욕실 주제가 아닐 때는 곰팡이를 반드시 넣지 말고, 욕실 글일 때만 필요 시 한두 번 선택적으로 언급한다. "
        "[2] 해결책(Solution): 코팅의 원리와 '좋은 코팅제 고르는 법'(성분, 함량, 피막 형성 등 제조사 관점)을 설명한다. "
        "[3] 입증(Proof): 발수력 테스트, 내구성, 실제 시공 사진/후기, 제조 공정 디테일(예: 폴리실라잔 함량)을 근거로 신뢰를 준다.\n"
        "6. 메인 키워드는 제목의 앞부분과 첫 문단에 반드시 포함한다. "
        "문단은 3~4줄 이내로 짧게 나누고, 중요한 문장은 문맥과 표현으로 자연스럽게 강조한다. "
        "마크다운 기호(#, **, _, ``` 등)는 사용하지 않고, 일반 문장과 띄어쓰기만 사용한다.\n"
        "7. 제품·맥락 구분: 퀵(14%), 티탄(28%), 레진(60%+30%), 전용 건식 관리제(자동차/바이크 유리막 후 관리), 리빙코트(가정·범용)를 엄격히 구분한다. 자동차/바이크 글에서는 '전용 건식 관리제'만 언급하고 리빙코트는 꺼내지 않는다. 비교는 내부(듀라코트 vs 리빙코트) 금지; 리빙코트 글→타사 관리제·불편한 청소 방식, 코팅/건식 글→일반 왁스·저가형 타사 코팅제와만 비교한다. "
        "8. 제품 비교, 성분 특징, 효과 차이는 '반드시' 표로 정리해 스크롤 정지 구간을 만든다. "
        "표는 항상 깔끔한 마크다운 표 형식으로 작성하며, 행/열 구조를 자동 글쓰기 표 템플릿에 맞춘다. "
        "각 행은 한 줄에만 작성하고, 각 셀은 ' | ' 문자로 구분하며, 셀 안에서는 줄바꿈(엔터)을 절대 넣지 않는다. "
        "듀라코트와 리빙코트를 함께 다루는 글에서는 다음 예시처럼만 작성한다. "
        "'| 구분 | 듀라코트 | 리빙코트 |\\n"
        "| --- | --- | --- |\\n"
        "| 주 용도 | 싱크대, 타일 등 강력 보호 | 싱크대, 타일, 욕실 등 유지 관리 |\\n"
        "| 주요 성분 | 폴리실라잔, 고급 코팅 성분 | 발수·오염 방지 코팅 성분 |\\n"
        "| 내구성 | 매우 높음 (장기간 유지) | 보통 (주기적 사용 권장) |\\n"
        "| 시공 난이도 | 셀프 시공 가능, 꼼꼼한 준비 필요 | 비교적 쉬운 셀프 시공 |\\n"
        "| 사용 주기 | 1회 시공 후 장기간 유지 | 주기적인 보완 코팅 권장 |\\n"
        "| 광택 | 깊고 선명한 고광택 | 은은하고 자연스러운 광택 |' "
        "이 형식을 벗어나는 애매한 텍스트 표나 잘려 보이는 표는 절대 사용하지 않는다. "
        "이미지에는 주제와 일치하는 대체 텍스트(Alt Text)에 가까운 설명형 문장을 함께 적는다고 가정하고, 본문에서 이미지의 의미를 한두 줄로 짚어준다.\n"
        "9. 제목은 숫자나 호기심을 자극하는 문구를 활용한다. 예) '전문가가 알려주는 ~법', '실패 없는 ~비결 3가지', '~ 전 꼭 체크할 것'.\n"
        "10. 본문에는 H2 소제목을 최소 3개 이상 두고, 필요시 H3 소제목으로 세부 내용을 나눈다. "
        "각 소제목 아래에는 충분한 설명과 예시를 넣어 정보 밀도를 유지한다.\n"
        "11. '듀라코트', '퍼마코트' 등 나눔랩 관련 브랜드명을 맥락에 맞게 자연스럽게 포함하되, 과도한 반복 광고처럼 보이지 않도록 한다. 작성자 별명이나 아이디를 제품명처럼 붙여 쓰지 않는다(예: 별명 발수코팅제 X, 듀라코트 리빙코트 O). 퀵·티탄·레진·바이크 레진·듀라코트 리빙코팅제의 영국 수출 실적을 맥락에 맞으면 한두 문장으로 강조해 신뢰도를 높인다.\n"
        "12. 글의 끝부분은 독자가 댓글로 질문하거나 경험을 공유하고 싶어지도록 질문형으로 마무리한다.\n"
        "13. 키워드와 내용을 전개할 때, 다음 4가지 테마 중 어떤 상황에 가까운지 인지하고 서술을 구성한다. "
        "[주방 관리: 싱크대, 인덕션, 가스레인지, 기름때·물때·변색] "
        "[욕실 관리: 타일, 수전, 유리, 샤워부스, 물때·변색] (곰팡이는 욕실 글에서만 필요할 때만 최소한으로) "
        "[프리미엄 가구: 원목 식탁, 거실장, 고급 가구, 색감 복원·피막 보호] "
        "[탈것: 자동차/바이크, 유리막 코팅, 광택 유지, 발수 복원].\n"
        "14. 출력 형식은 [TITLE] 제목, [BODY] 본문, [TAGS] 태그(해시태그 위주) 구조를 따른다. "
        "[BODY] 안에서는 H2/H3 형식의 소제목을 명확히 드러내도록 줄바꿈과 마크업을 활용한다.\n"
        "15. 본문에서는 필요시 [IMAGE] 태그를 사용해 이미지가 들어갈 구간을 표시하되, 이미지의 의미와 시각적 포인트를 간단히 설명하는 문장을 함께 넣는다.\n"
        "16. 취소선(~~, <s>)은 사용하지 않으며, 굵게/기울임 같은 마크다운 형식은 사용하지 않는다. "
        "가능하면 사람이 일상적으로 쓰는 자연스러운 문장 구조로 정리하고, AI가 쓴 것처럼 보이는 안내 문구나 메타 발언은 넣지 않는다.\n"
        "17. 사실 정확성 규칙(최우선): 근거 없는 단정 금지. 확인되지 않은 정보는 쓰지 않는다. 모호하면 일반론으로 낮춰 표현하거나 해당 문장을 삭제한다.\n"
        "18. 그래핀 관련 엄수: 그래핀은 보강/첨가 맥락으로만 제한적으로 설명한다. '그래핀이 코팅 작용을 한다', '그래핀이 피막을 형성한다', "
        "'그래핀이 코팅의 핵심 주성분이다' 같은 표현은 금지한다. 코팅 작용의 주체를 그래핀으로 단정하지 않는다.\n"
    )


def _get_keyword_and_scope_instructions(config, required_keyword, extra_keyword):
    """글 유형·키워드에 따른 keyword_instruction, scope_instruction, type_instruction, prompt_lead 반환. outline/body 공통."""
    if extra_keyword is None:
        extra_keyword = required_keyword
    apply_product_choice(config)
    post_type = (config.get("post_type") or "").strip() or "자동(매번 랜덤)"
    if post_type in ("맛집/일상", "취미글"):
        keyword_instruction = (
            "【키워드 100% 무시】 맛집·취미 에세이만. 제품·코팅 키워드 사용 금지."
        )
        scope_instruction = ""
        type_instruction = "맛집/취미 에세이에 맞는 제목·개요만 제시."
        prompt_lead = "맛집 또는 취미 에세이용 블로그 포스팅의 제목과 개요를 정해줘."
    elif post_type in ("자동차 정보", "바이크 정보", "코팅제 정보"):
        keyword_instruction = f"퀵·티탄·레진·전용 건식 관리제만. 리빙코트·욕실·가구 금지. 주제: '{required_keyword}'"
        scope_instruction = (
            "자동차/바이크/코팅제 정보만. 생활용(욕실·싱크대·가구·우리 집·리빙 코팅) 한 줄도 금지. "
            "감성 에세이·철학 독백·카페·집 풍경 묘사 금지.\n"
        )
        type_instruction = f"글 유형 [{post_type}]에 맞는 제목·개요만."
        prompt_lead = f"{keyword_instruction}을 반영해 블로그 포스팅의 제목과 개요를 정해줘."
    elif post_type == "제품 홍보":
        keyword_instruction = "듀라코트 리빙코트(주방·욕실·가구)만. 자동차/바이크 코팅 스펙 금지."
        scope_instruction = "제품 홍보(Living)만. 맛집·취미·자동차/바이크 스펙 금지.\n"
        type_instruction = "제품 홍보에 맞는 제목·개요만."
        prompt_lead = f"{keyword_instruction}을 반영해 블로그 포스팅의 제목과 개요를 정해줘."
    elif is_naeo_post_type(post_type):
        kw = (required_keyword or default_keyword()).strip() or default_keyword()
        keyword_instruction = f"NAEO·블로그·AI 검색 주제: '{kw}' (코팅·제품 키워드 무시)"
        scope_instruction = (
            "【범위】 NAEO·SEO·AEO·GEO·네이버 AI·블로그 유입만. "
            "코팅제·듀라코트·스마트스토어 판매 금지.\n"
            + outline_for_prompt()
            + "\n"
        )
        type_instruction = "위 고정 H2 순서·제목을 유지한 개요만. 제목은 NAEO·블로그 유입 관련."
        prompt_lead = "NAEO·블로그 AI 시대 트렌드 글의 제목과 개요를 정해줘."
    else:
        keyword_instruction = f"필수 주제: '{required_keyword}'" + (f", 추가 주제: '{extra_keyword}'" if extra_keyword != required_keyword else "")
        scope_instruction = "선택한 글 유형에 맞는 내용만.\n"
        type_instruction = "7:2:1 비율과 카테고리 가이드에 맞게 유형을 정한 뒤, 그에 맞는 제목·개요만 제시해."
        prompt_lead = f"{keyword_instruction}을 중심으로 블로그 포스팅의 제목과 개요를 정해줘."
    return post_type, keyword_instruction, scope_instruction, type_instruction, prompt_lead


def _template_outline(keyword: str, post_type: str = ""):
    """Ollama 실패·지연 시에도 포스팅이 이어지도록 키워드 기반 개요."""
    if is_naeo_post_type(post_type):
        return naeo_template_outline(keyword)
    kw = (keyword or "코팅").strip() or "코팅"
    title = f"{kw} 직접 해본 셀프 코팅 후기"
    outline = (
        f"## {kw}이 필요한 이유\n"
        f"## 준비물과 작업 전 체크\n"
        f"## 단계별 시공 방법\n"
        f"## 결과 확인과 유지 관리"
    )
    img = f"Close-up of {kw} coated surface with water beads, photorealistic, no text"
    return title, outline, img


def _template_body(
    title: str,
    outline_str: str,
    keyword: str,
    post_type: str = "",
    min_chars: int = 900,
    *,
    config: dict | None = None,
    account_id: str | None = None,
) -> tuple:
    """Ollama 본문 생성 실패 시 네이버 에디터에 넣을 수 있는 원고(최소 분량 보장)."""
    kw = (keyword or "코팅").strip() or "코팅"
    pt = (post_type or "").strip()
    sections = []
    for line in (outline_str or "").splitlines():
        line = line.strip()
        if line.startswith("##"):
            sections.append(line.lstrip("#").strip())
    if not sections:
        if pt in ("맛집/일상", "취미글"):
            sections = ["이번에 간 곳", "기억에 남는 메뉴", "다시 가고 싶은 이유", "한 줄 정리"]
        else:
            sections = ["왜 이 주제가 중요한가", "현장에서 자주 묻는 점", "직접 해본 팁", "마무리"]

    if pt in ("맛집/일상", "취미글"):
        opener = f"영업·시공 일정 사이에 들른 곳이라 기록해 둡니다. 제목 '{title}' 기준으로 짧게 정리했습니다.\n\n"
        section_fill = "분위기와 주차·동선 위주로 적어 두었습니다. 음식은 솔직한 인상만 남깁니다.\n\n"
        tags = "맛집,일상,후기"
    elif is_naeo_post_type(pt):
        opener = (
            "요즘 블로그 유입 숫자와 체감이 예전과 달라서, "
            f"'{title}' 주제로 정리해 봤습니다.\n\n"
        )
        section_fill = (
            "검색·홈피드·AI 답변 노출까지 한 번에 보기 어렵다는 점부터 짚고, "
            "SEO만으로는 부족한 이유를 짧게 풀어 씁니다.\n\n"
        )
        tags = naeo_template_tags()
    elif pt == "제품 홍보":
        opener = (
            f"주방·욕실·가구 오염 때문에 '{kw}'를 찾는 분이 많아, "
            "리빙코트 관점에서 정리했습니다.\n\n"
        )
        section_fill = (
            "생활 오염은 닦기 전 준비가 절반입니다. "
            "표면을 말린 뒤 얇게 반복 도포하면 관리 부담이 줄어듭니다.\n\n"
        )
        tags = f"{kw},리빙코트,주방관리"
    else:
        opener = (
            f"현장에서 '{kw}' 관련 문의가 잦아, 10년 넘게 시공해 본 기준으로 정리했습니다.\n\n"
        )
        section_fill = (
            "먼지·기름막 제거 후 얇게 여러 번 나눠 작업하면 마감이 균일해집니다. "
            "완공 후에는 전용 건식 관리제로 발수를 유지하는 편이 낫습니다.\n\n"
        )
        tags = f"{kw},유리막코팅,관리팁"

    cfg = config if isinstance(config, dict) else {}
    exp_line = _build_experience_brief(cfg, pt, kw, account_id).split("\n")
    for line in exp_line:
        if line.startswith("【도입 참고】") or line.startswith("【이번 앵글】"):
            opener = line.replace("【도입 참고】 ", "").replace("【이번 앵글】 ", "") + "\n\n" + opener
            break

    fillers = [
        section_fill,
        "표면 상태를 먼저 확인한 뒤, 제품 설명서에 맞는 도포 간격을 지키는 편이 낫습니다.\n\n",
        "완공 직후에는 직사광선 아래서 물을 뿌려 발수와 잔여물을 함께 점검해 보세요.\n\n",
        "주기적으로 전용 관리제로 발수를 복원하면 초기 마감을 오래 유지할 수 있습니다.\n\n",
    ]
    parts = [f"## {sections[0]}\n\n", opener]
    for i, sec in enumerate(sections[1:]):
        parts.append(f"## {sec}\n\n")
        parts.append(fillers[i % len(fillers)])
    parts.append("[IMAGE]\n\n")
    body = _pad_body_to_min_length("".join(parts), max(min_chars, 900))
    return _finalize_blog_article(
        body,
        tags,
        config=cfg,
        post_type=pt,
        title=title,
        keyword=kw,
        account_id=account_id,
    )


def _apply_body_quality_guard(config, body, tags, keyword, intent_plan, log_func):
    if config.get("enable_quality_guard", True):
        try:
            from blog_quality_guard import revise_article, summarize_quality_report

            revised_body, quality_report = revise_article(body, keyword, intent_plan)
            config["_quality_report"] = quality_report
            _safe_log(log_func, f"      [품질 보정] {summarize_quality_report(quality_report)}")
            return revised_body, tags
        except Exception as quality_exc:
            _safe_log(log_func, f"      [품질 보정 생략] {quality_exc}")
    else:
        try:
            from blog_quality_guard import inspect_article

            base_report = inspect_article(body, keyword, intent_plan)
            config["_quality_report"] = {"before": base_report, "after": base_report}
        except Exception:
            pass
    return body, tags


def _template_body_with_quality(
    title,
    outline_str,
    required_keyword,
    post_type,
    *,
    min_chars,
    config,
    account_id,
    intent_plan,
    log_func,
):
    body, tags = _template_body(
        title,
        outline_str,
        required_keyword,
        post_type,
        min_chars=min_chars,
        config=config,
        account_id=account_id,
    )
    return _apply_body_quality_guard(
        config, body, tags, required_keyword, intent_plan, log_func
    )


async def generate_outline(config, required_keyword, extra_keyword, log_func, master_guidelines_str):
    """1단계: 제목·개요·이미지설명만 생성. 맥락에 맞는 글 흐름을 먼저 정함."""
    if extra_keyword is None:
        extra_keyword = required_keyword
    post_type, keyword_instruction, scope_instruction, type_instruction, prompt_lead = _get_keyword_and_scope_instructions(
        config, required_keyword, extra_keyword
    )
    if config.get("enable_intent_planner", True):
        try:
            from blog_intent_planner import build_intent_plan, render_plan_prompt

            intent_plan = build_intent_plan(required_keyword, post_type)
            config["_intent_plan"] = intent_plan
            intent_prompt = render_plan_prompt(intent_plan)
            _safe_log(
                log_func,
                f"      [의도 분석] {intent_plan.get('intent_type')} · {intent_plan.get('reader_question')}",
            )
        except Exception:
            intent_plan = {}
            intent_prompt = ""
    else:
        intent_plan = {}
        intent_prompt = ""
    master_guidelines = (master_guidelines_str or config.get("master_guidelines") or DEFAULT_MASTER_GUIDELINES).strip()

    if is_naeo_post_type(post_type):
        if not (required_keyword or "").strip():
            required_keyword = default_keyword()
        title, outline_str, image_desc = naeo_template_outline(required_keyword)
        _safe_log(log_func, "      [NAEO] 영상 챕터 고정 개요 적용")
        _safe_log(log_func, "      [개요] 제목·개요 확정 → 본문 작성 단계로 진행")
        if image_desc:
            preview = image_desc.strip().replace("\n", " ")[:100]
            _safe_log(log_func, f"      [이미지 장면] {preview}{'…' if len(image_desc) > 100 else ''}")
        return title, outline_str, image_desc

    ollama_mode = _normalize_text_provider(config) == "ollama"
    if ollama_mode:
        guidelines_block = _build_ollama_guidelines_block(
            master_guidelines,
            post_type,
            scope_instruction,
            keyword_instruction,
            config=config,
            keyword=required_keyword,
            max_chars=900,
            for_outline=True,
        )
        outline_prompt = (
            f"{guidelines_block}\n\n"
            f"{intent_prompt}\n"
            f"{type_instruction}\n"
            f"키워드 '{required_keyword}' 주제의 네이버 블로그 글 제목·개요만 작성. 본문은 쓰지 마라.\n"
            "제목 예: '장마철 체인 녹, 미리 막는 3가지' (판매 문구·브랜드 나열 금지).\n"
            "개요는 ## 소제목 4~6개, 각 줄에 한 줄 설명.\n"
            "=== 아래 형식만 출력 ===\n"
            "[TITLE]\n제목 한 줄\n"
            "[OUTLINE]\n## 소제목 → 한 줄 설명\n"
            "[IMAGE_DESC]\n영어 이미지 설명 한 문장\n"
        )
    else:
        outline_prompt = (
            f"{prompt_lead} "
            "자동차 코팅제·바이크 코팅제·리빙코팅제를 개발하는 10년 경력 제조 이사의 시선으로, 네이버/티스토리용 블로그 포스팅 하나를 기획해줘.\n"
            f"{type_instruction}\n{scope_instruction}\n{intent_prompt}\n"
            "아래 형식으로만 출력해. 본문은 쓰지 마라.\n"
            "[TITLE]\n(제목 한 줄, 50자 이내, 호기심·정보성)\n"
            "[OUTLINE]\n"
            "(H2 소제목과 해당 섹션에서 다룰 내용을 한 줄씩 4~6개. 예: '## 왜 타일 코팅이 필요한가 → 오염·습도 문제와 코팅의 역할')\n"
            "[IMAGE_DESC]\n"
            "(이 포스팅 대표 이미지로 쓸 장면을 영어로 한 문장. 예: Bright bathroom tiles with water beads after coating, no text, photorealistic)\n"
        )
    fallback_title = f"{required_keyword} 셀프 코팅 후기" if required_keyword else "코팅 후기"
    fallback_outline = "## 도입 (공감)\n## 원리 설명\n## 시공 방법\n## 마무리"
    fallback_img = "Clean coated surface with water beads, photorealistic, no text"

    outline_predict = 550 if ollama_mode else 1200
    try:
        if ollama_mode:
            if not await _ollama_ping_with_retry(log_func, attempts=3):
                _safe_log(log_func, "      Ollama 사용 불가 → 템플릿 개요로 진행합니다.")
                return _template_outline(required_keyword, post_type)
            deadline = _ollama_async_deadline(outline_predict)
            text = await asyncio.wait_for(
                _generate_text_with_fallback(config, outline_prompt, log_func, num_predict=outline_predict),
                timeout=deadline,
            )
        else:
            text = await _generate_text_with_fallback(config, outline_prompt, log_func, num_predict=outline_predict)
    except asyncio.TimeoutError:
        _safe_log(log_func, "      Ollama 개요 생성 지연 → 템플릿 개요로 진행합니다.")
        return _template_outline(required_keyword, post_type)
    except Exception as e:
        if _is_quota_error(str(e)):
            _log_quota_hint(log_func)
        _safe_log(log_func, f"      개요 생성 오류: {e}")
        if ollama_mode:
            _safe_log(log_func, "      템플릿 개요로 에디터 진입을 계속합니다.")
            return _template_outline(required_keyword, post_type)
        return fallback_title, fallback_outline, fallback_img

    text = _trim_to_format_markers(text)
    title_match = re.search(r"\[TITLE\](.*?)(?:\[OUTLINE\]|\[IMAGE)", text, re.S)
    title = _normalize_generated_title(
        title_match.group(1) if title_match else "",
        required_keyword,
        fallback_title,
    )

    outline_match = re.search(r"\[OUTLINE\](.*?)(?:\[IMAGE_DESC\]|$)", text, re.S)
    outline_str = strip_strikethrough_markers(
        outline_match.group(1).strip() if outline_match else fallback_outline
    )
    if len(outline_str.strip()) < 30 or _looks_like_reasoning_leak(outline_str):
        outline_str = fallback_outline

    img_match = re.search(r"\[IMAGE_DESC\](.*?)(?:\n\n|\Z)", text, re.S)
    image_desc = (img_match.group(1).strip() if img_match else fallback_img).strip()
    if not image_desc or len(image_desc) < 10:
        image_desc = fallback_img
    _safe_log(log_func, "      [개요] 제목·개요 확정 → 본문 작성 단계로 진행")
    if image_desc:
        preview = image_desc.strip().replace("\n", " ")[:100]
        _safe_log(log_func, f"      [이미지 장면] {preview}{'…' if len(image_desc) > 100 else ''}")
    return title, outline_str, image_desc


async def generate_body_from_outline(config, title, outline_str, required_keyword, extra_keyword, log_func, master_guidelines_str, account_id=None):
    """2단계: 확정된 제목·개요에 맞춰 본문만 작성. 맥락 이탈(아토피·자동차 등 무관 내용) 금지."""
    if extra_keyword is None:
        extra_keyword = required_keyword
    apply_product_choice(config)
    _, keyword_instruction, scope_instruction, _, _ = _get_keyword_and_scope_instructions(
        config, required_keyword, extra_keyword
    )
    post_type = (config.get("post_type") or "").strip() or "자동(매번 랜덤)"
    ollama_mode = _normalize_text_provider(config) == "ollama"
    master_guidelines = (master_guidelines_str or config.get("master_guidelines") or "").strip()
    extra_guidelines = (config.get("writing_guidelines") or "").strip()
    intent_plan = config.get("_intent_plan") or {}
    try:
        from blog_intent_planner import render_plan_prompt

        intent_prompt = render_plan_prompt(intent_plan)
    except Exception:
        intent_prompt = ""
    min_body_len = _resolve_min_body_len(
        master_guidelines,
        extra_guidelines,
        ollama_mode=ollama_mode,
        config=config,
    )
    _safe_log(log_func, f"      본문 최소 분량: {min_body_len}자 (마스터 지침 기준)")

    if ollama_mode:
        guidelines_block = _build_ollama_guidelines_block(
            master_guidelines,
            post_type,
            scope_instruction,
            keyword_instruction,
            account_id=account_id,
            config=config,
            keyword=required_keyword,
            max_chars=900,
            min_body_len=min_body_len,
        )
        naeo_block = f"\n{outline_for_prompt()}\n" if is_naeo_post_type(post_type) else ""
        body_prompt = (
            f"{guidelines_block}\n\n"
            f"{naeo_block}"
            f"{intent_prompt}\n"
            f"【제목】\n{title}\n\n【개요(반드시 이 순서·내용으로)】\n{outline_str}\n\n"
            f"키워드 '{required_keyword}' 주제 네이버 블로그 본문을 한국어로 작성.\n"
            "개요에 없는 주제(글 유형과 무관한 자동차/리빙/맛집 등)를 섞지 마라.\n"
            f"【구조】 공감(상황) → 해결(원리·팁) → 입증(현장 경험). 본문 최소 {min_body_len}자 이상.\n"
            f"개요의 각 ## 소제목마다 2~3문단, 표 1개 이상(해당 시).\n"
            "【금지】 취소선, 안녕하세요, 알아보겠습니다, 도움이 되었으면 합니다, 그래핀 코팅 주성분 단정.\n"
            "=== 아래 형식만 출력 ===\n"
            "[BODY]\n(## 소제목 포함 본문)\n[TAGS]\n(태그 쉼표 구분, 3~6개)\n"
        )
    else:
        guidelines_text = _trim_guidelines_for_prompt(_default_guidelines(), 5000)
        if master_guidelines:
            guidelines_text += "\n\n[사용자 공통 지침]\n" + _trim_guidelines_for_prompt(master_guidelines, 4000)
        if extra_guidelines:
            guidelines_text += "\n\n[이번 작업 추가 지침]\n" + _trim_guidelines_for_prompt(extra_guidelines, 1500)

        if account_id == "hymini1":
            channel_instruction = "말투·톤: [Style A (hymini1): 10년 경력 제조 이사의 신뢰감 있는 톤 (~입니다).]"
        elif account_id == "hymini11":
            channel_instruction = "말투·톤: [Style B (hymini11): 라이더 시선의 실용 팁 톤 (~해요). 감성 에세이·철학 독백 금지.]"
        else:
            channel_tones = random.sample(CHANNEL_STYLES, min(2, len(CHANNEL_STYLES)))
            channel_instruction = f"말투·톤: [{channel_tones[0]}] + [{channel_tones[1]}]"

        output_styles = [
            "Q&A·질문형 도입 + 단계별 해결",
            "체크리스트 도입 + 원리·팁 설명",
            "Before/After 대비 + 숫자·표 정리",
            "꿀팁 리스트형 + 한 줄 결론",
            "체크리스트형(번호 리스트) + 현장 사례 2~3문장",
        ]
        chosen_styles = random.sample(output_styles, min(2, len(output_styles)))
        style_instruction = (
            "이번 글의 본문 구성은 아래 2가지 스타일을 섞어서 써줘. "
            "이전 글과 최대한 다른 형식이 되도록 구성해.\n"
            f"- {chosen_styles[0]}\n"
            f"- {chosen_styles[1]}\n"
        )

        vivid_angle = random.choice(_VIVID_ANGLES)
        _FORMAT_AVOID_THIS_TIME = [
            "이번에는 감성 에세이·철학 독백 도입을 쓰지 말고, 키워드 관련 질문 한 줄로 바로 시작해줘.",
            "이번에는 '첫째, 둘째, 셋째' 숫자 나열형 본문을 쓰지 말고, Q&A 대화형이나 체크리스트형으로만 풀어줘.",
            "이번에는 '정리하면~', '요약하면~' 같은 마무리 멘트를 쓰지 말고, 독자에게 질문 한 줄로 끝내줘.",
            "이번에는 H2 소제목을 일정한 패턴으로 반복하지 말고, 소제목 길이와 리듬을 일부러 다르게 섞어 써줘.",
            "이번에는 이전 글에서 자주 쓰인 표현(예: 셀프 시공, 꿀팁, 비결)을 피해, 전혀 다른 표현으로 같은 의미를 풀어줘.",
            "이번에는 바이크/자동차 글에서 리빙·주방·욕실·가구·집 풍경 이야기를 한 줄도 넣지 마.",
        ]
        chosen_avoid = random.choice(_FORMAT_AVOID_THIS_TIME)
        format_variety_instruction = (
            "【형식 절대 반복 금지】 같은 형식의 글을 반복해서 쓰지 말 것. "
            "이전에 썼던 글과 구조·제목 패턴·도입부 스타일이 겹치지 않도록 일부러 다르게 구성해.\n"
            f"【이번 글만 해당】 {chosen_avoid}\n"
        )

        perfect_block = _perfect_blog_writing_block(
            post_type=post_type,
            account_id=account_id,
            config=config,
            keyword=required_keyword,
            min_body_len=min_body_len,
        )
        naeo_block = f"\n{outline_for_prompt()}\n" if is_naeo_post_type(post_type) else ""
        body_prompt = (
            f"{perfect_block}\n\n"
            f"{naeo_block}"
            f"{intent_prompt}\n"
            "【필수】 아래 제목과 개요에 맞는 본문만 작성해. 개요에 없는 섹션을 추가하거나, 제목·개요와 무관한 내용을 넣지 마라.\n"
            "예: 제목이 '욕실 타일'이면 자동차 코팅·아토피·바이크 경험 등 다른 주제를 본문에 넣지 말 것. 제목이 '맛집'이면 제품 홍보를 본문 중심으로 넣지 말 것.\n"
            f"【글 유형】 {post_type}\n{scope_instruction}"
            "【제목】\n" + title + "\n\n【개요(반드시 이 순서·내용으로)】\n" + outline_str + "\n\n"
            f"{channel_instruction}\n"
            f"{style_instruction}"
            f"이번 글의 흐름을 만들 때는 반드시 다음 구체적인 앵글을 녹여줘: {vivid_angle}\n"
            f"{format_variety_instruction}"
            "글쓰기 마스터 지침을 준수해 [BODY]와 [TAGS]만 출력해. [TITLE]은 출력하지 마라(이미 정해짐).\n"
            "【금지】 취소선(~~, <s>), '안녕하세요', '알아보겠습니다', 제목·개요와 무관한 경험담(10년 아토피 등은 주제가 코팅/리빙일 때만 한 줄 이내). "
            "감성 에세이·철학 독백·카페·집 풍경·리빙코트 교차 홍보 금지. 작성자 별명이나 아이디를 제품명처럼 쓰지 말 것(예: ○○ 발수코팅제, ○○ 제품 등 X). 제품명은 듀라코트·퍼마코트·리빙코트·퀵·티탄·레진만.\n"
            f"{_ANTI_ESSAY_WRITING_BLOCK}\n"
            "【사실성 엄수】 확인되지 않은 화학/성능 사실은 단정하지 말 것. 특히 그래핀을 코팅 작용 주체로 단정하는 문장(그래핀이 코팅한다/피막형성한다/핵심 코팅 성분이다)은 절대 금지.\n"
            f"【분량】 본문 최소 {min_body_len}자 이상. 개요의 모든 소제목을 빠짐없이 풀어 쓸 것.\n"
            "글쓰기 마스터 지침:\n" + guidelines_text
        )

    fallback_tags = naeo_template_tags() if is_naeo_post_type(post_type) else "blog"

    body_predict = _ollama_body_num_predict(min_body_len) if ollama_mode else 8192
    try:
        retry_prompt = body_prompt
        max_attempts = 4 if ollama_mode else 2
        for attempt in range(max_attempts):
            if ollama_mode and attempt >= 1:
                retry_prompt = (
                    f"{_ollama_type_rules(post_type)}\n"
                    f"{keyword_instruction}\n{scope_instruction}\n"
                    f"제목: {title}\n개요:\n{outline_str}\n"
                    f"한국어 네이버 블로그 본문 최소 {min_body_len}자 이상. 금지어·판매 멘트 없이.\n"
                    "개요 소제목마다 2~3문단. === 형식만 ===\n"
                    "[BODY]\n(## 소제목)\n[TAGS]\n(쉼표 구분)\n"
                )
                body_predict = _ollama_body_num_predict(min_body_len)
            if ollama_mode:
                if not await _ollama_ping_with_retry(log_func, attempts=3):
                    _safe_log(log_func, "      Ollama 사용 불가 → 템플릿 본문으로 진행합니다.")
                    return _template_body_with_quality(
                        title,
                        outline_str,
                        required_keyword,
                        post_type,
                        min_chars=min_body_len,
                        config=config,
                        account_id=account_id,
                        intent_plan=intent_plan,
                        log_func=log_func,
                    )
                deadline = _ollama_async_deadline(body_predict)
                text = await asyncio.wait_for(
                    _generate_text_with_fallback(config, retry_prompt, log_func, num_predict=body_predict),
                    timeout=deadline,
                )
            else:
                text = await _generate_text_with_fallback(config, retry_prompt, log_func, num_predict=body_predict)

            text = _trim_to_format_markers(text)
            if ollama_mode:
                body = _extract_body_from_ollama_text(text)
            else:
                body_match = re.search(r"\[BODY\](.*?)(?:\[TAGS\]|$)", text, re.S)
                body = body_match.group(1).strip() if body_match else ""
            if (not body or _looks_like_reasoning_leak(body)) and text and not _looks_like_reasoning_leak(text):
                body = text.strip()
            if not body or _looks_like_reasoning_leak(body):
                if attempt < max_attempts - 1:
                    _safe_log(log_func, "      본문 파싱 실패 → 재생성")
                    continue
                _safe_log(log_func, "      본문 파싱 실패 → 템플릿 본문으로 진행합니다.")
                return _template_body_with_quality(
                    title,
                    outline_str,
                    required_keyword,
                    post_type,
                    min_chars=min_body_len,
                    config=config,
                    account_id=account_id,
                    intent_plan=intent_plan,
                    log_func=log_func,
                )

            body = strip_strikethrough_markers(body)
            body = re.sub(r"\*\*([^*]+)\*\*", r"\1", body)

            scope_err = _violates_post_type_scope(body, post_type)
            if scope_err and attempt < max_attempts - 1:
                _safe_log(log_func, f"      글 유형 불일치({scope_err}) → 본문 재생성")
                retry_prompt = (
                    body_prompt
                    + f"\n\n[교정] {scope_err}. {_ollama_type_rules(post_type)} 다시 준수해 작성."
                )
                continue

            if _contains_banned_phrases(body) and attempt < max_attempts - 1:
                _safe_log(log_func, "      금지어 포함 → 본문 재생성")
                retry_prompt = body_prompt + "\n\n[교정] 금지어(안녕하세요·알아보겠습니다 등) 없이 다시 작성."
                continue

            if _contains_narrative_cliches(body) and attempt < max_attempts - 1:
                _safe_log(log_func, "      감성 에세이·주제 이탈 서사 → 본문 재생성")
                retry_prompt = (
                    body_prompt
                    + "\n\n[교정] 감성 에세이·철학 독백·카페·집 풍경·리빙코트 교차 홍보를 모두 제거하고, "
                    "키워드 관련 실용 팁·체크리스트 중심으로 다시 작성."
                )
                continue

            if _contains_fact_violation(body) and attempt < max_attempts - 1:
                _safe_log(log_func, "      사실성 검증 실패(그래핀) → 본문 재생성")
                retry_prompt = (
                    body_prompt
                    + "\n\n[교정 지시] 그래핀을 코팅 작용 주체로 단정하는 문장을 모두 제거하고 다시 작성해."
                )
                continue

            if len(body) < min_body_len:
                if not ollama_mode and len(body) >= int(min_body_len * 0.85):
                    _safe_log(
                        log_func,
                        f"      본문 길이 {len(body)}자 → 보강 후 확정 (재생성 생략)",
                    )
                    body = _pad_body_to_min_length(body, min_body_len)
                elif attempt < max_attempts - 1:
                    _safe_log(
                        log_func,
                        f"      본문 길이 미달 ({len(body)}자 < {min_body_len}자) → 재생성",
                    )
                    retry_prompt = (
                        body_prompt
                        + f"\n\n[교정] 본문이 {len(body)}자로 너무 짧습니다. 반드시 최소 {min_body_len}자 이상. "
                        "개요의 모든 ## 소제목을 빠짐없이 풀어 쓰고, 각 절마다 구체적 설명·현장 팁·예시를 추가해 다시 작성."
                    )
                    if ollama_mode:
                        body_predict = _ollama_body_num_predict(min_body_len)
                    continue
                else:
                    _safe_log(
                        log_func,
                        f"      본문 길이 미달 ({len(body)}자) → 보강 후 확정",
                    )
                    body = _pad_body_to_min_length(body, min_body_len)

            if len(body) < min_body_len:
                _safe_log(
                    log_func,
                    f"      본문 길이 미달 ({len(body)}자) → 템플릿으로 보강 ({min_body_len}자)",
                )
                return _template_body_with_quality(
                    title,
                    outline_str,
                    required_keyword,
                    post_type,
                    min_chars=min_body_len,
                    config=config,
                    account_id=account_id,
                    intent_plan=intent_plan,
                    log_func=log_func,
                )

            tag_match = re.search(r"\[TAGS\](.*)", text, re.S)
            tags = _normalize_generated_tags(
                tag_match.group(1) if tag_match else "",
                required_keyword,
                fallback_tags,
            )
            body, tags = _finalize_blog_article(
                body,
                tags,
                config=config,
                post_type=post_type,
                title=title,
                keyword=required_keyword,
                account_id=account_id,
            )
            body, tags = _apply_body_quality_guard(
                config, body, tags, required_keyword, intent_plan, log_func
            )
            _safe_log(log_func, f"      본문 확정 ({len(body)}자 / 최소 {min_body_len}자)")
            return body, tags

        _safe_log(log_func, "      본문 품질 미달 → 템플릿 본문으로 진행합니다.")
        return _template_body_with_quality(
            title,
            outline_str,
            required_keyword,
            post_type,
            min_chars=min_body_len,
            config=config,
            account_id=account_id,
            intent_plan=intent_plan,
            log_func=log_func,
        )
    except asyncio.TimeoutError:
        _safe_log(log_func, "      본문 생성 지연 → 템플릿 본문으로 진행합니다.")
        return _template_body_with_quality(
            title,
            outline_str,
            required_keyword,
            post_type,
            min_chars=min_body_len,
            config=config,
            account_id=account_id,
            intent_plan=intent_plan,
            log_func=log_func,
        )
    except Exception as e:
        if _is_quota_error(str(e)):
            _log_quota_hint(log_func)
        _safe_log(log_func, f"      본문 생성 오류: {e}")
        _safe_log(log_func, "      템플릿 본문으로 에디터 진입을 계속합니다.")
        return _template_body_with_quality(
            title,
            outline_str,
            required_keyword,
            post_type,
            min_chars=min_body_len,
            config=config,
            account_id=account_id,
            intent_plan=intent_plan,
            log_func=log_func,
        )


async def generate_content(config, required_keyword, extra_keyword, log_func, master_guidelines_str, account_id=None):
    """필수/추가 키워드로 블로그 원고 생성. account_id가 hymini1/hymini11이면 해당 계정 톤으로 고정해 hymini1과 hymini11 글이 달라지게 함."""
    if extra_keyword is None:
        extra_keyword = required_keyword
    apply_product_choice(config)
    post_type = (config.get("post_type") or "").strip() or "자동(매번 랜덤)"

    # 글 유형별 키워드 처리 (Override Rules). 문자열은 POST_TYPES와 동기화 유지. 유형 추가 시 scope_instruction 분기도 함께 수정할 것.
    if post_type in ("맛집/일상", "취미글"):
        keyword_instruction = (
            "【키워드 100% 무시】 입력된 '포스팅 키워드'는 전부 무시한다. "
            "사장님의 실제 취미(낚시 힐링, 전국 맛집 탐방, 할리/인디언/두카티 바이크 투어, 외제 신차 시승)만 사용하여 에세이 형태로 작성한다. "
            "제품명·듀라코트·리빙코트·코팅제·퀵·티탄·레진 등 키워드는 사용하지 말 것. 제품 홍보가 섞이면 거짓 정보가 된다."
        )
    elif post_type in ("자동차 정보", "바이크 정보", "코팅제 정보"):
        keyword_instruction = (
            f"퀵(14%)·티탄(28%)·레진(60% 원액+30% 레진)·전용 건식 관리제 관련만 사용한다. "
            "리빙코트·수전·싱크대·욕실·가구 등 생활용 키워드는 절대 섞지 않는다. "
            f"(참고: 이번 주제 '{required_keyword}' 중 자동차/바이크/코팅제 관련만 선별 사용, 나머지는 무시)"
        )
    elif post_type == "제품 홍보":
        keyword_instruction = (
            "듀라코트 리빙코트(주방, 욕실, 가구 등 생활 오염 방지) 관련만 사용한다. "
            "자동차/바이크 코팅제 스펙(퀵·티탄·레진 %) 키워드는 사용하지 말 것."
        )
    else:
        keyword_instruction = f"필수 주제: '{required_keyword}'" + (
            f", 이번 글에 반드시 포함할 추가 주제: '{extra_keyword}'" if extra_keyword != required_keyword else ""
        )

    master_guidelines = (master_guidelines_str or config.get("master_guidelines") or DEFAULT_MASTER_GUIDELINES).strip()
    extra_guidelines = (config.get("writing_guidelines") or "").strip()
    ollama_mode = _normalize_text_provider(config) == "ollama"
    min_body_len = _resolve_min_body_len(
        master_guidelines,
        extra_guidelines,
        ollama_mode=ollama_mode,
        config=config,
    )
    _safe_log(log_func, f"      본문 최소 분량: {min_body_len}자 (마스터 지침 기준)")
    guidelines_text = _default_guidelines()
    if master_guidelines:
        guidelines_text += "\n\n[사용자 공통 지침]\n" + master_guidelines
    if extra_guidelines:
        guidelines_text += "\n\n[이번 작업 추가 지침]\n" + extra_guidelines

    # 채널별 출력 스타일 4가지 중 매번 2개 랜덤 선택 → 형식 단조로움 방지
    output_styles = [
        "Q&A·질문형 도입 + 단계별 해결",
        "체크리스트 도입 + 원리·팁 설명",
        "Before/After 대비 + 숫자·표 정리",
        "꿀팁 리스트형 + 한 줄 결론",
    ]
    chosen_styles = random.sample(output_styles, min(2, len(output_styles)))
    style_instruction = f"이번 글의 구성은 아래 2가지 스타일을 조합해서 써줘. (매번 다른 형식이 되도록) [{chosen_styles[0]}] + [{chosen_styles[1]}]"
    # 계정별 톤: hymini1 → Style A, hymini11 → Style B 고정 (두 계정 글 다르게). 그 외는 랜덤 2개 조합
    if account_id == "hymini1":
        channel_instruction = "말투·톤은 반드시 아래만 사용해. [Style A (hymini1): 10년 경력 제조 이사의 신뢰감 있는 톤 (~입니다).]"
    elif account_id == "hymini11":
        channel_instruction = "말투·톤은 반드시 아래만 사용해. [Style B (hymini11): 라이더 시선의 실용 팁 톤 (~해요). 감성 에세이·철학 독백 금지.]"
    else:
        channel_tones = random.sample(CHANNEL_STYLES, min(2, len(CHANNEL_STYLES)))
        channel_instruction = f"말투·톤은 아래 2가지를 섞어서 써줘. [{channel_tones[0]}] + [{channel_tones[1]}]"

    # scope/keyword 분기 문자열은 POST_TYPES와 동일하게 유지. 유형 추가 시 POST_TYPES + 여기 분기 + keyword_instruction 분기 모두 반영할 것.
    scope_instruction = ""
    if post_type == "자동(매번 랜덤)":
        type_instruction = "이번 글은 사용자 지침의 7:2:1 비율과 카테고리 가이드에 맞게 유형(정보/전문/홍보, 취미, 맛집 등)을 스스로 정해, 그에 맞는 제목·본문·말투로 작성해."
        tone_choice = random.choice(['정보 전달형', '사용 후기형', '비포애프터 강조형', '감성 블로그 스타일', '전문가 리뷰 스타일'])
        prompt_lead = (
            f"{keyword_instruction}을(를) 중심으로, 자동차 코팅제·바이크 코팅제·리빙코팅제를 개발하고 있는 10년 경력 제조 이사의 시선에서 "
            "네이버/티스토리/구글에 함께 활용 가능한 블로그 포스팅 원고를 작성해줘. "
        )
    else:
        type_instruction = (
            f"이번 글 유형: [{post_type}]. 반드시 이 유형에 맞는 글만 쓴다. "
            "맛집을 골랐으면 맛집 글, 취미를 골랐으면 취미 글, 자동차 정보를 골랐으면 자동차만—유형과 다른 주제(예: 맛집 선택했는데 듀라코트 리빙코트 설명)는 절대 쓰지 말 것. "
            "아래 지침에서 이 유형에 해당하는 작성 가이드와 7:2:1, '판매가 아닌 해결 중심'을 따르고, 유형에 맞는 제목·본문·말투로만 작성할 것."
        )
        # 글 유형에 맞는 내용만: 맛집=맛집글, 취미=취미글, … 제품(리빙코트)을 주제로 넣지 말 것.
        if post_type == "자동차 정보":
            scope_instruction = (
                "【범위】 자동차 정보만. 퀵(14%)·티탄(28%)·레진(60%+30%)·전용 건식 관리제만 사용. "
                "리빙코트 언급 금지. 세면대·싱크대·수전·욕실·가구 등 생활용 맥락은 한 줄도 쓰지 말 것(데이터 꼬임·거짓 방지). 바이크 언급 금지.\n"
            )
        elif post_type == "바이크 정보":
            scope_instruction = (
                "【범위】 바이크 정보만. 퀵·티탄·레진·바이크 전용 건식 관리제만 사용. "
                "리빙코트 언급 금지. 세면대·싱크대·수전·욕실·가구·우리 집·리빙 코팅 등 생활용 맥락은 한 줄도 쓰지 말 것. "
                "감성 에세이·카페·집 풍경·철학 독백 금지. 자동차·승용차·차량은 한 줄도 쓰지 말 것.\n"
            )
        elif post_type == "맛집/일상":
            scope_instruction = (
                "【범위】 맛집이면 맛집에 관한 글만 쓴다. 음식·맛집·방문 후기·일상·카공·맛집 추천이 주제. "
                "듀라코트 리빙코트·코팅제를 주제로 한 제품 설명을 쓰지 말 것. 본문은 맛집·일상 이야기만. 제품은 맛집 이야기 속 한두 줄만 가능.\n"
            )
        elif post_type == "취미글":
            scope_instruction = (
                "【범위】 취미면 취미에 관한 글만 쓴다. 낚시·드라이브·바이크 투어·일상 취미·취미 경험이 주제. "
                "듀라코트·리빙코트·코팅제 홍보나 제품 설명을 본문 중심으로 쓰지 말 것. 본문은 취미·일상 이야기만.\n"
            )
        elif post_type == "코팅제 정보":
            scope_instruction = (
                "【범위】 코팅제 정보만. 퀵(14%)·티탄(28%)·레진(60%+30%)·전용 건식 관리제·원리·시공만. "
                "리빙코트 언급 금지. 세면대·싱크대·수전·욕실·가구 등 생활용 맥락은 쓰지 말 것. 맛집·취미 일상은 주제로 쓰지 말 것.\n"
            )
        elif post_type == "정보성 팁":
            scope_instruction = (
                "【범위】 정보성 팁만. 10년 경력 광택/유리막 시공 노하우, 아토피 안심 천연 비누 제작 팁 등. "
                "제품 나열형이 아니라 '방법·원리' 위주. 근거 없는 수치 제시 금지.\n"
            )
        elif post_type == "제품 홍보":
            scope_instruction = (
                "【범위】 제품 홍보(Living 중심)만. 듀라코트 리빙코트(주방, 욕실, 가구 등 생활 오염 방지) 소개·시공 후기·이벤트만. "
                "자동차/바이크 코팅제 스펙(퀵·티탄·레진 %) 언급 금지. 맛집·취미 일상 글이 아님.\n"
            )
        elif post_type == "알림글":
            scope_instruction = (
                "【범위】 알림만. 공지·이벤트·안내·업데이트가 주제. 다른 유형으로 쓰지 말 것.\n"
            )
        elif is_naeo_post_type(post_type):
            scope_instruction = (
                "【범위】 NAEO·SEO·AEO·GEO·네이버 AI·블로그 유입만. "
                "코팅제·듀라코트·스마트스토어 판매 유도 금지.\n"
                + outline_for_prompt()
                + "\n"
            )
        else:
            scope_instruction = "【범위】 선택한 글 유형에 맞는 내용만 쓴다. 유형과 다른 주제를 본문 중심으로 쓰지 말 것.\n"
        tone_choice = "정보 전달형" if "정보" in post_type or "팁" in post_type else "감성 블로그 스타일" if "취미" in post_type or "맛집" in post_type else "전문가 리뷰 스타일"
        prompt_lead = (
            f"선택한 글 유형 [{post_type}]과 아래 사용자 지침을 최우선으로 해서 블로그 포스팅 원고를 작성해줘. "
            f"참고 키워드: {keyword_instruction}. (키워드는 유형·지침에 맞을 때만 활용하고, 유형과 지침에 맞는 내용을 우선해.) "
            "자동차 코팅제·바이크 코팅제·리빙코팅제를 개발하고 있는 10년 경력 제조 이사의 시선으로 써줘. "
        )

    vivid_angle = random.choice(_VIVID_ANGLES)
    # 절대로 같은 형식 사용 금지: 매 요청마다 하나의 '금지 형식'을 랜덤 지정해 다른 구성을 강제
    _FORMAT_AVOID_THIS_TIME = [
        "이번에는 감성 에세이·철학 독백 도입을 쓰지 말고, 키워드 관련 질문 한 줄로 바로 시작해줘.",
        "이번에는 '1, 2, 3' 숫자 나열형 본문을 쓰지 말고, Q&A 대화형이나 한 가지 포인트를 깊게 파는 단일 테마형으로 써줘.",
        "이번에는 '~방법', '~비결', '~꿀팁' 같은 제목을 쓰지 말고, 호기심을 자극하는 질문형 제목이나 한 줄 경험담형 제목으로 지어줘.",
        "이번에는 H2 소제목을 3개 나열하는 방식을 쓰지 말고, H2를 2개만 쓰거나, 하나의 긴 흐름으로 풀어쓰는 형식으로 써줘.",
        "이번에는 'Before/After' 대비형 도입을 쓰지 말고, 독자 질문 한 줄로 시작하거나 계절·상황 묘사로 시작하는 형식으로 써줘.",
        "이번에는 마지막을 '정리하면~', '요약하면~'으로 끝내지 말고, 독자에게 던지는 질문이나 다음에 할 일 한 줄로 끝내줘.",
    ]
    chosen_avoid = random.choice(_FORMAT_AVOID_THIS_TIME)
    format_variety_instruction = (
        "【형식 절대 반복 금지】 같은 형식의 글을 절대로 쓰지 말 것. 이전에 썼던 글과 구조·제목 패턴·서론/결론 스타일이 겹치면 안 된다. "
        "매번 다른 구성을 사용할 것. 지금까지 자주 쓰인 형식은 쓰지 말고 반드시 다른 형식으로 쓸 것. "
        f"【이번 글만 해당】 {chosen_avoid}\n"
    )

    prompt = (
        prompt_lead
        + "글에서 '나눔랩 개발자'라고 쓰지 말고, '자동차 코팅제, 바이크 코팅제, 리빙코팅제를 개발하고 있는 제조 이사입니다' 정도로만 소개해. 작성자 별명이나 아이디를 제품명처럼 붙여 쓰지 말 것.\n"
        f"{type_instruction}\n"
        f"{scope_instruction}"
        f"{style_instruction}\n"
        f"{channel_instruction}\n"
        f"이번 포스팅의 전체 톤은 '{tone_choice}'에 가깝게 잡되, 전문성과 친근함이 함께 느껴지도록 구성해.\n"
        f"【이번 글에 반드시 반영】 {vivid_angle}\n"
        f"{format_variety_instruction}"
        "【금지】 '안녕하세요', '알아보겠습니다', '도움이 되었으면 합니다', '짜증 나시죠?' 등 AI스러운 상투적 도입부·광고 멘트는 사용하지 마세요.\n"
        "【사실성 엄수】 확인되지 않은 정보는 단정하지 마세요. 특히 그래핀을 코팅 작용의 주체로 단정하는 문장(그래핀이 코팅한다/피막형성한다/핵심 코팅 성분이다)은 절대 금지.\n"
        f"【분량】 [BODY] 본문은 반드시 최소 {min_body_len}자 이상. 소제목마다 2~3문단, 표 1개 이상(해당 시).\n"
        "아래 '글쓰기 마스터 지침(Master Directives)'을 반드시 준수해서 [TITLE], [BODY], [TAGS] 형식으로 출력해.\n"
        "【필수】 취소선은 절대 사용하지 마세요. ~~, <s>, <strike>, text-decoration:line-through 등 어떤 형태도 쓰지 말고, "
        "해당 문장은 그냥 일반 텍스트로만 출력하세요. (취소선 사용 시 블로그 발행 오류가 발생합니다.)\n"
        "글쓰기 마스터 지침:\n"
        + guidelines_text
    )

    fallback = (
        f"{required_keyword} 셀프 코팅 후기",
        "제품 소개 [IMAGE] 시공 방법 [IMAGE] 사용 후기 [IMAGE]",
        "듀라코트 리빙코트, 셀프코팅",
    )
    max_retries = 4 if ollama_mode else 3
    last_error = None
    retry_prompt = prompt
    num_predict = _ollama_body_num_predict(min_body_len) if ollama_mode else 8192

    for attempt in range(max_retries):
        try:
            text = await _generate_text_with_fallback(
                config, retry_prompt, log_func, num_predict=num_predict
            )

            title_match = re.search(r"\[TITLE\](.*?)\[BODY\]", text, re.S)
            title = title_match.group(1).strip() if title_match else fallback[0]
            title = strip_strikethrough_markers(re.sub(r"\*\*([^*]+)\*\*", r"\1", title))[:100]

            body_match = re.search(r"\[BODY\](.*?)\[TAGS\]", text, re.S)
            body = body_match.group(1).strip() if body_match else text
            body = strip_strikethrough_markers(body)
            body = re.sub(r"\*\*([^*]+)\*\*", r"\1", body)

            # 마무리 문장 랜덤 추가 제거 — 제목·맥락과 어긋나는 한 줄 방지(예: 욕실 글 끝에 '5분 시공 꿀팁' 등)

            tag_match = re.search(r"\[TAGS\](.*)", text, re.S)
            tags = tag_match.group(1).strip() if tag_match else "blog"

            if _contains_fact_violation(body):
                log_func("      ⚠️ 사실성 검증 실패(그래핀 관련 표현) → 재시도")
                if attempt < max_retries - 1:
                    retry_prompt = prompt + "\n\n[교정] 그래핀을 코팅 주체로 단정하는 문장 제거 후 다시 작성."
                    await asyncio.sleep(1)
                    continue

            if len(body) < min_body_len and attempt < max_retries - 1:
                log_func(
                    f"      ⚠️ 본문 길이 미달 ({len(body)}자 < {min_body_len}자) → 재생성"
                )
                retry_prompt = (
                    prompt
                    + f"\n\n[교정] 본문이 {len(body)}자로 너무 짧습니다. "
                    f"반드시 최소 {min_body_len}자 이상으로, 소제목마다 구체적 설명·팁·예시를 추가해 다시 작성."
                )
                if ollama_mode:
                    num_predict = _ollama_body_num_predict(min_body_len)
                await asyncio.sleep(1)
                continue

            if len(body) < min_body_len:
                log_func(
                    f"      ⚠️ 본문 길이 미달 ({len(body)}자) → 최소 {min_body_len}자까지 보강"
                )
                body = _pad_body_to_min_length(body, min_body_len)

            log_func(f"      본문 확정 ({len(body)}자 / 최소 {min_body_len}자)")
            return title, body, tags
        except Exception as e:
            last_error = e
            err_msg = str(e)
            is_429 = "429" in err_msg or "quota" in err_msg.lower()
            if is_429 and attempt < max_retries - 1:
                delay = 15
                match = re.search(r"retry in ([\d.]+)\s*s", err_msg, re.I)
                if match:
                    delay = min(60, max(10, int(float(match.group(1)) + 1)))
                log_func(f"      ⚠️ 원고 생성 쿼터(429) — {delay}초 후 재시도 ({attempt + 1}/{max_retries})...")
                await asyncio.sleep(delay)
                continue
            log_func(f"      ⚠️ 원고 생성 오류: {e}")
            return fallback

    log_func(f"      ⚠️ 원고 생성 오류(재시도 소진): {last_error}")
    return fallback


def _build_image_prompt(
    required_keyword,
    extra_keyword,
    post_type=None,
    title=None,
    image_desc=None,
    variant: str | None = None,
):
    """이미지 생성용 프롬프트. variant=mid(중간)·end(끝)로 장면을 구분."""
    shot_styles = [
        "close-up macro shot",
        "wide-angle composition",
        "top-down editorial shot",
        "eye-level realistic product scene",
        "cinematic perspective",
    ]
    lighting_styles = [
        "soft morning daylight",
        "golden hour warm lighting",
        "neutral studio lighting",
        "high-contrast dramatic lighting",
        "diffused indoor natural light",
    ]
    color_moods = [
        "clean minimal color palette",
        "high-contrast modern palette",
        "warm natural tones",
        "cool premium metallic tones",
        "balanced neutral tones",
    ]
    style_hint = random.choice(shot_styles)
    light_hint = random.choice(lighting_styles)
    mood_hint = random.choice(color_moods)

    if variant == "mid":
        variant_hint = (
            "Mid-article scene: in-progress application, close-up detail, or before/during work "
            f"clearly related to '{required_keyword}'. Different angle from a finished result shot."
        )
    elif variant == "end":
        variant_hint = (
            "End-article scene: finished result with strong water beading and deep gloss "
            f"clearly related to '{required_keyword}'. Satisfying after-shot, not a duplicate mid scene."
        )
    else:
        variant_hint = ""

    # 만약 기본 템플릿의 범용 블로거 이미지 프롬프트("Modern blogger...")가 들어온 경우, 이를 무시하고 키워드 매칭 이미지를 생성하도록 함
    if image_desc and image_desc.strip() and "Modern blogger" not in image_desc and "blogger analyzing" not in image_desc:
        desc = image_desc.strip()
        if len(desc) > 500:
            desc = desc[:500]
        return (
            f"{desc}. "
            f"{variant_hint} "
            f"{style_hint}, {light_hint}, {mood_hint}. "
            "Make this scene clearly different from previous generated images. "
            "No text or letters, no people. Photorealistic."
        )
    post_type = (post_type or "").strip()
    if post_type == "맛집/일상":
        return (
            "A warm, appetizing photo of restaurant food or cafe scene, "
            "dish on table, soft natural lighting, no text or people in frame. Photorealistic, inviting."
        )
    if post_type == "취미글":
        return (
            "A photo of hobby or lifestyle scene: fishing, motorcycle touring, or outdoor activity, "
            "natural lighting, no text or people in frame. Photorealistic, atmospheric."
        )
    if extra_keyword is None:
        extra_keyword = required_keyword
    keyword_for_img = f"{required_keyword} and {extra_keyword}" if extra_keyword != required_keyword else required_keyword
    kw_all = f"{required_keyword} {extra_keyword}".lower()
    if any(k in kw_all for k in ["욕실", "화장실", "샤워부스"]):
        scene_hint = "bright bathroom interior with tiles and glass shower booth, water beads visible on surfaces"
    elif any(k in kw_all for k in ["주방", "싱크", "싱크대", "가스레인지", "인덕션"]):
        scene_hint = "modern kitchen sink and cooktop area, clean surfaces, traces of water and oil"
    elif any(k in kw_all for k in ["가구", "원목", "마루", "테이블", "식탁"]):
        scene_hint = "wooden table and furniture in a living or dining room, warm lighting, clean coated surface"
    elif any(k in kw_all for k in ["자동차", "카", "vehicle", "car"]):
        scene_hint = "car hood and body close-up, strong reflection and water beading on coated paint"
    elif any(k in kw_all for k in ["바이크", "오토바이", "motorcycle", "bike"]):
        scene_hint = "motorcycle tank and engine area, metallic gloss and water-repellent coating effect"
    else:
        scene_hint = "home interior surfaces that are often exposed to water and stains, looking very clean"
    return (
        f"A high-quality product photo for a coating brand about {keyword_for_img}. "
        f"{scene_hint}. "
        f"{variant_hint} "
        f"{style_hint}, {light_hint}, {mood_hint}. "
        "The composition must be visually different from previous images for the same keyword. "
        "Show strong water beading and deep gloss on the surface. "
        "No text or letters, no people. Photorealistic, detailed."
    )


async def _generate_images_vertex(config, prompt, log_func, image_dir):
    """Vertex AI(Imagen)로 이미지 생성. 성공 시 경로 리스트, 실패 시 빈 리스트."""
    if not _lazy_vertex() or not config.get("vertex_project_id"):
        return []
    v_project = config["vertex_project_id"].strip()
    if not v_project:
        return []
    v_json = config.get("vertex_json") or cfg.VERTEX_JSON_PATH
    try:
        log_func("         🎨 Vertex AI로 AI 이미지를 생성합니다...")
        if v_json and os.path.exists(v_json):
            os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = os.path.abspath(v_json)
        else:
            try:
                os.environ["GOOGLE_CLOUD_QUOTA_PROJECT"] = v_project
            except Exception:
                pass
        _vertexai.init(project=v_project, location="us-central1")
        v_model = _ImageGenerationModel.from_pretrained("imagen-3.0-generate-001")
        v_res = await asyncio.to_thread(
            v_model.generate_images,
            prompt=prompt,
            number_of_images=1,
        )
        if v_res and v_res.images:
            fpath = os.path.join(image_dir, f"img_{datetime.now().strftime('%H%M%S')}_0.png")
            v_res.images[0].save(fpath)
            log_func("         ✅ AI 이미지 1개 생성 완료 (Vertex AI)")
            return [fpath]
    except Exception as e:
        err_msg = str(e)[:120]
        log_func(f"         ⚠️ Vertex AI 이미지 생성 실패: {err_msg}")
        if "403" in err_msg or "quota" in err_msg.lower() or "Application Default" in err_msg:
            log_func("         💡 Vertex 403 해결: key.json(서비스 계정) 사용 또는 gcloud auth application-default set-quota-project " + v_project)
    return []


def _save_gemini_inline_images(response, image_dir):
    """generate_content(IMAGE) 응답에서 이미지 파일 경로 추출."""
    paths = []
    if not response or not getattr(response, "candidates", None):
        return paths
    stamp = datetime.now().strftime("%H%M%S")
    for cand in response.candidates:
        content = getattr(cand, "content", None)
        if not content:
            continue
        for idx, part in enumerate(getattr(content, "parts", None) or []):
            if not getattr(part, "inline_data", None):
                continue
            fpath = os.path.join(image_dir, f"img_{stamp}_{len(paths)}.png")
            try:
                if hasattr(part, "as_image"):
                    part.as_image().save(fpath)
                else:
                    _pil_image().open(io.BytesIO(part.inline_data.data)).save(fpath)
                if os.path.getsize(fpath) > 1024:
                    paths.append(fpath)
            except Exception:
                continue
    return paths


async def _generate_images_gemini_flash(config, prompt, log_func, image_dir):
    """Gemini 네이티브 이미지 모델(gemini-2.5-flash-image 등). API Key."""
    if not _lazy_genai():
        return []
    api_key = (config.get("vertex_api_key") or config.get("gemini_key") or "").strip()
    if not api_key:
        return []
    models = ("gemini-2.5-flash-image", "gemini-3.1-flash-image-preview")
    client = _GenAIClient(api_key=api_key)
    for model_name in models:
        try:
            log_func(f"         🎨 Gemini 이미지 생성 시도... ({model_name})")
            res = await asyncio.to_thread(
                client.models.generate_content,
                model=model_name,
                contents=prompt,
                config=_genai_types.GenerateContentConfig(response_modalities=["IMAGE"]),
            )
            paths = _save_gemini_inline_images(res, image_dir)
            if paths:
                log_func(f"         ✅ AI 이미지 {len(paths)}개 생성 완료 (Gemini / {model_name})")
                return paths
        except Exception as e:
            log_func(f"         ⚠️ Gemini 이미지 ({model_name}) 실패: {str(e)[:100]}")
    return []


async def _generate_images_genai(config, prompt, log_func, image_dir):
    """Gen AI: Gemini 이미지 → Imagen 순으로 시도."""
    paths = await _generate_images_gemini_flash(config, prompt, log_func, image_dir)
    if paths:
        return paths
    if not _lazy_genai():
        return []
    api_key = (config.get("vertex_api_key") or config.get("gemini_key") or "").strip()
    if not api_key:
        return []
    imagen_models = ("imagen-4.0-generate-001", "imagen-3.0-generate-002")
    client = _GenAIClient(api_key=api_key, http_options={"api_version": "v1beta"})
    for model_name in imagen_models:
        try:
            log_func(f"         🎨 Imagen 이미지 생성 시도... ({model_name})")
            res = await asyncio.to_thread(
                client.models.generate_images,
                model=model_name,
                prompt=prompt,
                config=_genai_types.GenerateImagesConfig(number_of_images=1),
            )
            if res and res.generated_images:
                out = []
                for idx, img in enumerate(res.generated_images):
                    fpath = os.path.join(image_dir, f"img_{datetime.now().strftime('%H%M%S')}_{idx}.png")
                    if hasattr(img, "image"):
                        img.image.save(fpath)
                    else:
                        pil_img = _pil_image().open(io.BytesIO(img.image_bytes))
                        pil_img.save(fpath)
                    out.append(fpath)
                log_func(f"         ✅ AI 이미지 {len(out)}개 생성 완료 (Imagen / {model_name})")
                return out
        except Exception as e:
            log_func(f"         ⚠️ Imagen ({model_name}) 실패: {str(e)[:100]}")
    return []


async def _generate_images_pollinations(prompt, log_func, image_dir):
    """API 키 없이 무료 이미지 생성 (Pollinations)."""
    import urllib.parse

    import requests

    short = re.sub(r"\s+", " ", (prompt or ""))[:480]
    url = (
        "https://image.pollinations.ai/prompt/"
        + urllib.parse.quote(short, safe="")
        + "?width=1024&height=576&nologo=true&enhance=false"
    )
    log_func("         🎨 무료 이미지 생성(Pollinations) 시도...")
    try:
        res = await asyncio.to_thread(requests.get, url, timeout=120)
        if res.status_code == 402:
            log_func("         ⚠️ Pollinations 무료 API 종료(402). Gen AI(Gemini) 또는 Vertex를 사용하세요.")
            return []
        if res.status_code != 200:
            body = (res.text or "")[:120]
            log_func(f"         ⚠️ Pollinations HTTP {res.status_code}: {body}")
            return []
        if res.content and len(res.content) > 1024 and res.headers.get("content-type", "").startswith("image"):
            fpath = os.path.join(image_dir, f"img_{datetime.now().strftime('%H%M%S')}_free.png")
            with open(fpath, "wb") as f:
                f.write(res.content)
            with _pil_image().open(fpath) as im:
                im.verify()
            log_func("         ✅ 무료 AI 이미지 1개 생성 완료 (Pollinations)")
            return [fpath]
        log_func("         ⚠️ Pollinations 응답이 이미지가 아닙니다.")
    except Exception as e:
        log_func(f"         ⚠️ Pollinations 실패: {str(e)[:80]}")
    return []


def _generate_images_pillow_sync(title, required_keyword, image_desc, image_dir):
    """네트워크 없이 로컬에서 대표 이미지 카드 생성."""
    from PIL import ImageDraw, ImageFont

    Image = _pil_image()
    width, height = 1024, 576
    palettes = [
        ((24, 48, 78), (52, 96, 140)),
        ((34, 40, 58), (88, 72, 120)),
        ((18, 52, 44), (46, 110, 92)),
    ]
    c1, c2 = random.choice(palettes)
    img = Image.new("RGB", (width, height), c1)
    draw = ImageDraw.Draw(img)
    for y in range(height):
        t = y / max(height - 1, 1)
        color = tuple(int(c1[i] * (1 - t) + c2[i] * t) for i in range(3))
        draw.line([(0, y), (width, y)], fill=color)

    headline = (title or required_keyword or "Blog Post").strip()[:36]
    sub = (image_desc or required_keyword or "").strip()[:60]
    if len(sub) > 60:
        sub = sub[:57] + "..."

    font_title = ImageFont.load_default()
    font_sub = ImageFont.load_default()
    for font_path in (
        "C:/Windows/Fonts/malgun.ttf",
        "C:/Windows/Fonts/malgunbd.ttf",
    ):
        if os.path.isfile(font_path):
            try:
                font_title = ImageFont.truetype(font_path, 42)
                font_sub = ImageFont.truetype(font_path, 22)
                break
            except Exception:
                pass

    draw.rectangle([(48, height - 200), (width - 48, height - 56)], fill=(15, 22, 35))
    draw.text((64, height - 185), headline, fill=(245, 248, 255), font=font_title)
    if sub:
        draw.text((64, height - 120), sub, fill=(200, 210, 225), font=font_sub)

    fpath = os.path.join(image_dir, f"img_{datetime.now().strftime('%H%M%S')}_local.png")
    img.save(fpath, format="PNG")
    return fpath


async def _generate_images_pillow(title, required_keyword, image_desc, log_func, image_dir):
    log_func("         🖼️ 로컬 플레이스홀더 이미지 생성(Pillow)...")
    try:
        fpath = await asyncio.to_thread(
            _generate_images_pillow_sync, title, required_keyword, image_desc, image_dir
        )
        log_func("         ✅ 로컬 이미지 1개 생성 완료 (Pillow)")
        return [fpath]
    except Exception as e:
        log_func(f"         ⚠️ Pillow 이미지 실패: {str(e)[:80]}")
        return []


async def _generate_images_for_prompt(config, prompt, log_func, image_dir, *, title=None, required_keyword=None, image_desc=None):
    """단일 프롬프트로 이미지 1장 생성."""
    provider = _normalize_image_provider(config)
    paths = []

    if provider in ("free", "pollinations"):
        paths = await _generate_images_pollinations(prompt, log_func, image_dir)
        if not paths and (config.get("gemini_key") or config.get("vertex_api_key")):
            log_func("         ↪ Pollinations 실패 → Gen AI(Gemini) 재시도...")
            paths = await _generate_images_genai(config, prompt, log_func, image_dir)

    elif provider == "pillow":
        paths = await _generate_images_pillow(title, required_keyword, image_desc, log_func, image_dir)

    elif provider == "vertex":
        paths = await _generate_images_vertex(config, prompt, log_func, image_dir)
        if not paths:
            log_func("         ↪ Vertex AI 이미지 실패 → 무료 이미지(Pollinations) 자동 백업 생성...")
            paths = await _generate_images_pollinations(prompt, log_func, image_dir)

    elif provider == "genai":
        paths = await _generate_images_genai(config, prompt, log_func, image_dir)
        if not paths:
            log_func("         ↪ Gen AI(Gemini) 이미지 실패 → 무료 이미지(Pollinations) 자동 백업 생성...")
            paths = await _generate_images_pollinations(prompt, log_func, image_dir)

    else:
        paths = await _generate_images_genai(config, prompt, log_func, image_dir)
        if not paths:
            paths = await _generate_images_vertex(config, prompt, log_func, image_dir)
        if not paths:
            paths = await _generate_images_pollinations(prompt, log_func, image_dir)

    # 모든 AI 방식 실패 시 최종 로컬 Pillow 플레이스홀더 대체 생성 (빈 글 방지)
    if not paths and provider != "pillow":
        log_func("         ↪ 최종 이미지 생성 실패 → 로컬 이미지(Pillow)로 대체 생성...")
        paths = await _generate_images_pillow(title, required_keyword, image_desc, log_func, image_dir)

    return paths


async def generate_images(config, required_keyword, extra_keyword, log_func, image_dir, title=None, image_desc=None):
    """AI로 이미지 2장 생성(본문 중간·끝). 키워드·개요에 맞는 서로 다른 장면."""
    post_type = (config.get("post_type") or "").strip()
    provider = _normalize_image_provider(config)
    image_count = max(1, min(int(config.get("article_image_count") or 2), 2))
    variants = (["mid", "end"] if image_count >= 2 else ["mid"])[:image_count]

    if provider == "pillow":
        log_func(f"         🎨 로컬 이미지 생성 ({image_count}장 목표)...")
        paths: list[str] = []
        for variant in variants:
            prompt = _build_image_prompt(
                required_keyword,
                extra_keyword,
                post_type,
                title=title,
                image_desc=image_desc,
                variant=variant,
            )
            got = await _generate_images_for_prompt(
                config,
                prompt,
                log_func,
                image_dir,
                title=title,
                required_keyword=required_keyword,
                image_desc=image_desc,
            )
            if got:
                paths.append(got[0])
        if not paths:
            log_func("         ⚠️ 로컬 이미지 생성에 실패했습니다.")
        elif len(paths) < image_count:
            log_func(f"         ✅ 로컬 이미지 {len(paths)}개 생성 (목표 {image_count}장)")
        else:
            log_func(f"         ✅ 로컬 이미지 {len(paths)}개 생성 완료")
        return paths

    log_func(f"         🎨 AI 이미지 {image_count}장 생성 (중간·끝, 키워드 맞춤)...")

    async def one(variant: str) -> list[str]:
        scene_note = "시공·작업 중 장면" if variant == "mid" else "완성 후 물방울·광택 결과"
        desc = f"{image_desc} | {scene_note}" if image_desc else scene_note
        prompt = _build_image_prompt(
            required_keyword,
            extra_keyword,
            post_type,
            title=title,
            image_desc=desc,
            variant=variant,
        )
        got = await _generate_images_for_prompt(config, prompt, log_func, image_dir)
        return got[:1] if got else []

    results = await asyncio.gather(*[one(v) for v in variants])
    paths = [p for batch in results for p in batch]

    if not paths:
        log_func("         ⚠️ AI 이미지 생성에 실패해, 이번 포스팅은 이미지 없이 진행합니다.")
        log_func("         💡 GUI에서 'Gen AI (Gemini 이미지)' 선택 + Gemini API 키 확인을 권장합니다.")
    elif len(paths) < image_count:
        log_func(f"         ✅ AI 이미지 {len(paths)}개 생성 (목표 {image_count}장)")
    else:
        log_func(f"         ✅ AI 이미지 {len(paths)}개 생성 완료 (중간·끝)")
    return paths
