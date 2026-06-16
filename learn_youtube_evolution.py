# -*- coding: utf-8 -*-
"""YouTube 가이드 영상 학습 → 동영상 제작 플레이북 진화."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from shorts_factory.youtube_learner import (  # noqa: E402
    EVOLUTION_PATH,
    learn_from_url,
    load_evolution,
    seed_from_brand,
)


def main() -> int:
    ap = argparse.ArgumentParser(description="YouTube → 동영상 제작 플레이북 진화")
    ap.add_argument("url", nargs="?", help="YouTube URL (없으면 --seed)")
    ap.add_argument("--seed", action="store_true", help="brand.json 참고 영상 일괄 학습")
    ap.add_argument("--status", action="store_true", help="현재 진화 상태만 출력")
    args = ap.parse_args()

    if args.status:
        evo = load_evolution()
        print(json.dumps({
            "generation": evo.get("generation"),
            "learned_videos": len(evo.get("learned_videos") or []),
            "playbook": evo.get("playbook"),
            "path": str(EVOLUTION_PATH),
        }, ensure_ascii=False, indent=2))
        return 0

    if args.seed or not args.url:
        print(">> brand.json 참고 YouTube 영상 일괄 학습...")
        result = seed_from_brand(print)
        evo = result["evolution"]
        print(f"\n완료: gen={evo.get('generation')} / 학습 영상 {len(evo.get('learned_videos') or [])}개")
        print(f"저장: {EVOLUTION_PATH}")
        return 0

    result = learn_from_url(args.url, print)
    evo = result.get("evolution") or load_evolution()
    print(f"\n완료: gen={evo.get('generation')}")
    print(f"저장: {EVOLUTION_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
