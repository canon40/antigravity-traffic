# -*- coding: utf-8 -*-
"""
콘텐츠 팩토리 파이프라인 (n8n + Gemma4 + FastAPI 워크플로 Python 구현).

1) 주제 입력 → 로컬 Gemma4 초안 블로그
2) HTML/MD 저장
3) 이미지 키워드 추출 → Unsplash 다운로드
4) 제휴 DB 매칭 → 상업용 2차 HTML
"""

from __future__ import annotations

import asyncio
import html
import os
import re
from dataclasses import dataclass, field
from typing import Any, Callable

from content_factory.affiliate_db import search_by_topic
from content_factory.naver_context import fetch_blog_snippets
from content_factory.storage import content_root, save_html, save_text
from content_factory.unsplash_client import download_and_save

LogFn = Callable[[str], None]


def _log_default(msg: str) -> None:
    print(msg, flush=True)


def _factory_model() -> str:
    return (
        os.environ.get("CONTENT_FACTORY_MODEL", "").strip()
        or os.environ.get("BLOG_OLLAMA_MODEL", "").strip()
        or "gemma4:e2b"
    )


def _persona() -> str:
    return os.environ.get(
        "CONTENT_FACTORY_PERSONA",
        "IT·가전 리뷰어. 실사용 경험과 스펙 비교를 중시하며 과장 없이 씀.",
    ).strip()


@dataclass
class FactoryResult:
    topic: str
    draft_path: str = ""
    commercial_path: str = ""
    image_paths: list[str] = field(default_factory=list)
    affiliate_products: list[dict[str, Any]] = field(default_factory=list)
    title: str = ""
    tags: str = ""


def _wrap_html(title: str, body: str, *, affiliate_block: str = "") -> str:
    safe_title = html.escape(title)
    parts = [f"<h1>{safe_title}</h1>"]
    for block in re.split(r"\n\s*\n", body.strip()):
        block = block.strip()
        if not block:
            continue
        if block.startswith("## "):
            parts.append(f"<h2>{html.escape(block[3:].strip())}</h2>")
        elif block.startswith("# "):
            parts.append(f"<h2>{html.escape(block[2:].strip())}</h2>")
        else:
            parts.append(f"<p>{html.escape(block).replace(chr(10), '<br/>')}</p>")
    if affiliate_block:
        parts.append(f"<section class='affiliate'>{affiliate_block}</section>")
    inner = "\n".join(parts)
    return (
        "<!DOCTYPE html><html lang='ko'><head><meta charset='utf-8'/>"
        f"<title>{safe_title}</title></head><body>{inner}</body></html>"
    )


def _parse_generation(text: str) -> tuple[str, str, str, str]:
    title = "제목 없음"
    body = text
    tags = ""
    image_kw = ""

    m = re.search(r"\[TITLE\](.*?)(?=\[OUTLINE\]|\[BODY\]|\[TAGS\]|\[IMAGE_KEYWORDS\]|$)", text, re.S | re.I)
    if m:
        title = m.group(1).strip().split("\n")[0].strip()
    m = re.search(r"\[BODY\](.*?)(?=\[TAGS\]|\[IMAGE_KEYWORDS\]|\[IMAGE_DESC\]|$)", text, re.S | re.I)
    if m:
        body = m.group(1).strip()
    else:
        # [OUTLINE]만 있고 [BODY]가 없을 때 OUTLINE 이후 본문 사용
        m2 = re.search(r"\[OUTLINE\](.*?)(?=\[TAGS\]|\[IMAGE_KEYWORDS\]|\[IMAGE_DESC\]|$)", text, re.S | re.I)
        if m2:
            body = m2.group(1).strip()
    body = re.sub(r"^\[OUTLINE\].*?(?=\n##|\n\[|$)", "", body, flags=re.S).strip()
    m = re.search(r"\[TAGS\](.*?)(?=\[IMAGE_KEYWORDS\]|$)", text, re.S | re.I)
    if m:
        tags = m.group(1).strip()
    m = re.search(r"\[IMAGE_KEYWORDS\](.*)", text, re.S | re.I)
    if m:
        image_kw = m.group(1).strip().split(",")[0].strip()

    return title, body, tags, image_kw or title


async def _generate_with_ollama(prompt: str, log: LogFn) -> str:
    from blog_content_gen import (
        _ollama_chat_once,
        _ollama_ping_with_retry,
        _ollama_read_timeout_for,
    )

    if not await _ollama_ping_with_retry(log, attempts=2):
        raise RuntimeError("Ollama가 실행 중이 아닙니다. ollama serve 후 다시 시도하세요.")
    model = _factory_model()
    num_predict = 2200
    timeout = _ollama_read_timeout_for(num_predict)
    return await _ollama_chat_once(model, prompt, log, num_predict, timeout)


