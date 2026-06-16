# -*- coding: utf-8 -*-
"""24/7 Super Agent 워크플로 (Base44 영상 로컬 구현)."""

__all__ = ["SuperAgentResult", "run_super_agent_workflow"]


def __getattr__(name: str):
    if name in __all__:
        from super_agents.pipeline import SuperAgentResult, run_super_agent_workflow

        return {"SuperAgentResult": SuperAgentResult, "run_super_agent_workflow": run_super_agent_workflow}[name]
    raise AttributeError(name)
