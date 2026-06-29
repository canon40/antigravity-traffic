#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
[퍼마코트 SEO 전용] 네이버 블로그 상위 노출 최적화 포스팅 초안 생성기.
- 자동차 / 바이크 분리형 메타 데이터 매핑
- 스마트스토어 상품 ID 전용 링크 연동
- 검색 로봇이 선호하는 정보성 글 구성 및 태그 세팅
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

ENV_PATH = ROOT / ".env"
load_dotenv(ENV_PATH, override=True)

LISTINGS_PATH = ROOT / "data" / "smartstore_listings.json"
FEATURES_PATH = ROOT / "data" / "permacoat_blog_products.json"
OUTPUT_DIR = ROOT / "generated_content"

_LEGACY_KO = ("리빙코트", "듀라코트", "리빙코팅제", "파마코트", "듀라코트 리빙코트")
_CAR_BAN = ("오토바이", "바이크", "모터사이클", "헬멧", "머플러")
_BIKE_BAN = ("승용차", "자동차", "세단", "SUV", "차량용")


def _log(msg: str) -> None:
    try:
        print(msg, flush=True)
    except UnicodeEncodeError:
        print(msg.encode("cp949", errors="replace").decode("cp949"), flush=True)


def load_product_database() -> dict[str, dict]:
    """smartstore_listings SEO + permacoat_blog_products features 병합."""
    features_doc = {}
    if FEATURES_PATH.is_file():
        features_doc = json.loads(FEATURES_PATH.read_text(encoding="utf-8"))

    listings_doc = {}
    if LISTINGS_PATH.is_file():
        listings_doc = json.loads(LISTINGS_PATH.read_text(encoding="utf-8"))

    db: dict[str, dict] = {}
    for row in listings_doc.get("listings") or []:
        if row.get("category") not in ("car", "bike"):
            continue
        pid = str(row.get("seller_id") or "").strip()
        if not pid:
            continue
        seo = row.get("seo") or {}
        extra = features_doc.get(pid) or {}
        db[pid] = {
            "type": row.get("category") or extra.get("type") or "car",
            "title_keywords": seo.get("page_title") or row.get("title") or "",
            "meta_desc": seo.get("meta_description") or "",
            "tags": list(seo.get("tags") or []),
            "features": list(extra.get("features") or []),
            "listing_title": row.get("title") or "",
            "product_line": row.get("product_line") or "",
        }
    return db


PRODUCT_DATABASE = load_product_database()


def _sanitize_blog_body(text: str, *, is_bike: bool, display: str) -> str:
    out = text or ""
    for term in _LEGACY_KO:
        out = out.replace(term, display)
    banned = _BIKE_BAN if is_bike else _CAR_BAN
    for term in banned:
        out = re.sub(re.escape(term), "", out)
    return re.sub(r"\n{3,}", "\n\n", out).strip()


def call_gemini_blog_content(keyword: str, product_info: dict, is_bike: bool) -> str:
    """Gemini — 네이버 SEO 정보성 블로그 본문."""
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key or api_key.lower().startswith("your_"):
        return "[오류: .env에 GEMINI_API_KEY가 필요합니다.]"

    try:
        from google import genai
    except ImportError:
        return "[오류: pip install google-genai]"

    client = genai.Client(api_key=api_key)
    product_title = product_info["title_keywords"]
    features_list = "\n - ".join(product_info.get("features") or [])
    meta_hint = product_info.get("meta_desc") or ""

    if is_bike:
        category_note = (
            "주의: 반드시 바이크·오토바이·헬멧 전용 가이드로 작성. "
            "'승용차', '자동차', '세단', '차량용' 표현 금지."
        )
        display = "퍼마코트 바이크"
    else:
        category_note = (
            "주의: 반드시 자동차·세단·SUV 차량 관리 가이드로 작성. "
            "'오토바이', '바이크', '모터사이클', '헬멧' 금지."
        )
        display = "퍼마코트 자동차"

    prompt = f"""당신은 네이버 파워 블로거이자 디지털 마케팅 전문가입니다.
검색 노출에 유리한 정보성 블로그 리뷰 포스팅을 작성하세요.

[제품 정보]
- 공식 키워드: {product_title}
- 강점:
 - {features_list}
- 메타 힌트: {meta_hint}

{category_note}

[구조]
1. 인트로: 계절·날씨 맥락에서 관리 필요성 (기스·변색·오염)
2. 왜 퍼마코트인가 — 차별점
3. 발수·비딩·광택 효과 (숏폼 영상과 연계된다고 언급)
4. 초보자 셀프 시공 5단계 (세차→건조→도포→버핑→경화)
5. 추천 대상·마무리

[규칙]
- 1,500자 내외, 경어체, 정보 전달 중심
- 구형명 '리빙코트', '듀라코트' 절대 금지
- 마크다운 제목(##) 사용 가능
"""

    try:
        model = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
        response = client.models.generate_content(model=model, contents=prompt)
        raw = (getattr(response, "text", None) or "").strip()
        return _sanitize_blog_body(raw, is_bike=is_bike, display=display) if raw else ""
    except Exception as exc:
        return f"[콘텐츠 생성 지연: {exc}]"


