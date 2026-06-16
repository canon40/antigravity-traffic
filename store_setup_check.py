# -*- coding: utf-8 -*-
"""스마트스토어 파이프라인 준비 상태 점검."""

from __future__ import annotations

import os
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import config as cfg
from store_supabase import _TABLE, fetch_keywords, supabase_enabled, upsert_keywords


def _ok(msg: str) -> None:
    print(f"  [OK] {msg}")


def _warn(msg: str) -> None:
    print(f"  [!!] {msg}")


def _fail(msg: str) -> None:
    print(f"  [XX] {msg}")


def check_env() -> bool:
    print("\n=== 1. 환경 변수 (.env) ===")
    gemini = (cfg.GEMINI_API_KEY or cfg.GOOGLE_API_KEY or "").strip()
    if gemini:
        _ok(f"Gemini API 키 설정됨 (...{gemini[-6:]})")
    else:
        _fail("Gemini API 키 없음 - .env 에 GOOGLE_API_KEY 또는 GEMINI_API_KEY 입력")

    if cfg.SUPABASE_URL:
        _ok(f"SUPABASE_URL = {cfg.SUPABASE_URL}")
    else:
        _warn("SUPABASE_URL 없음 - 로컬 JSON(data/store_keywords.json) 사용")

    key = (cfg.SUPABASE_ANON_KEY or cfg.SUPABASE_SERVICE_KEY or os.environ.get("SUPABASE_KEY", "")).strip()
    if key:
        _ok(f"Supabase 키 설정됨 (...{key[-6:]})")
    elif cfg.SUPABASE_URL:
        _fail("SUPABASE_ANON_KEY / SUPABASE_KEY 없음")
    else:
        _warn("Supabase 키 미설정 (로컬 모드)")

    _ok(f"키워드 테이블명: {_TABLE}")
    return bool(gemini)


def check_docs() -> bool:
    print("\n=== 2. 가이드 문서 (docs/) ===")
    path = _ROOT / "docs" / "naver_shopping_seo.txt"
    if not path.exists():
        _fail(f"없음: {path}")
        return False
    text = path.read_text(encoding="utf-8")
    _ok(f"naver_shopping_seo.txt ({len(text)}자)")
    required = ("50자", "어류징", "태그 사전", "[] () - _ /")
    missing = [r for r in required if r not in text]
    if missing:
        _warn(f"권장 문구 누락 가능: {', '.join(missing)}")
    else:
        _ok("필수 SEO 룰 문구 포함 확인")
    return True


def check_files() -> bool:
    print("\n=== 3. 파이프라인 파일 ===")
    names = (
        "store_pipeline.py",
        "store_marketing_agent.py",
        "store_keyword_crawler.py",
        "store_supabase.py",
        "run_store_pipeline.bat",
    )
    ok = True
    for name in names:
        p = _ROOT / name
        if p.exists():
            _ok(name)
        else:
            _fail(f"없음: {name}")
            ok = False
    return ok


def check_supabase_connection() -> bool:
    print("\n=== 4. Supabase 연결·테이블 ===")
    if not supabase_enabled():
        _warn("Supabase 미사용 - 연결 테스트 생략 (로컬 JSON 모드)")
        local = _ROOT / "data" / "store_keywords.json"
        if local.exists():
            _ok(f"로컬 키워드 파일: {local}")
        else:
            _warn("로컬 키워드 파일 없음 - 첫 크롤/생성 시 생성됩니다")
        return True

    probe = [{
        "category": "__setup_check__",
        "keyword": "__probe__",
        "monthly_search_volume": 1,
        "competition_index": 0.1,
    }]
    res = upsert_keywords(probe)
    if not res.get("ok"):
        err = str(res.get("error", ""))
        if "PGRST205" in err or ("relation" in err and "does not exist" in err):
            _fail(f"테이블 public.{_TABLE} 없음 - sql/keywords_schema.sql 을 SQL Editor 에서 실행")
            print("       https://supabase.com/dashboard/project/qkporqtajfikppwsishz/sql/new")
        elif "401" in err or "JWT" in err:
            _fail("Supabase 인증 실패 - ANON_KEY / SERVICE_KEY 확인")
        else:
            _fail(f"Supabase 오류: {err[:200]}")
        return False

    _ok(f"테이블 public.{_TABLE} upsert 성공")
    rows = fetch_keywords("__setup_check__", limit=1)
    if rows:
        _ok("키워드 조회 성공")
    return True


def main() -> int:
    print("스마트스토어 마케팅 파이프라인 - 준비 상태 점검")
    results = [
        check_env(),
        check_docs(),
        check_files(),
        check_supabase_connection(),
    ]
    print("\n=== 요약 ===")
    if all(results):
        print("  모든 필수 항목 준비 완료. GUI: run_gui.bat → 스마트스토어 탭")
        print("  CLI: run_store_pipeline.bat")
        return 0
    print("  일부 항목 보완 필요. 위 [XX]/[!!] 메시지를 확인하세요.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
