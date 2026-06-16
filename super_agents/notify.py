# -*- coding: utf-8 -*-
"""Gmail SMTP 알림 (Super Agent 4단계 — 선택)."""

from __future__ import annotations

import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path


def _smtp_config() -> dict[str, str]:
    return {
        "host": os.environ.get("SUPER_AGENT_SMTP_HOST", "smtp.gmail.com").strip(),
        "port": os.environ.get("SUPER_AGENT_SMTP_PORT", "587").strip(),
        "user": os.environ.get("SUPER_AGENT_GMAIL_USER", "").strip(),
        "password": os.environ.get("SUPER_AGENT_GMAIL_APP_PASSWORD", "").strip(),
        "to": os.environ.get("SUPER_AGENT_EMAIL_TO", "").strip(),
    }


def email_configured() -> bool:
    cfg = _smtp_config()
    return bool(cfg["user"] and cfg["password"] and cfg["to"])


def send_briefing_email(
    *,
    subject: str,
    body_text: str,
    html_path: str | Path | None = None,
) -> None:
    cfg = _smtp_config()
    if not email_configured():
        raise RuntimeError(
            "Gmail 미설정. .env 에 SUPER_AGENT_GMAIL_USER, "
            "SUPER_AGENT_GMAIL_APP_PASSWORD, SUPER_AGENT_EMAIL_TO 를 추가하세요."
        )

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = cfg["user"]
    msg["To"] = cfg["to"]
    msg.attach(MIMEText(body_text, "plain", "utf-8"))

    if html_path:
        path = Path(html_path)
        if path.is_file():
            html = path.read_text(encoding="utf-8", errors="replace")
            msg.attach(MIMEText(html, "html", "utf-8"))

    port = int(cfg["port"] or "587")
    with smtplib.SMTP(cfg["host"], port, timeout=60) as server:
        server.starttls()
        server.login(cfg["user"], cfg["password"])
        server.sendmail(cfg["user"], [cfg["to"]], msg.as_string())
