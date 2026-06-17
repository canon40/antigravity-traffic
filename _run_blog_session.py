# -*- coding: utf-8 -*-
"""1회 블로그 원고 생성 + 네이버 발행 (GUI 없이)."""
from __future__ import annotations

import asyncio
import json
import os
import sys
from datetime import datetime

_ROOT = os.path.dirname(os.path.abspath(__file__))
os.chdir(_ROOT)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

os.environ.setdefault("BLOG_STANDALONE", "1")
os.environ.setdefault("BLOG_JARVIS_BRIDGE", "0")
os.environ.setdefault("BLOG_JARVIS_MODEL_ROUTING", "0")
os.environ.setdefault("BLOG_API_SPARING", "0")
os.environ.setdefault("BLOG_TEXT_PROVIDER", "gemini")
os.environ.setdefault("BLOG_IMAGE_PROVIDER", "genai")
os.environ.setdefault("BLOG_OLLAMA_MODEL", "qwen3:4b")
os.environ.setdefault("BLOG_OLLAMA_TIMEOUT", "120")
os.environ.setdefault("BLOG_DEFER_BROWSER", "1")
os.environ.setdefault("BLOG_BROWSER_PER_ROUND", "1")
os.environ.setdefault("BLOG_UNLOAD_AFTER_JOB", "1")

LOG_PATH = os.path.join(_ROOT, "_run_blog_session.log")


def log(msg: str) -> None:
    line = f"[{datetime.now().strftime('%H:%M:%S')}] {msg}"
    try:
        print(line, flush=True)
    except UnicodeEncodeError:
        print(line.encode("cp949", errors="replace").decode("cp949"), flush=True)
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(line + "\n")


async def main() -> int:
    open(LOG_PATH, "w", encoding="utf-8").close()
    from blog_automation_flow import run_main_loop
    from blog_content_gen import apply_product_choice
    from mobile_server import HeadlessApp, build_config

    acc_path = os.path.join(_ROOT, "accounts.json")
    with open(acc_path, encoding="utf-8") as f:
        data = json.load(f)

    work = dict(data)
    raw_kws = work.get("keywords") or ""
    if isinstance(raw_kws, str):
        work["keywords"] = [k.strip() for k in raw_kws.split(",") if k.strip()]
    elif not isinstance(raw_kws, list):
        work["keywords"] = []

    override_kw = (os.environ.get("BLOG_OVERRIDE_KEYWORD") or "").strip()
    if override_kw:
        work["keywords"] = [override_kw]

    apply_product_choice(work)
    keywords = work.get("keywords") or []
    if isinstance(keywords, list):
        keywords = ", ".join(str(x).strip() for x in keywords if str(x).strip())
    post_type = (work.get("post_type") or "").strip()
    if not post_type or post_type == "자동(매번 랜덤)":
        log("ERROR: 글 유형(주제)을 accounts.json에 저장하거나 GUI에서 선택한 뒤 실행해 주세요.")
        return 1
    if not str(keywords).strip() and post_type not in ("맛집/일상", "취미글", "알림글"):
        log("ERROR: 포스팅 키워드를 accounts.json 또는 GUI에 입력한 뒤 실행해 주세요.")
        return 1

    tp_label = (data.get("text_provider") or os.environ.get("BLOG_TEXT_PROVIDER") or "gemini").strip()
    if "Gemini" in tp_label and "Ollama" not in tp_label.split("→")[0]:
        text_provider = "gemini"
    elif "Ollama" in tp_label or "로컬" in tp_label:
        text_provider = "ollama"
    else:
        text_provider = os.environ.get("BLOG_TEXT_PROVIDER", "gemini").strip().lower()
    if text_provider == "gemini":
        os.environ["BLOG_API_SPARING"] = "0"
    image_provider = os.environ.get("BLOG_IMAGE_PROVIDER", "genai").strip().lower()

    payload = {
        "gemini_key": data.get("gemini_key", ""),
        "vertex_api_key": data.get("vertex_api_key", ""),
        "vertex_project_id": data.get("vertex_project_id", ""),
        "naver_id1": data.get("naver_id1", ""),
        "naver_pw1": data.get("naver_pw1", ""),
        "naver_id2": data.get("naver_id2", ""),
        "naver_pw2": data.get("naver_pw2", ""),
        "keywords": keywords,
        "post_type": post_type,
        "product_choice": work.get("product_choice") or "none",
        "product_url": (work.get("product_url") or "").strip(),
        "count": int(data.get("count") or 1),
        "gap": 1,
        "use_naver1": data.get("use_naver1", True),
        "use_naver2": data.get("use_naver2", True),
        "use_tistory": data.get("use_tistory", True),
        "use_google": data.get("use_google", False),
        "tistory_id": data.get("tistory_id", ""),
        "tistory_pw": data.get("tistory_pw", ""),
        "manual_confirm": False,
        "master_guidelines": data.get("master_guidelines") or "",
        "writing_guidelines": data.get("writing_guidelines") or "",
        "text_provider": text_provider,
        "image_provider": image_provider,
    }

    config = build_config(payload)
    config["text_provider"] = text_provider
    config["image_provider"] = image_provider
    if payload.get("product_url"):
        config["product_url"] = payload["product_url"]

    app = HeadlessApp()

    def _relay(msg, level="info"):
        del level
        log(msg)

    app.log = _relay  # type: ignore[method-assign]

    targets = []
    if config.get("use_naver1") and config.get("naver_ids"):
        targets.append(config["naver_ids"][0])
    if config.get("use_naver2") and config.get("n2_id"):
        targets.append(config["n2_id"])
    if config.get("use_tistory"):
        targets.append(f"티스토리({config.get('tistory_id') or '?'})")

    log("=== 블로그 1회 발행 세션 시작 ===")
    log(f"발행 대상: {', '.join(targets) or '없음'}")
    log(f"키워드: {config.get('keywords')}")
    log(f"글 유형: {config.get('post_type')}")

    try:
        await run_main_loop(app, config)
        logs = app.get_logs()
        if any("완료" in x or "성공" in x or "발행" in x for x in logs[-30:]):
            log("SESSION_OK")
            return 0
        if any("❌" in x for x in logs[-20:]):
            log("SESSION_FAIL")
            return 1
        log("SESSION_DONE")
        return 0
    except Exception as e:
        log(f"SESSION_ERROR: {e}")
        return 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
