# -*- coding: utf-8 -*-
"""login2 .env 의 Supabase·경로 설정을 JARVIS .env 에 병합."""

from __future__ import annotations

import os
from pathlib import Path

LOGIN2_ROOT = Path(__file__).resolve().parent
JARVIS_ROOT = Path(os.environ.get("JARVIS_ROOT", r"D:\@code\javis"))

SYNC_KEYS = (
    "SUPABASE_URL",
    "SUPABASE_ANON_KEY",
    "SUPABASE_KEY",
    "SUPABASE_SERVICE_KEY",
    "STORE_KEYWORDS_TABLE",
    "CANON_AUTOBLOG_PATH",
    "CANON_AUTOBLOG_URL",
    "CANON_AUTOBLOG_PORT",
)


def _parse_env(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if not path.is_file():
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip().startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        out[k.strip()] = v.strip()
    return out


def _upsert_env_file(path: Path, updates: dict[str, str]) -> list[str]:
    changed: list[str] = []
    lines: list[str] = []
    if path.is_file():
        lines = path.read_text(encoding="utf-8").splitlines()

    index: dict[str, int] = {}
    for i, line in enumerate(lines):
        if "=" in line and not line.strip().startswith("#"):
            k = line.split("=", 1)[0].strip()
            index[k] = i

    for key, val in updates.items():
        if not val:
            continue
        new_line = f"{key}={val}"
        if key in index:
            if lines[index[key]] != new_line:
                lines[index[key]] = new_line
                changed.append(key)
        else:
            if lines and lines[-1].strip():
                lines.append("")
            if not any("canon4040 Autoblog" in ln for ln in lines):
                lines.append("# --- canon4040 Autoblog / login2 연동 ---")
            lines.append(new_line)
            changed.append(key)

    if changed:
        path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    return changed


def main() -> int:
    login_env = _parse_env(LOGIN2_ROOT / ".env")
    javis_env_path = JARVIS_ROOT / ".env"
    if not javis_env_path.is_file():
        print(f"[XX] JARVIS .env 없음: {javis_env_path}")
        return 1

    updates: dict[str, str] = {}
    for key in SYNC_KEYS:
        if key in login_env and login_env[key]:
            updates[key] = login_env[key]

    updates.setdefault("CANON_AUTOBLOG_PATH", str(LOGIN2_ROOT))
    updates.setdefault("CANON_AUTOBLOG_URL", "http://127.0.0.1:8790")
    updates.setdefault("CANON_AUTOBLOG_PORT", "8790")

    changed = _upsert_env_file(javis_env_path, updates)
    login_changed = _upsert_env_file(LOGIN2_ROOT / ".env", {"JARVIS_ROOT": str(JARVIS_ROOT)})

    print("JARVIS .env 병합:", javis_env_path)
    if changed:
        print("  갱신:", ", ".join(changed))
    else:
        print("  Supabase·경로 키 이미 최신")

    if login_changed:
        print("login2 .env 갱신:", ", ".join(login_changed))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
