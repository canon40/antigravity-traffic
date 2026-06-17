# -*- coding: utf-8 -*-
"""JARVIS·Traffic run_*.bat 스캔 → data/programs_catalog.json (Git 커밋용)."""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
JARVIS_ROOT = Path(os.environ.get("JARVIS_ROOT", r"D:\@code\javis"))
OUT = ROOT / "data" / "programs_catalog.json"

ICON_BY_CAT = {
    "seo": "fa-magnifying-glass-chart",
    "blog": "fa-blog",
    "video": "fa-film",
    "studio": "fa-store",
    "agent": "fa-robot",
    "ops": "fa-plug",
    "traffic": "fa-gauge-high",
}

CAT_RULES = [
    ("blog", r"blog|블로그"),
    ("video", r"video|영상|shorts|숏츠|youtube|키워드영상"),
    ("studio", r"detail|상세|studio|스튜디오|sangseopage"),
    ("seo", r"seo|naver|keyword|키워드|rank|순위|hybrid"),
    ("agent", r"jarvis|javis|workspace|agent|자비스|autonom|evolution|harness|brain"),
    ("ops", r"check|connect|검증|setup|install|doctor|sync|점검"),
]


def _slug(name: str) -> str:
    base = re.sub(r"\.bat$", "", name, flags=re.I)
    base = re.sub(r"[^\w가-힣]+", "_", base).strip("_").lower()
    return base[:64] or "program"


def _guess_category(stem: str) -> str:
    low = stem.lower()
    for cat, pattern in CAT_RULES:
        if re.search(pattern, low, re.I):
            return cat
    return "agent"


def _pretty_name(stem: str) -> str:
    name = re.sub(r"^run_", "", stem, flags=re.I)
    name = name.replace("_", " ").strip()
    return name or stem


def _scan_bats(base: Path, *, source: str, workspace: str, extra: dict | None = None) -> list[dict]:
    if not base.is_dir():
        return []
    items = []
    for path in sorted(base.glob("run_*.bat")):
        stem = path.stem
        cat = _guess_category(stem)
        pid = f"{source}_{_slug(path.name)}"
        entry = {
            "id": pid,
            "name": _pretty_name(stem),
            "workspace": workspace,
            "source": source,
            "launcher": path.name,
            "category": cat,
            "description": f"{path.name} — {workspace} 로컬 실행",
            "icon": ICON_BY_CAT.get(cat, "fa-play"),
        }
        if extra:
            entry.update(extra)
        items.append(entry)
    return items


TRAFFIC_OVERRIDES = {
    "run.bat": {
        "id": "traffic_web_hub",
        "name": "웹 SEO 허브 (현재)",
        "category": "traffic",
        "description": "순위 추적·SEO·블로그 PWA 대시보드",
        "icon": "fa-gauge-high",
        "cloud_action": "hub_status",
    },
    "run_gui.bat": {
        "id": "traffic_autoblog_gui",
        "name": "Autoblog GUI",
        "category": "blog",
        "description": "클라우드: 블로그 스튜디오 · PC: run_gui.bat 데스크톱 GUI",
        "icon": "fa-desktop",
        "cloud_action": "blog_studio",
    },
    "run_blog_post.bat": {
        "id": "traffic_blog_post",
        "name": "blog post",
        "category": "blog",
        "description": "키워드 1회 원고 생성·발행 (run_blog_post.bat)",
        "icon": "fa-blog",
        "cloud_action": "blog_pipeline",
    },
    "run_블로그_자동.bat": {
        "id": "traffic_blog_auto",
        "name": "블로그 자동",
        "category": "blog",
        "description": "Autoblog GUI 실행 (자동화 탭)",
        "icon": "fa-blog",
        "cloud_action": "blog_studio",
    },
    "run_블로그_전체.bat": {
        "id": "traffic_blog_full",
        "name": "블로그 전체",
        "category": "blog",
        "description": "네이버+티스토리 전체 발행 1회",
        "icon": "fa-blog",
        "cloud_action": "blog_pipeline",
    },
    "run_content_factory.bat": {
        "id": "traffic_content_factory",
        "name": "콘텐츠 팩토리",
        "category": "blog",
        "description": "상품·블로그 SEO 초안 생성 파이프라인",
        "icon": "fa-wand-magic-sparkles",
        "cloud_action": "content_generate",
    },
    "run_seo_hub_verify.bat": {
        "id": "local_run_seo_hub_verify",
        "name": "허브 배포 검증",
        "category": "ops",
        "description": "로컬/프로덕션 SEO 허브 API 점검",
        "icon": "fa-stethoscope",
    },
    "run_programs_check.bat": {
        "id": "traffic_programs_check",
        "name": "프로그램 점검",
        "category": "ops",
        "description": "허브 모듈·API 순차 점검",
        "icon": "fa-stethoscope",
    },
    "rank_daily.bat": {
        "id": "traffic_rank_daily",
        "name": "일일 순위",
        "category": "seo",
        "description": "로컬에서 순위 1회 추적",
        "icon": "fa-ranking-star",
    },
    "traffic_once.bat": {
        "id": "traffic_once",
        "name": "트래픽 1회",
        "category": "traffic",
        "description": "스마트스토어 HTTP 방문 1회 테스트",
        "icon": "fa-car",
    },
}


