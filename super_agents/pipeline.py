# -*- coding: utf-8 -*-
"""
Base44 Super Agents 워크플로 — 로컬 24/7 멀티 에이전트 파이프라인.

영상: https://youtu.be/Ovj5f0ajDww (WorldofAI — 24/7 Claude Agents)

에이전트 체인:
  1) Research  — 웹·네이버 검색 + Ollama 딥 리서치 (신뢰도 점수)
  2) Script    — 브리핑 → 영상/블로그 스크립트 (인트로·세그먼트·CTA)
  3) Report    — 스타일 HTML 리포트 (브라우저 인쇄 → PDF)
  4) Notify    — Gmail SMTP (선택, .env 설정 시)
"""

from __future__ import annotations

import asyncio
import json
import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from super_agents.notify import email_configured, send_briefing_email
from super_agents.report import save_html_report
from super_agents.web_research import gather_research_context

_ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = _ROOT / "data" / "super_agents" / "workflow.json"

LogFn = Callable[[str], None]


def _log_default(msg: str) -> None:
    print(msg, flush=True)


def _model() -> str:
    return (
        os.environ.get("SUPER_AGENT_MODEL", "").strip()
        or os.environ.get("BLOG_OLLAMA_MODEL", "").strip()
        or os.environ.get("CONTENT_FACTORY_MODEL", "").strip()
        or "gemma4:e2b"
    )


def default_workflow() -> dict[str, Any]:
    return {
        "id": "Ovj5f0ajDww",
        "title": "AI 뉴스 데일리 Super Agent",
        "source_video": "https://youtu.be/Ovj5f0ajDww",
        "schedule": {
            "enabled": False,
            "time_local": "09:00",
            "timezone": "Asia/Seoul",
        },
        "research_topics": [
            "AI agents open source 2026",
            "Claude Anthropic news",
            "AI benchmarks releases",
            "humanoid robotics AI",
        ],
        "objective": (
            "매일 AI 업계 뉴스를 조사하고, 신뢰도 점수와 출처를 포함한 브리핑을 작성한 뒤 "
            "영상·블로그용 스크립트로 변환한다."
        ),
        "agents": [
            {"id": "research", "label": "딥 리서치", "role": "웹 검색·신뢰도·출처"},
            {"id": "script", "label": "스크립트", "role": "인트로·세그먼트·CTA·아웃트로"},
            {"id": "report", "label": "리포트", "role": "HTML 브리핑 (PDF 인쇄용)"},
            {"id": "notify", "label": "Gmail", "role": "이메일 발송 (선택)"},
        ],
        "options": {
            "use_naver_search": True,
            "use_web_search": True,
            "send_email": False,
            "email_subject_prefix": "[Super Agent]",
        },
    }


def load_workflow(path: Path | None = None) -> dict[str, Any]:
    p = path or CONFIG_PATH
    if not p.is_file():
        p.parent.mkdir(parents=True, exist_ok=True)
        data = default_workflow()
        p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        return data
    return json.loads(p.read_text(encoding="utf-8"))


@dataclass
class SuperAgentResult:
    title: str = ""
    briefing: str = ""
    script: str = ""
    sources: list[str] = field(default_factory=list)
    html_path: str = ""
    emailed: bool = False
    run_dir: str = ""


async def _ollama_chat(prompt: str, log: LogFn, *, num_predict: int = 2800) -> str:
    from blog_content_gen import (
        _ollama_chat_once,
        _ollama_ping_with_retry,
        _ollama_read_timeout_for,
    )

    if not await _ollama_ping_with_retry(log, attempts=2):
        raise RuntimeError("Ollama가 실행 중이 아닙니다. `ollama serve` 후 다시 시도하세요.")
    model = _model()
    timeout = _ollama_read_timeout_for(num_predict)
    return await _ollama_chat_once(model, prompt, log, num_predict, timeout)


def _extract_sources(text: str) -> list[str]:
    urls = re.findall(r"https?://[^\s\]>\"']+", text)
    seen: set[str] = set()
    out: list[str] = []
    for u in urls:
        u = u.rstrip(".,)")
        if u not in seen:
            seen.add(u)
            out.append(u)
    return out


