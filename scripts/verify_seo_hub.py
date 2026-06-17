# -*- coding: utf-8 -*-
"""SEO · JARVIS 허브 파이프라인 검증 — 로컬·Vercel 시뮬·(선택) 프로덕션 URL."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _check(name: str, ok: bool, detail: str = "") -> dict:
    return {"name": name, "ok": ok, "detail": detail}


def _vercel_deps() -> dict:
    req = ROOT / "requirements-vercel.txt"
    text = req.read_text(encoding="utf-8") if req.is_file() else ""
    need = ("flask", "requests", "beautifulsoup4", "httpx", "python-dotenv")
    missing = [p for p in need if p not in text.lower()]
    return _check(
        "requirements_vercel",
        not missing,
        "ok" if not missing else f"missing: {', '.join(missing)}",
    )


def _bundled_data() -> list[dict]:
    out = []
    for rel in (
        "config.defaults.json",
        "data/rank_hub_state.json",
        "data/rank_history_seed.json",
        "data/programs_catalog.json",
        "templates/index.html",
        "vercel.json",
    ):
        p = ROOT / rel
        out.append(_check(f"file:{rel}", p.is_file(), str(p) if p.is_file() else "없음"))
    return out


def _import_hub(*, vercel: bool, full: bool = False) -> list[dict]:
    os.environ["VERCEL"] = "1" if vercel else ""
    if not vercel and "VERCEL" in os.environ:
        del os.environ["VERCEL"]

    vt = ROOT / "vercel_traffic"
    if vt.is_dir() and str(vt) not in sys.path:
        sys.path.insert(0, str(vt))

    results: list[dict] = []
    try:
        from traffic_session import run_traffic_session  # noqa: F401

        results.append(_check("import_traffic_session", True))
    except Exception as exc:
        results.append(_check("import_traffic_session", False, str(exc)))

    try:
        from app import app  # noqa: F401

        results.append(_check("import_app", True, "VERCEL=1" if vercel else "local"))
    except Exception as exc:
        results.append(_check("import_app", False, str(exc)))
        return results

    from app import app

    routes = [
        ("GET", "/api/health"),
        ("GET", "/api/status"),
        ("GET", "/api/config"),
        ("GET", "/api/history"),
        ("GET", "/api/logs"),
        ("GET", "/api/content/workflows"),
        ("GET", "/api/javis/programs?workspace=traffic"),
        ("GET", "/"),
    ]
    with app.test_client() as client:
        for method, path in routes:
            fn = getattr(client, method.lower())
            resp = fn(path)
            ok = resp.status_code < 400
            body = resp.get_data(as_text=True)[:120]
            results.append(_check(f"route:{path}", ok, f"{resp.status_code} {body}"))

        # 콘텐츠 생성 (네트워크 없음)
        gen = client.post(
            "/api/content/generate",
            json={"workflow": "blog_review", "keyword": "테스트키워드", "product_name": "퍼마코트"},
        )
        gen_ok = gen.status_code == 200
        gen_body = {}
        try:
            gen_body = gen.get_json() or {}
        except Exception:
            pass
        results.append(
            _check(
                "post:content_generate",
                gen_ok and gen_body.get("success"),
                f"{gen.status_code} success={gen_body.get('success')}",
            )
        )

        # JARVIS 클라우드 실행 (연동 점검)
        launch = client.post("/api/javis/launch", json={"id": "traffic_javis_connect"})
        launch_body = launch.get_json() or {}
        results.append(
            _check(
                "post:javis_launch_cloud",
                launch.status_code == 200 and launch_body.get("success"),
                f"{launch.status_code} cloud={launch_body.get('cloud')}",
            )
        )

        # Cron (네이버 호출 — --full 일 때만)
        if full:
            cron = client.get("/api/cron/track")
            results.append(_check("cron:track", cron.status_code == 200, f"HTTP {cron.status_code}"))
        else:
            results.append(_check("cron:track", True, "skipped (use --full)"))

    try:
        from rank_tracker import load_config

        cfg = load_config()
        kw = len(cfg.get("keywords") or [])
        pri = len(cfg.get("priority_keywords") or [])
        results.append(
            _check(
                "load_config",
                kw > 0 or pri > 0,
                f"keywords={kw}, priority={pri}",
            )
        )
    except Exception as exc:
        results.append(_check("load_config", False, str(exc)))

    return results


def _probe_url(base: str) -> list[dict]:
    base = base.rstrip("/")
    out: list[dict] = []
    for path in ("/api/health", "/api/status"):
        url = f"{base}{path}"
        try:
            with urlopen(url, timeout=25) as resp:
                code = resp.status
                snippet = resp.read(200).decode("utf-8", errors="replace")
            out.append(_check(f"live:{path}", code == 200, f"{code} {snippet[:80]}"))
        except HTTPError as e:
            out.append(_check(f"live:{path}", False, f"HTTP {e.code}"))
        except URLError as e:
            out.append(_check(f"live:{path}", False, str(e.reason)))
    return out


def _print_report(results: list[dict]) -> None:
    for r in results:
        mark = "OK" if r["ok"] else "FAIL"
        line = f"  [{mark}] {r['name']}"
        if r.get("detail"):
            line += f" — {r['detail']}"
        print(line)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="SEO 허브 파이프라인 검증")
    p.add_argument("--json", action="store_true")
    p.add_argument("--url", default="", help="배포 URL (예: https://www.permacoat.shop)")
    p.add_argument("--full", action="store_true", help="Cron·네이버 순위 추적 포함 (느림)")
    p.add_argument("--vercel", action="store_true", help="Vercel 런타임/연동까지 함께 검증 (외부 의존성 포함)")
    args = p.parse_args(argv)

    results: list[dict] = [*_bundled_data()]
    if args.vercel:
        results.insert(0, _vercel_deps())
    results.extend(_import_hub(vercel=args.vercel, full=args.full))
    if args.url:
        results.extend(_probe_url(args.url))

    critical = [
        r
        for r in results
        if r["name"].startswith(("import_app", "route:/api/status", "live:/api/status"))
        or (args.vercel and r["name"].startswith("requirements_"))
    ]
    ok = all(r["ok"] for r in critical)

    if args.json:
        print(json.dumps({"ok": ok, "results": results}, ensure_ascii=False, indent=2))
        return 0 if ok else 1

    print("=" * 60)
    print("  SEO · JARVIS 허브 파이프라인 검증")
    print("=" * 60)
    _print_report(results)
    print("-" * 60)
    if ok:
        print("  핵심 검증: 통과")
        if args.url:
            print(f"  프로덕션 ({args.url}): 위 live:* 항목 확인")
        else:
            print("  배포 후: python scripts/verify_seo_hub.py --url https://YOUR-DOMAIN")
    else:
        print("  핵심 검증: 실패 — FAIL 항목 수정 후 재실행")
    print("=" * 60)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
