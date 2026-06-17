# -*- coding: utf-8 -*-
"""
Codex / JARVIS / 터미널에서 서랍 워커만 단독 실행.

  python drawer/cli.py list
  python drawer/cli.py route --keyword "욕실코팅"
  python drawer/cli.py invoke wiki --post-type "자동차 정보"
  python drawer/cli.py invoke store --category "생활" --concept "리빙코트"
"""

from __future__ import annotations

import argparse
import json
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)


def cmd_list(_args):
    from drawer.registry import agents_config, loaded_modules
    from blog_constants import DRAWER_MODULES

    cfg = agents_config()
    print(json.dumps({
        "modules": list(DRAWER_MODULES),
        "boot_sequence": cfg.get("boot_sequence", []),
        "agent_pipeline": cfg.get("agent_pipeline", []),
        "dev_pipeline": cfg.get("dev_pipeline", {}),
        "workers": cfg.get("workers", {}),
        "text_chain": cfg.get("text_chain", []),
        "image_chain": cfg.get("image_chain", []),
        "jarvis_model_routing": cfg.get("jarvis_model_routing", {}),
        "loaded": loaded_modules(),
    }, ensure_ascii=False, indent=2))


def cmd_pipeline(args):
    """에이전트 협업 순서만 출력 (Codex용)."""
    from drawer.registry import agents_config

    cfg = agents_config()
    mode = getattr(args, "mode", "blog") or "blog"
    lines = ["# boot", *[f"{s.get('order')}. {s.get('id')}: {s.get('command')}" for s in cfg.get("boot_sequence", [])]]
    if mode == "dev":
        lines.append("# dev (프로그램 개발)")
        for a in (cfg.get("dev_pipeline") or {}).get("phases") or []:
            llm = "llm" if a.get("llm") else "no-llm"
            agents = ",".join(a.get("agents") or [a.get("id", "")])
            lines.append(f"Phase {a.get('phase')}. {a.get('id')} - {a.get('label')} [{llm}] -> {agents}")
    else:
        lines.append("# agents (블로그·콘텐츠)")
        for a in cfg.get("agent_pipeline", []):
            lines.append(f"{a.get('order')}. {a.get('id')} - {a.get('label')} | llm={a.get('llm', False)}")
    out = "\n".join(lines)
    if sys.platform == "win32":
        enc = sys.stdout.encoding or "utf-8"
        try:
            print(out.encode(enc, errors="replace").decode(enc, errors="replace"))
        except Exception:
            print(out)
    else:
        print(out)


def cmd_route(args):
    from drawer.router import summarize_route

    payload = {}
    if args.keyword:
        payload["keyword"] = args.keyword
    if args.module:
        payload["module"] = args.module
    if args.text:
        payload["text"] = args.text
    if getattr(args, "task", None):
        payload["task"] = args.task
    print(json.dumps(summarize_route(payload), ensure_ascii=False, indent=2))


def cmd_dev_plan(args):
    from drawer.dev_pipeline import format_dev_plan_text, probe_installed_agents, summarize_dev_plan

    if getattr(args, "probes_only", False):
        print(json.dumps(probe_installed_agents(), ensure_ascii=False, indent=2))
        return 0
    task = " ".join(
        x for x in (getattr(args, "task", "") or getattr(args, "text", "") or "") if x
    ).strip()
    plan = summarize_dev_plan(task)
    if args.json:
        print(json.dumps(plan, ensure_ascii=False, indent=2))
    else:
        _print_safe(format_dev_plan_text(plan))
    return 0


def _print_safe(text: str) -> None:
    if sys.platform == "win32":
        enc = sys.stdout.encoding or "utf-8"
        try:
            print(text.encode(enc, errors="replace").decode(enc, errors="replace"), end="")
        except Exception:
            print(text, end="")
    else:
        print(text, end="")


def cmd_route_model(args):
    from drawer.model_router import summarize_model_route

    payload = {}
    if args.keyword:
        payload["keyword"] = args.keyword
    if args.text:
        payload["text"] = args.text
    if args.task:
        payload["task"] = args.task
    if args.module:
        payload["module"] = args.module
    print(json.dumps(summarize_model_route(payload), ensure_ascii=False, indent=2))


