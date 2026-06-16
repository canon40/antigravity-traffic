# -*- coding: utf-8 -*-
"""Vercel 클라우드 트래픽 API + 로컬 HTTP 방문 연동."""

from __future__ import annotations

import json
import sys
import threading
import time
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlparse

import httpx

ROOT = Path(__file__).resolve().parent
DEFAULT_ACCOUNTS = ROOT / "accounts.json"
DEFAULT_TARGET = "https://smartstore.naver.com"
DEFAULT_INTERVAL_MIN = 20


def _log(log_fn: Callable[[str], None] | None, msg: str) -> None:
    if not log_fn:
        return
    try:
        log_fn(msg)
    except UnicodeEncodeError:
        log_fn(msg.encode("ascii", errors="replace").decode("ascii"))


def load_vercel_config(accounts_path: str | Path | None = None) -> dict[str, Any]:
    path = Path(accounts_path) if accounts_path else DEFAULT_ACCOUNTS
    data: dict[str, Any] = {}
    if path.is_file():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            data = {}
    return {
        "vercel_api_url": (data.get("vercel_api_url") or "").strip(),
        "vercel_webhook_secret": (data.get("vercel_webhook_secret") or "").strip(),
        "vercel_enabled": bool(data.get("vercel_enabled", False)),
        "vercel_on_publish": bool(data.get("vercel_on_publish", True)),
        "vercel_interval_minutes": int(data.get("vercel_interval_minutes") or DEFAULT_INTERVAL_MIN),
        "vercel_mode": (data.get("vercel_mode") or "local").strip().lower(),
        "product_url": (data.get("product_url") or "").strip(),
    }


def normalize_traffic_url(api_url: str) -> str:
    base = (api_url or "").strip().rstrip("/")
    if not base:
        return ""
    if base.endswith("/api/traffic"):
        return base
    if base.endswith("/api"):
        return f"{base}/traffic"
    return f"{base}/api/traffic"


def normalize_health_url(api_url: str) -> str:
    base = (api_url or "").strip().rstrip("/")
    if not base:
        return ""
    if base.endswith("/api/health"):
        return base
    if base.endswith("/api/traffic"):
        return base[: -len("/traffic")] + "/health"
    if base.endswith("/api"):
        return f"{base}/health"
    return f"{base}/api/health"


def _auth_headers(secret: str) -> dict[str, str]:
    if not secret:
        return {}
    return {
        "Authorization": f"Bearer {secret}",
        "X-Webhook-Secret": secret,
    }


def _run_local(target_url: str, timeout_sec: float = 8.0) -> dict[str, Any]:
    vt_dir = ROOT / "vercel_traffic"
    if str(vt_dir) not in sys.path:
        sys.path.insert(0, str(vt_dir))
    from traffic_session import run_traffic_session

    result = run_traffic_session(target_url, timeout_sec=timeout_sec)
    return {"ok": bool(result.get("ok")), "channel": "local", "result": result}


def _run_cloud(target_url: str, config: dict[str, Any]) -> dict[str, Any]:
    post_url = normalize_traffic_url(config.get("vercel_api_url") or "")
    if not post_url:
        return {"ok": False, "channel": "cloud", "error": "vercel_api_url 미설정"}

    headers = {"Content-Type": "application/json", **_auth_headers(config.get("vercel_webhook_secret") or "")}
    payload = {"target_url": target_url, "timeout_sec": 8.0}
    with httpx.Client(timeout=12.0) as client:
        response = client.post(post_url, json=payload, headers=headers)

    try:
        body = response.json()
    except Exception:
        body = {"status": "error", "message": response.text[:300]}

    ok = response.status_code == 200 and body.get("status") == "success"
    return {
        "ok": ok,
        "channel": "cloud",
        "status_code": response.status_code,
        "body": body,
    }