async def run_content_factory(
    topic: str,
    *,
    use_naver_search: bool = True,
    use_unsplash: bool = True,
    max_images: int = 3,
    log: LogFn | None = None,
) -> FactoryResult:
    log = log or _log_default
    topic = (topic or "").strip()
    if not topic:
        raise ValueError("topic 필수")

    log(f"▶ 콘텐츠 팩토리 시작: {topic} (모델: {_factory_model()})")

    naver_ctx = ""
    if use_naver_search:
        log("   네이버 블로그 검색 컨텍스트 수집...")
        naver_ctx = await fetch_blog_snippets(topic)

    draft_prompt = (
        f"페르소나: {_persona()}\n"
        f"주제: {topic}\n\n"
        f"{naver_ctx}\n\n"
        "위 참고를 활용해 네이버 블로그용 글을 작성하라.\n"
        "출력 형식(태그 그대로):\n"
        "[TITLE] 15자 내외 제목\n"
        "[BODY] ## 소제목 포함 본문 800자 이상. 직접 경험 1문장 이상.\n"
        "[TAGS] 해시태그 10개, 쉼표 구분\n"
        "[IMAGE_KEYWORDS] Unsplash 검색용 영어 키워드 1개\n"
    )
    log("   1차 초안 생성 (로컬 Gemma4)...")
    raw = await _generate_with_ollama(draft_prompt, log)
    title, body, tags, image_query = _parse_generation(raw)
    log(f"   초안 완료: {title}")

    draft_html = _wrap_html(title, body)
    draft_path = save_html(topic, draft_html, suffix="draft")
    save_text(topic, f"# {title}\n\n{body}\n\n태그: {tags}", suffix="draft")
    log(f"   저장: {draft_path}")

    image_paths: list[str] = []
    if use_unsplash:
        q = image_query or topic
        log(f"   이미지 검색: {q}")
        try:
            image_paths = await download_and_save(q, max_images=max_images)
            if image_paths:
                log(f"   이미지 {len(image_paths)}장 저장")
            else:
                log("   Unsplash 키 없음 또는 결과 없음 — 이미지 단계 생략")
        except Exception as e:
            log(f"   이미지 단계 오류: {e}")

    products = search_by_topic(topic, limit=3)
    affiliate_html = ""
    if products:
        log(f"   제휴 상품 {len(products)}건 매칭")
        blocks = []
        for p in products:
            link = p.get("link") or ""
            name = html.escape(str(p.get("name") or ""))
            if p.get("blog_html"):
                blocks.append(str(p["blog_html"]))
            elif link:
                blocks.append(f'<p><a href="{html.escape(link)}" rel="nofollow sponsored">{name}</a></p>')
        affiliate_html = "\n".join(blocks)
    else:
        log("   제휴 DB 매칭 없음 — 상업용 링크 없이 2차 생성")

    commercial_prompt = (
        f"페르소나: {_persona()}\n"
        f"주제: {topic}\n"
        f"초안 제목: {title}\n"
        f"초안 본문:\n{body}\n\n"
        f"제휴 상품 HTML 블록:\n{affiliate_html or '(없음)'}\n\n"
        f"{naver_ctx}\n\n"
        "초안을 바탕으로 제휴 링크가 자연스럽게 들어간 상업용 블로그 글을 작성하라.\n"
        "링크 HTML은 본문 중간·하단에 그대로 삽입.\n"
        "출력 형식:\n"
        "[TITLE] 제목\n"
        "[BODY] 본문 (HTML a 태그 포함 가능)\n"
        "[TAGS] 태그\n"
    )
    log("   2차 상업용 콘텐츠 생성...")
    raw2 = await _generate_with_ollama(commercial_prompt, log)
    c_title, c_body, c_tags, _ = _parse_generation(raw2)
    commercial_path = save_html(topic, _wrap_html(c_title, c_body, affiliate_block=affiliate_html), suffix="commercial")
    log(f"   상업용 저장: {commercial_path}")
    log(f"완료. 출력 폴더: {content_root()}")

    return FactoryResult(
        topic=topic,
        draft_path=str(draft_path),
        commercial_path=str(commercial_path),
        image_paths=image_paths,
        affiliate_products=products,
        title=c_title,
        tags=c_tags,
    )


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="로컬 AI 콘텐츠 팩토리 (Gemma4 + n8n 대체 파이프라인)")
    parser.add_argument("topic", help="블로그 주제 (예: 선풍기 추천)")
    parser.add_argument("--no-naver", action="store_true", help="네이버 검색 컨텍스트 생략")
    parser.add_argument("--no-images", action="store_true", help="Unsplash 이미지 생략")
    args = parser.parse_args()
    result = asyncio.run(
        run_content_factory(
            args.topic,
            use_naver_search=not args.no_naver,
            use_unsplash=not args.no_images,
        )
    )
    print("\n--- 결과 ---")
    print(f"제목: {result.title}")
    print(f"초안: {result.draft_path}")
    print(f"상업용: {result.commercial_path}")
    if result.image_paths:
        print("이미지:", ", ".join(result.image_paths))


if __name__ == "__main__":
    main()