def generate_blog_draft(
    product_id: str,
    *,
    store_name: str | None = None,
    video_path: str | None = None,
) -> str:
    """상품 ID → 네이버 블로그 붙여넣기용 초안 TXT."""
    from store_link_builder import build_store_url, get_store_slug

    pid = str(product_id).strip()
    db = load_product_database()
    if pid not in db:
        _log(f"❌ 등록되지 않은 퍼마코트 상품 ID: {pid}")
        _log("자동차: 12577296206, 12578368490, 12655362429, 12752175192, 12752188305, 12752196803")
        _log("바이크: 12655391634, 12751444412, 12751477991, 12751493962")
        return ""

    info = db[pid]
    is_bike = info["type"] == "bike"
    slug = (store_name or get_store_slug()).strip()
    store_link = build_store_url(pid, store_slug=slug)

    blog_title = f"[셀프 가이드] {info['title_keywords']}"
    _log("✍️  네이버 SEO 키워드 조합에 맞춰 포스팅 작성 중…")
    blog_body = call_gemini_blog_content(info["title_keywords"], info, is_bike)

    video_hint = ""
    if video_path:
        video_hint = f"\n- 첨부 영상 파일: {Path(video_path).resolve()}\n"
    else:
        video_hint = "\n- 제작 완료된 *_shorts.mp4 파일을 에디터 상단에 드래그하세요.\n"

    title_kw_part = info["title_keywords"].split("|")[-1].strip() if "|" in info["title_keywords"] else info["title_keywords"]
    hashtag_line = " ".join(f"#{t}" for t in (info.get("tags") or [])[:15])

    draft = f"""======================================================================
[네이버 블로그 상위 노출 · 스마트스토어 연동 포스팅 초안]
상품 ID: {pid} · {'오토바이 전용' if is_bike else '차량용 유리막'}
======================================================================

📌 [권장 제목]
{blog_title}

----------------------------------------------------------------------
🎥 [동영상 업로드]
{video_hint}- 동영상 제목 키워드: "{title_kw_part}"
----------------------------------------------------------------------

📝 [본문]

{blog_body}


---

💡 생생한 발수·광택 효과는 첨부 숏폼 영상에서 확인하세요.
셀프 관리로 샵급 퀄리티가 필요하다면 아래 공식 스토어를 이용해 주세요.

👇 제품 구매 · 상세정보 👇
{store_link}

----------------------------------------------------------------------
🏷️ [태그 — 블로그 태그란에 붙여넣기]
{hashtag_line}

📋 [메타 설명 참고 — 블로그 발행 설정]
{info.get('meta_desc') or ''}
======================================================================"""

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out_name = f"blog_seo_{pid}.txt"
    out_path = OUTPUT_DIR / out_name
    out_path.write_text(draft, encoding="utf-8")

    legacy_path = ROOT / f"blog_draft_{pid}.txt"
    legacy_path.write_text(draft, encoding="utf-8")

    _log(f"✅ 블로그 초안 저장: {out_path}")
    _log(f"   (복사본: {legacy_path.name})")
    _log(f"👉 스마트스토어: {store_link}")
    return draft


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="퍼마코트 SEO 블로그 초안 (상품 ID)")
    parser.add_argument("product_id", nargs="?", help="스마트스토어 판매자센터 ID (예: 12577296206)")
    parser.add_argument("--store", default=None, help="스토어 slug (기본: nanumlab)")
    parser.add_argument("--video", help="숏폼 MP4 경로 (안내 문구에 포함)")
    parser.add_argument("--list", action="store_true", help="등록된 퍼마코트 ID 목록")
    args = parser.parse_args(argv)

    if args.list:
        db = load_product_database()
        for pid, info in sorted(db.items()):
            kind = "🚗" if info["type"] == "car" else "🏍️"
            _log(f"{kind} {pid} — {info.get('listing_title')}")
        return 0

    if not args.product_id:
        parser.error("product_id 가 필요합니다. --list 로 ID 목록을 확인하세요.")

    try:
        generate_blog_draft(args.product_id, store_name=args.store, video_path=args.video)
        return 0
    except Exception as exc:
        _log(f"❌ 오류: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
