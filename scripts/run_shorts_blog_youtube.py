#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
숏폼 → YouTube → 블로그(영상 자동 첨부) → 트래픽 연동.

예:
  python scripts/run_shorts_blog_youtube.py "퍼마코트 자동차"
  python scripts/run_shorts_blog_youtube.py "퍼마코트 바이크" --video "D:\\@code\\ai factory\\퍼마코트_바이크_shorts.mp4"
  python scripts/run_shorts_blog_youtube.py "퍼마코트 자동차" --no-youtube --no-traffic
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env", override=True)

# JARVIS 본체(계정·콘텐츠) + anty traffic 패치 모듈 병합
from blog_pipeline_runner import bootstrap_jarvis_imports, resolve_jarvis_root

_jarvis = bootstrap_jarvis_imports()
_bundled = ROOT / "javis"
if _bundled.is_dir() and str(_bundled) not in sys.path:
    sys.path.insert(0, str(_bundled))


def _log(msg: str) -> None:
    try:
        print(msg, flush=True)
    except UnicodeEncodeError:
        print(msg.encode("cp949", errors="replace").decode("cp949"), flush=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="숏폼·YouTube·블로그·트래픽 일괄")
    parser.add_argument("keyword", help="키워드 (예: 퍼마코트 자동차)")
    parser.add_argument("--video", help="기존 MP4 경로 (없으면 AI Factory에서 찾거나 생성)")
    parser.add_argument("--duration", type=int, default=30, help="숏폼 생성 길이(초)")
    parser.add_argument("--test", action="store_true", help="Veo 테스트 모드(0원)")
    parser.add_argument("--no-create", action="store_true", help="영상 없으면 생성하지 않음")
    parser.add_argument("--no-youtube", action="store_true", help="YouTube 업로드 생략")
    parser.add_argument("--no-blog", action="store_true", help="블로그 발행 생략")
    parser.add_argument("--no-traffic", action="store_true", help="트래픽 생략")
    parser.add_argument("--dry-run", action="store_true", help="숏폼·YouTube만, 블로그 미발행")
    args = parser.parse_args()

    from integrations.content_publish_pipeline import run_content_publish_pipeline

    report = run_content_publish_pipeline(
        args.keyword,
        create_video=not args.no_create,
        upload_youtube=not args.no_youtube,
        publish_blog=not args.no_blog and not args.dry_run,
        trigger_traffic=not args.no_traffic and not args.dry_run,
        video_path=args.video or "",
        duration=args.duration,
        test_mode=args.test,
        on_status=_log,
    )

    _log("")
    _log("=" * 58)
    _log(f"키워드: {report.get('keyword')}")
    _log(f"영상: {report.get('video_path') or '—'}")
    _log(f"YouTube: {report.get('youtube_url') or '—'}")
    _log(f"결과: {'성공' if report.get('ok') else '일부 실패'}")
    _log("=" * 58)
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
