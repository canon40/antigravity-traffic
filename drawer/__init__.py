# -*- coding: utf-8 -*-
"""서랍(Drawer) — on-demand 모듈 로딩."""

from drawer.router import route_intent, route_text_provider, summarize_route
from drawer.registry import get_worker, get_content_gen, get_automation_flow, loaded_modules, unload_all

__all__ = [
    "route_intent",
    "route_text_provider",
    "summarize_route",
    "get_worker",
    "get_content_gen",
    "get_automation_flow",
    "loaded_modules",
    "unload_all",
]
