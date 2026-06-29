#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""PC 꺼져도 돌아가는 Cloudtype 허브 상태 확인."""

from __future__ import annotations

import json
import os
import sys
import urllib.request

CLOUDTYPE = "https://port-0-antigravity-traffic-mqg8473t248a0738.sel3.cloudtype.app"
VERCEL = "https://permacoat.shop"


def _get(url: str, timeout: float = 12.0) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": "NanumLab-HubCheck/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _ok(msg: str) -> None:
    try:
        print(f"  [OK] {msg}", flush=True)
    except UnicodeEncodeError:
        print(f"  [OK] {msg.encode('cp949', errors='replace').decode('cp949')}", flush=True)


def _warn(msg: str) -> None:
    try:
        print(f"  [!!] {msg}", flush=True)
    except UnicodeEncodeError:
        print(f"  [!!] {msg.encode('cp949', errors='replace').decode('cp949')}", flush=True)


def _fail(msg: str) -> None:
    try:
        print(f"  [FAIL] {msg}", flush=True)
    except UnicodeEncodeError:
        print(f"  [FAIL] {msg.encode('cp949', errors='replace').decode('cp949')}", flush=True)


def main() -> int:
    print("=" * 56)
    print("24시간 SEO 허브 상태 (PC 꺼져도 Cloudtype에서 동작)")
    print("=" * 56)

    # Cloudtype 직접
    print(f"\n[1] Cloudtype API\n  {CLOUDTYPE}")
    try:
        health = _get(f"{CLOUDTYPE}/api/health")
        status = _get(f"{CLOUDTYPE}/api/status")
        if health.get("status") == "healthy":
            _ok("헬스체크 정상")
        else:
            _warn(f"헬스: {health}")
        if status.get("running"):
            _ok(f"순위 추적 ON · platform={status.get('platform')}")
        else:
            _fail("순위 추적 꺼짐 — Cloudtype 대시보드에서 Redeploy 또는 24h 시작")
        if status.get("traffic_running"):
            _ok(f"트래픽 루프 ON · 마지막: {status.get('last_traffic_at')}")
        else:
            _warn("트래픽 루프 꺼짐")
        if not status.get("naver_api_configured"):
            _warn("NAVER_CLIENT_ID/SECRET 미설정 — Cloudtype 환경변수 추가 권장")
        if status.get("persistence") == "cloud_tmp":
            _warn("Supabase 미연결 — 재시작 시 순위 기록 일부 소실 (SUPABASE_URL 설정 권장)")
        lr = status.get("last_rank_keyword")
        if lr:
            _ok(f"최근 순위: 「{lr}」 {status.get('last_rank')}위")
    except Exception as exc:
        _fail(f"Cloudtype 접속 실패: {exc}")
        print("\n  → Cloudtype 대시보드에서 Redeploy 필요")
        print("  → https://app.cloudtype.io/@canon4040/antigravity-traffic")
        return 1

    # Vercel 프록시
    print(f"\n[2] Vercel 대시보드 (permacoat.shop)")
    try:
        vs = _get(f"{VERCEL}/api/status")
        if vs.get("running") and vs.get("platform") == "cloudtype":
            _ok("Vercel → Cloudtype 연동 정상")
        elif vs.get("platform") == "vercel" and not vs.get("running"):
            _warn("정적 폴백만 표시 — Cloudtype 연결 확인")
        else:
            _ok(f"status: running={vs.get('running')} platform={vs.get('platform')}")
    except Exception as exc:
        _warn(f"Vercel status: {exc}")

    # 로컬 API 키
    print("\n[3] 로컬 PC API 키 (.env)")
    try:
        from pathlib import Path

        from dotenv import load_dotenv

        root = Path(__file__).resolve().parents[1]
        load_dotenv(root / ".env", override=True)
        naver_ok = bool(os.environ.get("NAVER_CLIENT_ID", "").strip())
        gemini_ok = bool(os.environ.get("GEMINI_API_KEY", "").strip())
        if naver_ok:
            _ok("NAVER 검색 API — 로컬 순위 조회 가능 (run_rank_report.bat)")
        else:
            _warn("NAVER_CLIENT_ID 미설정 — run_rank_report.bat 불가")
        if gemini_ok:
            _ok("GEMINI_API_KEY — 블로그 SEO·JARVIS LLM 가능 (run_verify_gemini.bat)")
        else:
            _warn("GEMINI_API_KEY 미설정 — run_permacoat_blog.bat 불가")
    except Exception as exc:
        _warn(f"로컬 키 확인: {exc}")

    print("\n" + "=" * 56)
    print("PC 꺼져도 안 되는 작업 (로컬 전용)")
    print("=" * 56)
    print("  · AI 숏폼 영상 (run_shorts.bat / Veo)")
    print("  · 네이버 블로그 발행 (영상 드래그 + 붙여넣기)")
    print("  · 판매자센터 SEO 자동 입력 (Playwright)")
    print("  · http://127.0.0.1:5000 로컬 허브")
    print("\n  -> 순위·트래픽만 24h: Cloudtype ([1] OK 이면 PC 꺼져도 동작)")
    print("=" * 56)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