def cmd_invoke(args):
    module_id = args.module

    if module_id == "wiki":
        from drawer.wiki import load_guidelines_for_task, list_slices

        text = load_guidelines_for_task(
            args.post_type or "",
            user_master=args.master or "",
            extra=args.extra or "",
        )
        if args.json:
            print(json.dumps({"ok": True, "chars": len(text), "slices": list_slices()}, ensure_ascii=False))
        else:
            print(text)
        return 0

    if module_id == "store":
        import asyncio
        from store_pipeline import run_store_pipeline

        api_key = args.api_key or os.environ.get("GEMINI_API_KEY", "")
        if not api_key:
            print(json.dumps({"ok": False, "error": "Gemini API 키 필요 (--api-key 또는 GEMINI_API_KEY)"}))
            return 1

        def log(m):
            print(m, flush=True)

        result = asyncio.run(
            run_store_pipeline(
                args.concept or "",
                args.category or "생활",
                seed_keywords=[s.strip() for s in (args.seeds or "").split(",") if s.strip()] or None,
                crawl=not args.no_crawl,
                use_playwright=not args.no_playwright,
                api_key=api_key,
                log_fn=log,
            )
        )
        print(json.dumps({"ok": result.get("ok"), "tags": result.get("tags_for_blog", "")[:200]}, ensure_ascii=False))
        return 0 if result.get("ok") else 1

    if module_id == "blog":
        print(json.dumps({
            "ok": True,
            "message": "blog 워커는 GUI 또는 javis_bridge POST /api/javis/start 로 실행하세요.",
            "hint": "run_gui.bat 또는 payload module=blog",
        }, ensure_ascii=False))
        return 0

    print(json.dumps({"ok": False, "error": f"unknown module: {module_id}"}))
    return 1


def main(argv=None):
    p = argparse.ArgumentParser(description="canon4040 Autoblog Drawer CLI")
    sub = p.add_subparsers(dest="cmd")

    sub.add_parser("list", help="모듈·에이전트 체인 목록")
    pp = sub.add_parser("pipeline", help="부팅·에이전트 순서만 텍스트 출력")
    pp.add_argument("--mode", choices=["blog", "dev"], default="blog", help="blog=콘텐츠 파이프라인, dev=프로그램 개발")

    pd = sub.add_parser("dev-plan", help="프로그램 개발 에이전트 단계 (FABLE·OpenClaw·Hermes·Gemma4·Llama)")
    pd.add_argument("--task", "--text", dest="task", default="", help="개발 작업 설명")
    pd.add_argument("--json", action="store_true")
    pd.add_argument("--probes-only", action="store_true", help="설치된 에이전트만 JSON 출력")

    pr = sub.add_parser("route", help="의도 라우팅만 (LLM 없음)")
    pr.add_argument("--keyword", default="")
    pr.add_argument("--module", default="")
    pr.add_argument("--text", default="")
    pr.add_argument("--task", default="", help="orchestration|coding|content|image_generate 등")

    prm = sub.add_parser("route-model", help="JARVIS 작업 유형별 모델 우선순위 (LLM 없음)")
    prm.add_argument("--keyword", default="")
    prm.add_argument("--text", default="")
    prm.add_argument("--task", default="")
    prm.add_argument("--module", default="")

    pi = sub.add_parser("invoke", help="워커 단독 실행")
    pi.add_argument("module", choices=["blog", "store", "wiki", "verify", "neighbor"])
    pi.add_argument("--post-type", default="")
    pi.add_argument("--master", default="")
    pi.add_argument("--extra", default="")
    pi.add_argument("--category", default="")
    pi.add_argument("--concept", default="")
    pi.add_argument("--seeds", default="")
    pi.add_argument("--api-key", default="")
    pi.add_argument("--no-crawl", action="store_true")
    pi.add_argument("--no-playwright", action="store_true")
    pi.add_argument("--json", action="store_true")

    args = p.parse_args(argv)
    if args.cmd == "list":
        cmd_list(args)
        return 0
    if args.cmd == "pipeline":
        cmd_pipeline(args)
        return 0
    if args.cmd == "dev-plan":
        return cmd_dev_plan(args)
    if args.cmd == "route":
        cmd_route(args)
        return 0
    if args.cmd == "route-model":
        cmd_route_model(args)
        return 0
    if args.cmd == "invoke":
        return cmd_invoke(args)
    p.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