def _apply_overrides(items: list[dict], overrides: dict) -> list[dict]:
    out = []
    seen = set()
    for item in items:
        launcher = item.get("launcher", "")
        if launcher in overrides:
            merged = {**item, **overrides[launcher]}
            out.append(merged)
            seen.add(merged["id"])
        else:
            out.append(item)
            seen.add(item["id"])
    return out


def _pick_jarvis_root(*, bundled_only: bool = False) -> Path:
    """Git 커밋용: javis/ 서브모듈만 스캔. 로컬 개발: JARVIS_ROOT 허용."""
    bundled = ROOT / "javis"
    if bundled_only:
        return bundled
    external = Path(os.environ.get("JARVIS_ROOT", r"D:\@code\javis"))
    bundled_count = len(list(bundled.glob("run_*.bat"))) if bundled.is_dir() else 0
    external_count = len(list(external.glob("run_*.bat"))) if external.is_dir() else 0
    if bundled_count > 0:
        return bundled
    if external_count > 0:
        return external
    return bundled if bundled.is_dir() else external


def _annotate_cloud(entry: dict[str, Any]) -> dict[str, Any]:
    """카탈로그 JSON에 cloud_action·runtime 메타 추가."""
    try:
        from javis_serverless import cloud_runtime, resolve_cloud_action
    except ImportError:
        return entry
    action = resolve_cloud_action(entry)
    out = dict(entry)
    if action:
        out["cloud_action"] = action
    out["runtime"] = cloud_runtime(entry)
    return out


def main(argv: list[str] | None = None) -> int:
    import argparse

    p = argparse.ArgumentParser(description="프로그램 카탈로그 동기화")
    p.add_argument(
        "--bundled-only",
        action="store_true",
        help="javis/ 서브모듈만 스캔 (Git·배포용 — 외부 D:\\ 경로 제외)",
    )
    args = p.parse_args(argv)

    jarvis_root = _pick_jarvis_root(bundled_only=args.bundled_only)

    traffic = _scan_bats(ROOT, source="local", workspace="traffic")
    traffic = _apply_overrides(traffic, TRAFFIC_OVERRIDES)

    javis = _scan_bats(jarvis_root, source="javis", workspace="javis") if jarvis_root.is_dir() else []

    # 웹 허브는 traffic 전용 고정 항목
    hub = {
        "id": "traffic_web_hub",
        "name": "웹 SEO 허브 (현재)",
        "workspace": "traffic",
        "source": "local",
        "launcher": "run.bat",
        "category": "traffic",
        "description": "순위 추적·SEO·블로그 PWA 대시보드",
        "icon": "fa-gauge-high",
    }
    if not any(p["launcher"] == "run.bat" for p in traffic):
        traffic.insert(0, hub)

    catalog = {
        "version": 1,
        "jarvis_root_hint": str(jarvis_root),
        "jarvis_remote": "https://github.com/FatihMakes/Mark-XXXIX.git",
        "traffic_count": len(traffic),
        "javis_count": len(javis),
        "programs": [_annotate_cloud(p) for p in traffic + javis],
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(catalog, f, ensure_ascii=False, indent=2)

    print(f"Wrote {OUT} - traffic {len(traffic)}, javis {len(javis)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
