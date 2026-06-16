# -*- coding: utf-8 -*-
"""네이버 블로그 글 1단계 진단 (naver-blog-refresh · 영상 2번 GEO 규칙)."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

FORBIDDEN_PHRASES = [
    "안녕하세요",
    "알아보겠습니다",
    "도움이 되었으면 합니다",
    "감사합니다",
]

DISCLOSURE_KEYWORDS = ["협찬", "체험", "내돈내산", "광고", "제공받", "원고료"]

EXPERIENCE_MARKERS = [
    r"직접",
    r"시공",
    r"현장",
    r"해봤",
    r"써봤",
    r"Before",
    r"After",
    r"전후",
    r"\d+\s*(분|시간|일|주|개월|㎡|m2|리터|L|원)",
]


def _read_input(path: str | None) -> str:
    if path and path != "-":
        return Path(path).read_text(encoding="utf-8")
    return sys.stdin.read()


def _count_h2(text: str) -> int:
    return len(re.findall(r"^##\s+", text, re.MULTILINE))


def _has_question_end(text: str) -> bool:
    tail = text.strip()[-280:]
    return "?" in tail or "？" in tail


def _experience_score(text: str) -> int:
    return sum(1 for p in EXPERIENCE_MARKERS if re.search(p, text, re.IGNORECASE))


def diagnose(text: str) -> list[dict[str, str]]:
    body = text.strip()
    chars = len(body)
    h2 = _count_h2(body)
    exp = _experience_score(body)
    has_disclosure = any(k in body[:400] for k in DISCLOSURE_KEYWORDS)
    forbidden_hit = [p for p in FORBIDDEN_PHRASES if p in body]
    has_images_marker = "[IMAGE]" in body or "![ " in body

    rows: list[dict[str, str]] = []

    def row(item: str, status: str, reason: str) -> None:
        rows.append({"item": item, "status": status, "reason": reason})

    if exp >= 2:
        row("직접 경험", "통과", f"경험 신호 {exp}건")
    elif exp == 1:
        row("직접 경험", "부족", "경험 신호 1건 — 2문장 이상 권장")
    else:
        row("직접 경험", "부족", "시공·수치·전후 일화 없음")

    row("일관 주제", "해당없음", "자동 판별 불가 — 글 유형 수동 확인")

    if has_disclosure or "협찬" not in body and "체험" not in body:
        if has_disclosure:
            row("진정성", "통과", "상단 고지 키워드 있음")
        else:
            row("진정성", "해당없음", "상업 고지 필요 시 맨 앞 한 줄 추가")

    if h2 >= 4:
        row("구조", "통과", f"## 소제목 {h2}개")
    elif h2 >= 1:
        row("구조", "부족", f"## {h2}개 — 4~6개 권장")
    else:
        row("구조", "부족", "## 소제목 없음 — AI 브리핑 인용에 불리")

    if re.search(r"202[4-6]|올해|최근|이번\s*(달|주|장마)", body):
        row("최신성", "통과", "구체 시점 언급")
    else:
        row("최신성", "부족", "2025~2026 또는 '최근 시공' 등 시점 추가")

    if has_images_marker:
        row("이미지", "해당없음", "[IMAGE] 마커 있음 — 본문·표에도 텍스트 서술 확인")
    else:
        row("이미지", "해당없음", "텍스트만 제공")

    if forbidden_hit:
        row("금지", "부족", "금지어: " + ", ".join(forbidden_hit))
    else:
        row("금지", "통과", "상투 인사·맺음말 없음")

    if chars >= 1500:
        row("분량", "통과", f"{chars}자")
    else:
        row("분량", "부족", f"{chars}자 — 최소 1,500자 권장")

    if _has_question_end(body):
        row("마무리 질문", "통과", "끝부분에 독자 질문")
    else:
        row("마무리 질문", "부족", "마지막 280자 안에 ? 질문 1개")

    return rows


def format_report(rows: list[dict[str, str]]) -> str:
    lines = [
        "# 네이버 블로그 진단 (1단계)",
        "",
        "| 항목 | 상태 | 근거 |",
        "|------|------|------|",
    ]
    critical: list[str] = []
    for r in rows:
        lines.append(f"| {r['item']} | {r['status']} | {r['reason']} |")
        if r["status"] == "부족" and len(critical) < 3:
            critical.append(f"- **{r['item']}**: {r['reason']}")

    lines.extend(["", "## 우선 수정 (치명 3건 이하)", ""])
    if critical:
        lines.extend(critical)
    else:
        lines.append("- (없음) 2단계 구조 재설계 진행 가능")

    fail_count = sum(1 for r in rows if r["status"] == "부족")
    if fail_count >= 4:
        lines.extend(["", "**권고**: 새 글 재발행 (제목·구조 전면 변경)"])
    elif fail_count >= 1:
        lines.extend(["", "**권고**: 기존 글 수정 또는 부분 재발행"])
    else:
        lines.extend(["", "**권고**: 윤문·사진만 보강 후 수정"])

    lines.extend(
        [
            "",
            "다음: `naver-blog-refresh` 스킬 2단계(구조 개요) → wiki/04_ai_briefing_geo.md",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description="네이버 블로그 글 1단계 진단")
    ap.add_argument("file", nargs="?", help="글 파일 경로 (없으면 stdin)")
    ap.add_argument("-o", "--output", help="결과 저장 경로")
    args = ap.parse_args()

    text = _read_input(args.file)
    if not text.strip():
        print("입력이 비었습니다.", file=sys.stderr)
        return 1

    report = format_report(diagnose(text))
    if args.output:
        Path(args.output).write_text(report, encoding="utf-8")
        print(f"저장: {args.output}")
    else:
        print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
