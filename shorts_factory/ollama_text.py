# -*- coding: utf-8 -*-
"""쇼츠 콘티용 Ollama/Gemini 텍스트 생성 — blog_content_gen import 없이 동작."""

from __future__ import annotations

import asyncio
import os
import threading

OLLAMA_BASE_URL = os.environ.get("BLOG_OLLAMA_URL", "http://localhost:11434").rstrip("/")
OLLAMA_READ_TIMEOUT = int(os.environ.get("BLOG_OLLAMA_TIMEOUT", "120"))
_OLLAMA_FAST_MODELS = (
    "qwen3:4b",
    "deepseek-r1:1.5b",
    "hermes3:latest",
    "gemma2:2b",
    "qwen3:8b",
)
_OLLAMA_SYSTEM = (
    "You are a Korean short-form video storyboard writer. "
    "Follow the requested output format exactly. Output valid JSON only when asked."
)


def _shrink_prompt(prompt: str, max_chars: int = 12000) -> str:
    text = (prompt or "").strip()
    if len(text) <= max_chars:
        return text
    head = int(max_chars * 0.38)
    tail = int(max_chars * 0.58)
    return text[:head] + "\n\n...[중간 생략]...\n\n" + text[-tail:]


def ollama_read_timeout_for(num_predict: int) -> int:
    env_cap = max(240, OLLAMA_READ_TIMEOUT)
    if num_predict <= 500:
        return min(env_cap, max(300, env_cap // 2))
    if num_predict <= 1200:
        return env_cap
    return min(env_cap + 120, 720)


async def ollama_ping() -> bool:
    import requests

    try:
        res = await asyncio.to_thread(requests.get, f"{OLLAMA_BASE_URL}/api/tags", timeout=4)
        return res.status_code == 200
    except Exception:
        return False


async def ollama_ping_with_retry(log_func=None, attempts: int = 3) -> bool:
    for i in range(attempts):
        if await ollama_ping():
            return True
        if i + 1 < attempts:
            if log_func:
                log_func(f"      Ollama 연결 재시도 ({i + 2}/{attempts})...")
            await asyncio.sleep(2)
    return False


async def _list_installed_models() -> set[str]:
    import requests

    try:
        res = await asyncio.to_thread(
            requests.get, f"{OLLAMA_BASE_URL}/api/tags", timeout=5
        )
        if res.status_code == 200:
            return {m.get("name", "") for m in (res.json().get("models") or []) if m.get("name")}
    except Exception:
        pass
    return set()


async def resolve_ollama_models(log_func) -> list[str]:
    installed = await _list_installed_models()
    ordered: list[str] = []
    env_model = (os.environ.get("BLOG_OLLAMA_MODEL", "qwen3:4b") or "").strip()

    if env_model:
        if env_model in installed:
            ordered.append(env_model)
        else:
            base = env_model.split(":")[0] + ":latest"
            if base in installed:
                ordered.append(base)

    for name in _OLLAMA_FAST_MODELS:
        if name in installed and name not in ordered:
            ordered.append(name)

    for name in sorted(installed):
        if name not in ordered:
            ordered.append(name)

    if not ordered:
        fallback = env_model or "qwen3:4b"
        log_func(f"      Ollama 모델 목록 확인 실패 — {fallback} 사용")
        return [fallback]
    log_func(f"      Ollama 모델 순서: {', '.join(ordered[:3])}")
    return ordered


async def ollama_chat_once(
    model: str, prompt: str, log_func, num_predict: int, read_timeout: int
) -> str:
    import requests

    compact = _shrink_prompt(prompt)
    user_tail = "\n\n반드시 요청한 형식(JSON 등)만 출력해."
    log_func(
        f"      로컬 Ollama({model}) 콘티 생성 중... (최대 {read_timeout}초)"
    )
    stop = threading.Event()

    def _heartbeat():
        tick = 0
        while not stop.wait(20):
            tick += 1
            log_func(f"      … Ollama({model}) 응답 대기 ({tick * 20}초)")

    hb = threading.Thread(target=_heartbeat, daemon=True)
    hb.start()

    def _extract(data: dict, via: str) -> str:
        if via == "chat":
            msg = data.get("message") or {}
            text = (msg.get("content") or msg.get("thinking") or "").strip()
        else:
            text = (data.get("response") or "").strip()
        if not text:
            raise RuntimeError(f"빈 Ollama 응답 ({via})")
        return text

    try:
        low = model.lower()
        chat_payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": _OLLAMA_SYSTEM},
                {"role": "user", "content": compact + user_tail},
            ],
            "stream": False,
            "keep_alive": "15m",
            "options": {"num_predict": num_predict, "temperature": 0.45, "top_p": 0.9},
        }
        generate_payload = {
            "model": model,
            "prompt": f"{_OLLAMA_SYSTEM}\n\n{compact}{user_tail}",
            "stream": False,
            "keep_alive": "15m",
            "options": {"num_predict": num_predict, "temperature": 0.45, "top_p": 0.9},
        }
        attempts: list[tuple[str, str, dict]] = []
        if "qwen3" in low or "deepseek-r1" in low:
            attempts.append(("chat", f"{OLLAMA_BASE_URL}/api/chat", chat_payload))
        attempts.append(("generate", f"{OLLAMA_BASE_URL}/api/generate", generate_payload))
        if "qwen3" not in low and "deepseek-r1" not in low:
            attempts.insert(0, ("chat", f"{OLLAMA_BASE_URL}/api/chat", chat_payload))

        errors: list[str] = []
        for via, url, payload in attempts:
            if "qwen3" in low or "deepseek-r1" in low:
                payload["think"] = False
            try:
                ollama_res = await asyncio.to_thread(
                    requests.post, url, json=payload, timeout=(10, read_timeout)
                )
                if ollama_res.status_code != 200:
                    raise RuntimeError(f"HTTP {ollama_res.status_code}: {ollama_res.text[:80]}")
                text = _extract(ollama_res.json(), via)
                log_func(f"      로컬 Ollama({model}/{via}) 완료 ({len(text)}자)")
                return text
            except Exception as e:
                errors.append(f"{via}: {str(e)[:60]}")
        raise RuntimeError(f"{model} 실패 ({'; '.join(errors)})")
    finally:
        stop.set()
