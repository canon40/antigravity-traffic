# -*- coding: utf-8 -*-
"""
프로그램·기능 개발 시 설치된 에이전트 사용 순서.

FABLE → OPENCLAW/Hermes → Codex(구현) → Gemma4(문서·UI) → Llama(로컬 보조) → 검증
동시에 여러 LLM 프로세스를 띄우지 않는다 (agents.json principles).
"""

from __future__ import annotations

import json
import os
import shutil
import urllib.error
import urllib.request
from functools import lru_cache
from typing import Any

from drawer.model_router import match_installed_ollama
from drawer.registry import agents_config


def _ollama_tags() -> set[str]:
    try:
        req = urllib.request.Request("http://127.0.0.1:11434/api/tags", method="GET")
        with urllib.request.urlopen(req, timeout=3) as resp:
            data = json.loads(resp.read().decode())
        return {m.get("name", "") for m in (data.get("models") or []) if m.get("name")}
    except Exception:
        return set()


def _openclaw_ok() -> bool:
    if not shutil.which("openclaw"):
        return False
    try:
        req = urllib.request.Request("http://127.0.0.1:18789/", method="GET")
        with urllib.request.urlopen(req, timeout=3) as resp:
            return 200 <= resp.status < 500
    except urllib.error.URLError:
        return False


def _fable_ok() -> bool:
    model = (
        os.environ.get("BLOG_CLAUDE_MODEL")
        or os.environ.get("JARVIS_CLAUDE_MODEL")
        or "claude-fable-5"
    ).strip()
    if "fable" in model.lower():
        return True
    javis = os.environ.get("JARVIS_ROOT", r"D:\@code\javis")
    return os.path.isfile(os.path.join(javis, "integrations", "claude_fable_bridge.py"))


@lru_cache(maxsize=1)
def dev_pipeline_config() -> dict[str, Any]:
    return agents_config().get("dev_pipeline") or {}


def probe_installed_agents() -> dict[str, dict[str, Any]]:
    """설치·가동 여부만 조사 (LLM 호출 없음)."""
    installed_ollama = _ollama_tags()
    profiles = (agents_config().get("jarvis_model_routing") or {}).get("model_profiles") or {}

    def _ollama_hit(profile_id: str) -> tuple[bool, str]:
        prof = profiles.get(profile_id) or {}
        cands = prof.get("ollama_models") or []
        matched = match_installed_ollama(installed_ollama, cands)
        if matched:
            return True, matched[0]
        return False, ""

    hermes_ok, hermes_model = _ollama_hit("hermes")
    gemma4_ok, gemma4_model = _ollama_hit("gemma4")
    llama_ok, llama_model = _ollama_hit("llama")
    deepseek_ok, deepseek_model = _ollama_hit("deepseek")

    return {
        "fable": {
            "installed": _fable_ok(),
            "label": "Claude Fable 5",
            "backend": "anthropic",
            "command": "run_fable5.bat apply",
            "model": os.environ.get("BLOG_CLAUDE_MODEL", "claude-fable-5"),
        },
        "openclaw": {
            "installed": _openclaw_ok(),
            "label": "OpenClaw Gateway",
            "backend": "openclaw",
            "command": "run_openclaw.bat",
            "dashboard": "http://127.0.0.1:18789/",
        },
        "hermes": {
            "installed": hermes_ok,
            "label": "Hermes 3",
            "backend": "ollama",
            "command": f"ollama run {hermes_model}" if hermes_model else "ollama pull hermes3:latest",
            "model": hermes_model,
        },
        "codex": {
            "installed": True,
            "label": "Codex / Cursor",
            "backend": "cursor",
            "external": True,
            "command": "drawer/cli.py dev-plan · Cursor Agent",
        },
        "gemma4": {
            "installed": gemma4_ok,
            "label": "Gemma 4",
            "backend": "ollama",
            "command": f"ollama run {gemma4_model}" if gemma4_model else "ollama pull gemma4:latest",
            "model": gemma4_model,
        },
        "llama": {
            "installed": llama_ok,
            "label": "Llama 3",
            "backend": "ollama",
            "command": f"ollama run {llama_model}" if llama_model else "ollama pull llama3:latest",
            "model": llama_model,
        },
        "deepseek": {
            "installed": deepseek_ok,
            "label": "DeepSeek R1",
            "backend": "ollama",
            "model": deepseek_model,
        },
        "ollama": {
            "installed": bool(installed_ollama),
            "label": "Ollama",
            "count": len(installed_ollama),
            "models": sorted(installed_ollama)[:12],
        },
    }


