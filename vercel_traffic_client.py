# -*- coding: utf-8 -*-
"""PC Autoblog ↔ Vercel 트래픽 API 클라이언트."""

from __future__ import annotations

import json
import sys
import threading
from pathlib import Path
from typing import Any, Callable

import httpx

ROOT = Path(__file__).resolve().parent
VT_ROOT = ROOT / "vercel_traffic"

DEFAULT_CONFIG: dict[str, Any] = {
    "vercel_api_url": "",
    "vercel_webhook_secret": "",
    "vercel_enabled": False,
    "vercel_on_publish": False,
    "vercel_interval_minutes": 20,
    "vercel_mode": "local",
    "product_url": "",
}


def load_vercel_config(path: str | Path | None = None) -> dict[str, Any]:
    """accounts.json에서 Vercel 트래픽 설정을 로드합니다."""
    cfg_path = Path(path) if path else ROOT / "accounts.json"
    data = dict(DEFAULT_CONFIG)
    if not cfg_path.is_file():
        return data
    with open(cfg_path, encoding="utf-8") as f:
        raw = json.load(f)
    if not isinstance(raw, dict):
        return data
    for key in DEFAULT_CONFIG:
        if key in raw:
            data[key] = raw[key]
    return data


def _ensure_vt_path() -> None:
    if VT_ROOT.is_dir() and str(VT_ROOT) not in sys.path:
        sys.path.insert(0, str(VT_ROOT))


def normalize_traffic_url(api_url: str) -> str:
    """API POST URL을 `/api/traffic` 형태로 맞춥니다."""
    url = (api_url or "").strip().rstrip("/")
    if not url:
        return ""
    if url.endswith("/api/traffic"):
        return url
    if url.endswith("/api/health"):
        return url[: -len("/health")] + "/traffic"
    if url.endswith("/api"):
        return f"{url}/traffic"
    return f"{url}/api/traffic"


def normalize_health_url(api_url: str) -> str:
    """헬스 체크 GET URL을 `/api/health` 형태로 맞춥니다."""
    traffic = normalize_traffic_url(api_url)
    if not traffic:
        return ""
    return traffic.replace("/api/traffic", "/api/health")


def _run_local(target_url: str, log: Callable[[str], None] | None = None) -> dict[str, Any]:
    _ensure_vt_path()
    from traffic_session import run_traffic_session

    log = log or (lambda _msg: None)
    log(f"로컬 방문: {target_url}")
    result = run_traffic_session(target_url, timeout_sec=8.0)
    ok = bool(result.get("ok"))
    log(f"로컬 결과: HTTP {result.get('status_code')} ({result.get('elapsed_sec')}s)")
    return {"mode": "local", "result": result, "ok": ok}


def _run_cloud(
    target_url: str,
    config: dict[str, Any],
    log: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    log = log or (lambda _msg: None)
    api_url = normalize_traffic_url(str(config.get("vercel_api_url") or ""))
    if not api_url:
        return {"mode": "cloud", "ok": False, "error": "vercel_api_url이 비어 있습니다."}

    headers = {"Content-Type": "application/json"}
    secret = str(config.get("vercel_webhook_secret") or "").strip()
    if secret:
        headers["Authorization"] = f"Bearer {secret}"
        headers["X-Webhook-Secret"] = secret

    body = {"target_url": target_url, "timeout_sec": 8}
    log(f"클라우드 방문: {api_url}")
    with httpx.Client(timeout=15.0) as client:
        response = client.post(api_url, json=body, headers=headers)
    try:
        payload = response.json()
    except Exception:
        payload = {"raw": (response.text or "")[:500]}

    ok = response.status_code == 200
    if isinstance(payload, dict) and "ok" in payload:
        ok = bool(payload.get("ok"))
    log(f"클라우드 결과: HTTP {response.status_code}")
    return {
        "mode": "cloud",
        "status_code": response.status_code,
        "result": payload,
        "ok": ok,
    }


def health_check(config: dict[str, Any] | None = None) -> dict[str, Any]:
    """클라우드 API 헬스를 확인합니다. URL 미설정 시 skip."""
    cfg = config or load_vercel_config()
    health_url = normalize_health_url(str(cfg.get("vercel_api_url") or ""))
    if not health_url:
        return {"ok": True, "skipped": True, "reason": "vercel_api_url 미설정"}

    headers: dict[str, str] = {}
    secret = str(cfg.get("vercel_webhook_secret") or "").strip()
    if secret:
        headers["Authorization"] = f"Bearer {secret}"
        headers["X-Webhook-Secret"] = secret

    with httpx.Client(timeout=10.0) as client:
        response = client.get(health_url, headers=headers)
    try:
        payload = response.json()
    except Exception:
        payload = {"raw": (response.text or "")[:300]}
    return {
        "ok": response.status_code == 200,
        "status_code": response.status_code,
        "result": payload,
    }


def trigger_traffic(
    url: str | None = None,
    *,
    config: dict[str, Any] | None = None,
    log: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    """local / cloud / both 모드로 상품 URL 1회 방문을 실행합니다."""
    cfg = dict(config or load_vercel_config())
    target = (url or cfg.get("product_url") or "").strip()
    if not target:
        return {"ok": False, "error": "방문 URL이 없습니다. product_url 또는 --url을 지정하세요."}

    mode = str(cfg.get("vercel_mode") or "cloud").strip().lower()
    log_fn = log or print
    outcomes: list[dict[str, Any]] = []

    if mode in ("local", "both"):
        try:
            outcomes.append(_run_local(target, log_fn))
        except Exception as exc:
            outcomes.append({"mode": "local", "ok": False, "error": str(exc)})

    if mode in ("cloud", "both"):
        try:
            outcomes.append(_run_cloud(target, cfg, log_fn))
        except Exception as exc:
            outcomes.append({"mode": "cloud", "ok": False, "error": str(exc)})

    ok = bool(outcomes) and all(o.get("ok") for o in outcomes)
    return {"ok": ok, "target_url": target, "mode": mode, "outcomes": outcomes}


class VercelTrafficScheduler:
    """vercel_enabled일 때 N분마다 trigger_traffic을 실행하는 daemon 스레드."""

    def __init__(
        self,
        config: dict[str, Any] | None = None,
        log: Callable[[str], None] | None = None,
        *,
        get_config: Callable[[], dict[str, Any]] | None = None,
        get_target_url: Callable[[], str] | None = None,
    ):
        self._get_config = get_config
        self._get_target_url = get_target_url
        self._config = dict(config or load_vercel_config())
        self._log = log or print
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    @property
    def running(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    def update_config(self, config: dict[str, Any]) -> None:
        self._config = dict(config)

    def start(self) -> None:
        if self.running:
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True, name="VercelTrafficScheduler")
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def _refresh_config(self) -> None:
        if self._get_config:
            try:
                self._config = dict(self._get_config())
            except Exception:
                pass

    def _loop(self) -> None:
        while not self._stop.is_set():
            self._refresh_config()
            if not self._config.get("vercel_enabled"):
                if self._stop.wait(5):
                    break
                continue
            target = ""
            if self._get_target_url:
                try:
                    target = (self._get_target_url() or "").strip()
                except Exception:
                    target = ""
            trigger_traffic(target or None, config=self._config, log=self._log)
            minutes = max(1, int(self._config.get("vercel_interval_minutes") or 20))
            if self._stop.wait(minutes * 60):
                break
