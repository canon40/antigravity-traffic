# -*- coding: utf-8 -*-
"""JARVIS·Traffic run_*.bat 스캔 → data/programs_catalog.json (Git 커밋용)."""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

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
    "run_gui.bat": {
        "id": "traffic_autoblog_gui",
        "name": "Autoblog GUI",
        "category": "blog",
        "description": "네이버·티스토리 블로그 자동화 데스크톱 GUI",
        "icon": "fa-window-maximize",
    },
    "run_seo_pipeline.bat": {
        "id": "traffic_seo_pipeline",
        "name": "SEO 파이프라인",
        "category": "seo",
        "description": "키워드·순위·콘텐츠 일괄 SEO 작업",
        "icon": "fa-diagram-project",
    },
    "run_content_factory.bat": {
        "id": "traffic_content_factory",
        "name": "콘텐츠 팩토리",
        "category": "blog",
        "description": "상품·블로그용 콘텐츠 생성 파이프라인",
        "icon": "fa-industry",
    },
    "run_javis_connect.bat": {
        "id": "traffic_javis_connect",
        "name": "JARVIS 연동 점검",
        "category": "ops",
        "description": "Supabase·환경변수 동기화 및 연결 확인",
        "icon": "fa-plug",
    },
    "run_programs_check.bat": {
        "id": "traffic_programs_check",
        "name": "프로그램 점검",
        "category": "ops",
        "description": "Python·Ollama·Playwright·브리지 순차 점검",
        "icon": "fa-stethoscope",
    },
    "run_shorts_factory.bat": {
        "id": "traffic_shorts_factory",
        "name": "숏츠 팩토리 (로컬)",
        "category": "video",
        "description": "쇼핑·숏츠 영상 제작 (로컬 연동)",
        "icon": "fa-film",
    },
    "run_rank_check.bat": {
        "id": "traffic_rank_check",
        "name": "순위 1회 점검",
        "category": "seo",
        "description": "CLI 순위 추적 1회 실행",
        "icon": "fa-ranking-star",
    },
    "run_monitor_auto.bat": {
        "id": "traffic_monitor_auto",
        "name": "순위 자동 모니터 (PC)",
        "category": "seo",
        "description": "로컬 PC 24시간 순위 모니터링",
        "icon": "fa-clock",
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


def _pick_jarvis_root() -> Path:
    bundled = ROOT / "javis"
    external = Path(os.environ.get("JARVIS_ROOT", r"D:\@code\javis"))
    bundled_count = len(list(bundled.glob("run_*.bat"))) if bundled.is_dir() else 0
    external_count = len(list(external.glob("run_*.bat"))) if external.is_dir() else 0
    if external_count >= bundled_count and external_count > 0:
        return external
    if bundled_count > 0:
        return bundled
    return external if external.is_dir() else bundled


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


def main() -> int:
    jarvis_root = _pick_jarvis_root()

    traffic = _scan_bats(ROOT, source="local", workspace="traffic")
    traffic = _apply_overrides(traffic, TRAFFIC_OVERRIDES)

    javis = _scan_bats(jarvis_root, source="javis", workspace="javis")

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

    print(f"Wrote {OUT} — traffic {len(traffic)}, javis {len(javis)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