async def run_super_agent_workflow(
    *,
    workflow: dict[str, Any] | None = None,
    topics_override: list[str] | None = None,
    send_email: bool | None = None,
    log: LogFn | None = None,
) -> SuperAgentResult:
    log = log or _log_default
    wf = workflow or load_workflow()
    opts = wf.get("options") or {}
    topics = topics_override or list(wf.get("research_topics") or [])
    objective = (wf.get("objective") or "").strip()

    log("▶ Super Agent 워크플로 시작 (영상: Base44 Super Agents 로컬 구현)")
    log(f"   모델: {_model()}")

    # --- Agent 1: Research ---
    log("\n[1/4] Research Agent — 검색 컨텍스트 수집...")
    ctx = await gather_research_context(
        topics,
        use_naver=bool(opts.get("use_naver_search", True)),
        use_web=bool(opts.get("use_web_search", True)),
    )
    research_prompt = (
        f"목표: {objective}\n\n"
        f"조사 주제: {', '.join(topics)}\n\n"
        f"{ctx}\n\n"
        "위 자료를 바탕으로 오늘의 AI 뉴스 딥 리서치 브리핑을 한국어로 작성하라.\n"
        "각 스토리마다:\n"
        "- 제목\n"
        "- 2~3문장 요약\n"
        "- [신뢰도 X/10] 점수와 근거 한 줄\n"
        "- 출처 URL (가능하면)\n"
        "스토리 3~5개. 마크다운 ## 소제목 사용.\n"
    )
    log("   Ollama 딥 리서치 생성...")
    briefing = await _ollama_chat(research_prompt, log, num_predict=2400)
    sources = _extract_sources(briefing + "\n" + ctx)
    log(f"   브리핑 완료 ({len(briefing)}자, 출처 {len(sources)}건)")

    # --- Agent 2: Script ---
    log("\n[2/4] Script Agent — 스크립트 변환...")
    script_prompt = (
        f"아래 AI 뉴스 브리핑을 YouTube/블로그용 스크립트로 변환하라.\n\n"
        f"{briefing}\n\n"
        "포함 요소:\n"
        "- [INTRO] 15초 훅\n"
        "- [SEGMENTS] 스토리별 1~2분 분량 (3~5개)\n"
        "- [CTA] 구독·뉴스레터 유도\n"
        "- [OUTRO] 마무리\n"
        "한국어, 말하듯 자연스럽게.\n"
    )
    script = await _ollama_chat(script_prompt, log, num_predict=2600)
    log(f"   스크립트 완료 ({len(script)}자)")

    title_m = re.search(r"^##\s+(.+)$", briefing, re.M)
    title = (title_m.group(1).strip() if title_m else "") or f"AI Daily Briefing {datetime.now().strftime('%Y-%m-%d')}"

    # --- Agent 3: Report ---
    log("\n[3/4] Report Agent — HTML 리포트...")
    html_path = save_html_report(
        title=title,
        briefing_md=briefing,
        script_md=script,
        sources=sources,
        root=_ROOT,
    )
    log(f"   저장: {html_path}")

    run_dir = html_path.parent
    briefing_path = run_dir / f"{html_path.stem}_briefing.md"
    script_path = run_dir / f"{html_path.stem}_script.md"
    briefing_path.write_text(briefing, encoding="utf-8")
    script_path.write_text(script, encoding="utf-8")

    # --- Agent 4: Notify ---
    do_email = send_email if send_email is not None else bool(opts.get("send_email", False))
    emailed = False
    if do_email:
        log("\n[4/4] Notify Agent — Gmail 발송...")
        if email_configured():
            prefix = (opts.get("email_subject_prefix") or "[Super Agent]").strip()
            send_briefing_email(
                subject=f"{prefix} {title}",
                body_text=f"{briefing}\n\n---\n\n{script}",
                html_path=html_path,
            )
            emailed = True
            log("   이메일 발송 완료")
        else:
            log("   Gmail 미설정 — SUPER_AGENT_GMAIL_* 환경변수를 확인하세요.")
    else:
        log("\n[4/4] Notify Agent — 이메일 생략 (옵션 off)")

    log(f"\n✅ Super Agent 완료 → {html_path}")
    return SuperAgentResult(
        title=title,
        briefing=briefing,
        script=script,
        sources=sources,
        html_path=str(html_path),
        emailed=emailed,
        run_dir=str(run_dir),
    )


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(
        description="24/7 Super Agent 워크플로 (Base44 영상 로컬 구현)",
    )
    parser.add_argument(
        "command",
        nargs="?",
        default="run",
        choices=["run", "init", "status"],
        help="run=1회 실행, init=설정 생성, status=상태",
    )
    parser.add_argument(
        "--topic",
        action="append",
        dest="topics",
        help="리서치 주제 추가 (여러 번 가능)",
    )
    parser.add_argument("--email", action="store_true", help="Gmail 발송 강제")
    parser.add_argument("--no-email", action="store_true", help="Gmail 생략")
    args = parser.parse_args()

    if args.command == "init":
        wf = load_workflow()
        print(f"설정 저장: {CONFIG_PATH}")
        print(json.dumps(wf, ensure_ascii=False, indent=2))
        return 0

    if args.command == "status":
        wf = load_workflow()
        print(json.dumps({
            "config": str(CONFIG_PATH),
            "model": _model(),
            "email_configured": email_configured(),
            "schedule": wf.get("schedule"),
            "topics": wf.get("research_topics"),
        }, ensure_ascii=False, indent=2))
        return 0

    send = True if args.email else (False if args.no_email else None)
    result = asyncio.run(
        run_super_agent_workflow(
            topics_override=args.topics or None,
            send_email=send,
        )
    )
    print("\n--- 결과 ---")
    print(f"제목: {result.title}")
    print(f"리포트: {result.html_path}")
    print(f"이메일: {'발송됨' if result.emailed else '미발송'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
