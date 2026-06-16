# -*- coding: utf-8 -*-
"""CLI: python -m shorts_factory.build --product living --keywords "..." """

from __future__ import annotations

import argparse
import asyncio
import re
import sys
import webbrowser
from datetime import datetime
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from shorts_factory.generator import generate_shorts_plan
from shorts_factory.niche_templates import list_niches
from shorts_factory.render import write_outputs_async


def _slug(product_id: str, topic: str) -> str:
    base = re.sub(r"[^\w가-힣]+", "_", (topic or product_id).strip())[:40].strip("_")
    day = datetime.now().strftime("%Y%m%d")
    return f"{product_id}_{day}_{base or 'shorts'}"


def main() -> int:
    p = argparse.ArgumentParser(description="쇼츠 콘티·스토리보드 생성 (FLOW용)")
    p.add_argument("--product", "-p", default="living", choices=["auto", "bike", "living"])
    p.add_argument("--keywords", "-k", default="", help="쉼표 구분 키워드 (영어·한국어)")
    p.add_argument("--topic", "-t", default="", help="주제 (비우면 제품 라벨)")
    p.add_argument("--hook", default="", help="후킹 한 줄 (선택)")
    p.add_argument("--scenes", type=int, default=4)
    p.add_argument(
        "--niche",
        "-n",
        default="",
        help="AI 니치 템플릿 id (예: mega_structures, ai_documentary). --list-niches 로 목록",
    )
    p.add_argument("--list-niches", action="store_true", help="니치 id 목록 출력 후 종료")
    p.add_argument("--slug", default="", help="출력 폴더명 (기본 자동)")
    p.add_argument("--open", action="store_true", help="생성 후 flow_board.html 브라우저 오픈")
    p.add_argument("--no-images", action="store_true", help="콘티 이미지 생성 생략")
    args = p.parse_args()

    if args.list_niches:
        for n in list_niches():
            flag = "쇼핑" if n.get("shopping_adaptable") else "일반"
            print(f"{n.get('id')}\t{flag}\t{n.get('name_ko')}")
        return 0

    if not (args.keywords or "").strip():
        p.error("--keywords/-k 가 필요합니다 (--list-niches 제외)")

    async def _run() -> Path:
        plan = await generate_shorts_plan(
            product_id=args.product,
            keywords=args.keywords,
            topic=args.topic,
            hook=args.hook,
            scenes=args.scenes,
            niche_id=args.niche.strip() or None,
        )
        slug = args.slug or _slug(args.product, plan.get("video_title") or args.topic)
        return await write_outputs_async(plan, slug, use_images=not args.no_images)

    out = asyncio.run(_run())
    print(f"생성 완료: {out}")
    print(f"  - plan.json / conti.md / story.md / flow_board.html")
    if args.open:
        webbrowser.open((out / "flow_board.html").resolve().as_uri())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