def _phase_list() -> list[dict[str, Any]]:
    phases = dev_pipeline_config().get("phases") or []
    if phases:
        return sorted(phases, key=lambda p: p.get("phase", p.get("order", 0)))
    return _default_phases()


def _default_phases() -> list[dict[str, Any]]:
    return [
        {"phase": 0, "id": "precheck", "label": "환경 점검", "llm": False, "agents": ["programs_check"]},
        {"phase": 1, "id": "hermes", "label": "요구사항·업무 분해", "llm": True, "agents": ["openclaw", "hermes"]},
        {"phase": 2, "id": "fable", "label": "LOOP 설계·감독", "llm": True, "agents": ["fable"], "heavy": True},
        {"phase": 3, "id": "codex", "label": "코드 구현", "llm": True, "agents": ["codex"], "external": True},
        {"phase": 4, "id": "gemma4", "label": "UI문구·README·주석", "llm": True, "agents": ["gemma4", "hermes"]},
        {"phase": 5, "id": "llama", "label": "로컬 스크립트·보조", "llm": True, "agents": ["llama", "deepseek"], "optional": True},
        {"phase": 6, "id": "openclaw_ops", "label": "백그라운드·Cron·보고", "llm": False, "agents": ["openclaw"]},
        {"phase": 7, "id": "verify", "label": "검증·점검", "llm": False, "agents": ["programs_check", "fable"]},
    ]


def build_dev_plan(task: str = "") -> dict[str, Any]:
    """개발 작업용 단계별 에이전트 계획 (설치된 것만 활성)."""
    probes = probe_installed_agents()
    steps: list[dict[str, Any]] = []
    skipped: list[str] = []

    for ph in _phase_list():
        agent_ids = list(ph.get("agents") or [ph.get("id")] or [])
        chosen: dict[str, Any] | None = None
        for aid in agent_ids:
            if aid in ("programs_check", "verify"):
                chosen = {"agent_id": aid, "label": "programs_check.py", "installed": True}
                break
            meta = probes.get(aid)
            if not meta:
                continue
            if meta.get("installed"):
                chosen = {"agent_id": aid, **meta}
                break
        if not chosen and ph.get("optional"):
            skipped.append(ph.get("id", ""))
            continue
        if not chosen and not ph.get("llm"):
            chosen = {"agent_id": agent_ids[0] if agent_ids else ph.get("id"), "installed": False}
        step = {
            "phase": ph.get("phase", ph.get("order")),
            "id": ph.get("id"),
            "label": ph.get("label", ""),
            "role": ph.get("role", ""),
            "llm": bool(ph.get("llm")),
            "heavy": bool(ph.get("heavy")),
            "external": bool(ph.get("external") or chosen and chosen.get("external")),
            "active": bool(chosen and chosen.get("installed", True)),
            "agent": chosen,
            "after": ph.get("after", []),
        }
        if not step["active"] and ph.get("llm") and not ph.get("optional"):
            step["warning"] = f"에이전트 미설치: {agent_ids}"
            skipped.append(ph.get("id", ""))
        steps.append(step)

    return {
        "task": (task or "").strip(),
        "principles": dev_pipeline_config().get("principles") or [],
        "probes": probes,
        "steps": steps,
        "skipped_optional": [s for s in skipped if s],
        "rule": "한 번에 하나의 LLM 단계만 실행. 이전 단계 완료 후 다음 phase.",
    }


def format_dev_plan_text(plan: dict[str, Any]) -> str:
    lines = ["# 프로그램 개발 — 에이전트 사용 순서", ""]
    if plan.get("task"):
        lines.append(f"작업: {plan['task']}")
        lines.append("")
    for p in plan.get("principles") or []:
        lines.append(f"- {p}")
    lines.append("")
    for s in plan.get("steps") or []:
        mark = "ON" if s.get("active") else "SKIP"
        ag = s.get("agent") or {}
        name = ag.get("label") or ag.get("agent_id") or "-"
        model = ag.get("model") or ag.get("command") or ""
        llm = "LLM" if s.get("llm") else "no-LLM"
        lines.append(f"Phase {s.get('phase')}. [{mark}] {s.get('label')} ({s.get('id')}) [{llm}]")
        if s.get("role"):
            lines.append(f"    역할: {s['role']}")
        lines.append(f"    → {name}" + (f" · {model}" if model else ""))
        if s.get("warning"):
            lines.append(f"    !! {s['warning']}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def summarize_dev_plan(task: str = "") -> dict[str, Any]:
    plan = build_dev_plan(task)
    active_chain = [
        f"{s['id']}:{s['agent'].get('agent_id', '')}"
        for s in plan.get("steps") or []
        if s.get("active") and s.get("agent")
    ]
    plan["active_chain"] = active_chain
    return plan