def health_check(config: dict[str, Any] | None = None) -> dict[str, Any]:
    cfg = config or load_vercel_config()
    mode = (cfg.get("vercel_mode") or "local").lower()
    api_url = (cfg.get("vercel_api_url") or "").strip()

    if mode == "local" or not api_url:
        target = resolve_target_url(cfg)
        try:
            local = _run_local(target)
            ok = bool(local.get("ok"))
            code = (local.get("result") or {}).get("status_code")
            return {
                "ok": ok,
                "mode": "local",
                "url": target,
                "body": {"message": f"로컬 HTTP 방문 OK (HTTP {code})" if ok else "로컬 방문 실패"},
                "result": local,
            }
        except Exception as exc:
            return {"ok": False, "mode": "local", "error": str(exc)}

    health_url = normalize_health_url(api_url)
    headers = _auth_headers(cfg.get("vercel_webhook_secret") or "")
    with httpx.Client(timeout=10.0) as client:
        response = client.get(health_url, headers=headers)
    try:
        body = response.json()
    except Exception:
        body = {"message": response.text[:200]}
    return {
        "ok": response.status_code == 200,
        "status_code": response.status_code,
        "body": body,
        "url": health_url,
        "mode": "cloud",
    }


def resolve_target_url(config: dict[str, Any], override: str | None = None) -> str:
    url = (override or config.get("product_url") or "").strip()
    return url or DEFAULT_TARGET


def trigger_traffic(
    target_url: str | None = None,
    *,
    config: dict[str, Any] | None = None,
    log: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    cfg = dict(config or load_vercel_config())
    url = resolve_target_url(cfg, target_url)
    mode = (cfg.get("vercel_mode") or "local").lower()
    results: dict[str, Any] = {}

    has_cloud_url = bool(normalize_traffic_url(cfg.get("vercel_api_url") or ""))
    if mode in ("cloud", "both") and not has_cloud_url:
        _log(log, "   ⚠️ vercel_api_url 없음 → 로컬 HTTP만 실행합니다.")
        mode = "local"

    if mode in ("local", "both"):
        _log(log, f"   ☁️ 로컬 트래픽 방문: {url}")
        results["local"] = _run_local(url)

    if mode in ("cloud", "both"):
        _log(log, f"   ☁️ Vercel 트래픽 호출: {url}")
        results["cloud"] = _run_cloud(url, cfg)

    if not results:
        return {"ok": False, "error": f"알 수 없는 vercel_mode: {mode}", "results": {}}

    ok = all(item.get("ok") for item in results.values())
    return {"ok": ok, "target_url": url, "mode": mode, "results": results}


class VercelTrafficScheduler:
    """PC에서 Vercel/로컬 트래픽을 주기 실행 (Base44 없이도 동작)."""

    def __init__(
        self,
        *,
        get_config: Callable[[], dict[str, Any]],
        get_target_url: Callable[[], str],
        log: Callable[[str], None] | None = None,
    ):
        self._get_config = get_config
        self._get_target_url = get_target_url
        self._log = log
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    @property
    def running(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    def start(self) -> None:
        if self.running:
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="vercel-traffic-scheduler", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def _loop(self) -> None:
        while not self._stop.is_set():
            cfg = self._get_config()
            if not cfg.get("vercel_enabled"):
                _log(self._log, "   ☁️ Vercel 주기 실행: 비활성화됨")
                break
            interval = max(1, int(cfg.get("vercel_interval_minutes") or DEFAULT_INTERVAL_MIN))
            target = self._get_target_url()
            _log(self._log, f"   ☁️ Vercel 주기 트래픽 ({interval}분) — {target}")
            try:
                outcome = trigger_traffic(target, config=cfg, log=self._log)
                if outcome.get("ok"):
                    _log(self._log, "   ✅ Vercel 트래픽 성공")
                else:
                    _log(self._log, f"   ⚠️ Vercel 트래픽 실패: {outcome}")
            except Exception as exc:
                _log(self._log, f"   ❌ Vercel 트래픽 오류: {exc}")

            for _ in range(interval * 60):
                if self._stop.is_set():
                    return
                time.sleep(1)
