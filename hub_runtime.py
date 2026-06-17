# -*- coding: utf-8 -*-
"""Vercel(Cron) · Cloudtype(데몬 스레드) · 로컬 PC 구분."""

from __future__ import annotations

import os
import sys
from pathlib import Path


def cloud_platform() -> str:
    """vercel | cloudtype | local"""
    explicit = (os.environ.get("HUB_CLOUD_PLATFORM") or "").strip().lower()
    if explicit in ("vercel", "cloudtype", "local"):
        return explicit
    if os.environ.get("VERCEL"):
        return "vercel"
    if os.environ.get("CLOUDTYPE") or os.environ.get("CLOUDTYPE_SERVICE"):
        return "cloudtype"
    # Cloudtype env 미설정 배포: Linux 컨테이너(/app) 또는 PORT만 있는 PaaS
    if sys.platform != "win32":
        if Path("/app").is_dir():
            return "cloudtype"
        if os.environ.get("PORT"):
            return "cloudtype"
        if os.environ.get("GUNICORN_CMD_ARGS") or os.environ.get("KUBERNETES_SERVICE_HOST"):
            return "cloudtype"
        server_sw = (os.environ.get("SERVER_SOFTWARE") or "").lower()
        if "gunicorn" in server_sw or "uvicorn" in server_sw:
            return "cloudtype"
    return "local"


def is_vercel() -> bool:
    return cloud_platform() == "vercel"


def is_cloudtype() -> bool:
    return cloud_platform() == "cloudtype"


def is_cloud_hub() -> bool:
    return cloud_platform() in ("vercel", "cloudtype")


def is_cron_mode() -> bool:
    """Vercel Cron — 서버리스, 백그라운드 스레드 없음."""
    return is_vercel()


def uses_ephemeral_disk() -> bool:
    """Supabase 미설정 시 /tmp 등 휘발 저장 (Vercel·Cloudtype)."""
    return is_cloud_hub()
