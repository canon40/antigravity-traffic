# -*- coding: utf-8 -*-
"""키워드별 순위 추이·TOP10 진입 일수·목표 순위 ETA."""
from __future__ import annotations

from datetime import datetime

from rank_tracker import NOT_FOUND_RANK, get_history, normalize_rank

GOAL_RANKS = (10, 50, 100)
LEGACY_NOT_FOUND = 999


def _parse_dt(raw: str) -> datetime | None:
    if not raw:
        return None
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(str(raw).strip()[:16], fmt)
        except ValueError:
            continue
    return None


def _parse_rank(raw) -> int | None:
    if raw is None or raw == "" or raw == "-":
        return None
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return None
    if value >= NOT_FOUND_RANK or value == LEGACY_NOT_FOUND:
        return None
    if value < 1:
        return None
    return value


def keyword_history_series(keyword: str, store_name: str, history: list | None = None) -> list[dict]:
    """키워드별 시간순 순위 시계열."""
    history = history if history is not None else get_history()
    rows = [
        r
        for r in history
        if (r.get("키워드") or r.get("keyword")) == keyword
        and (r.get("스토어명") or r.get("store_name") or "") == (store_name or "")
    ]
    series: list[dict] = []
    for row in rows:
        dt = _parse_dt(row.get("날짜") or row.get("date") or "")
        rank = _parse_rank(row.get("순위") if "순위" in row else row.get("rank"))
        if not dt:
            continue
        series.append({"at": dt.isoformat(), "rank": rank, "not_found": rank is None})
    series.sort(key=lambda x: x["at"])
    return series


def days_to_first_top10(keyword: str, store_name: str, history: list | None = None) -> int | None:
    """첫 추적일부터 TOP10 최초 진입까지 소요 일수. 미진입 시 None."""
    series = keyword_history_series(keyword, store_name, history)
    real = [(s["at"], s["rank"]) for s in series if s.get("rank") is not None]
    if not real:
        return None
    first_dt = _parse_dt(real[0][0])
    if not first_dt:
        return None
    for at, rank in real:
        if rank is not None and 1 <= rank <= 10:
            entered = _parse_dt(at)
            if entered:
                return max(0, (entered.date() - first_dt.date()).days)
    return None


def top10_entry_label(keyword: str, store_name: str, current_rank, history: list | None = None) -> str | None:
    """현재 TOP10이면 진입 소요 일수 문구."""
    real = normalize_rank(current_rank)
    if real is None or real > 10:
        return None
    days = days_to_first_top10(keyword, store_name, history)
    if days is None:
        return "TOP10 진입"
    if days == 0:
        return "TOP10 · 당일 진입"
    return f"TOP10 · {days}일 만에 진입"


def project_days_to_target(
    current_rank,
    keyword: str,
    store_name: str,
    target: int,
    history: list | None = None,
) -> int | None:
    """최근 추이 기반 목표 순위 도달 예상 일수."""
    real = normalize_rank(current_rank)
    if real is None:
        return None
    if real <= target:
        return 0
    series = keyword_history_series(keyword, store_name, history)
    points = [(s["at"], s["rank"]) for s in series if s.get("rank") is not None]
    if len(points) < 2:
        return None
    first_at, first_rank = points[0]
    last_at, last_rank = points[-1]
    first_dt = _parse_dt(first_at)
    last_dt = _parse_dt(last_at)
    if not first_dt or not last_dt:
        return None
    span_days = max(1, (last_dt.date() - first_dt.date()).days)
    improvement = first_rank - last_rank
    if improvement <= 0:
        return None
    remaining = last_rank - target
    if remaining <= 0:
        return 0
    return max(1, round(span_days * remaining / improvement))


def rank_goal_progress(current_rank, *, max_depth: int = 10000) -> dict:
    """TOP100/50/10 목표 대비 진행률 (0~100)."""
    real = normalize_rank(current_rank)
    if real is None:
        return {
            "top100": 0,
            "top50": 0,
            "top10": 0,
            "scale_max": max_depth,
            "current": None,
        }
    scale = max(max_depth, real, 100)
    def pct(goal: int) -> float:
        if real <= goal:
            return 100.0
        return max(0.0, min(99.9, round(100 * (1 - (real - goal) / (scale - goal)), 1)))
    return {
        "top100": pct(100),
        "top50": pct(50),
        "top10": pct(10),
        "scale_max": scale,
        "current": real,
    }


def enrich_keyword_summary(summary: list[dict], history: list | None = None) -> list[dict]:
    """대시보드용 — ETA·진행률·TOP10 진입일."""
    history = history if history is not None else get_history()
    enriched: list[dict] = []
    for item in summary:
        kw = item.get("keyword") or ""
        store = item.get("store_name") or ""
        rank = item.get("last_rank")
        goals = rank_goal_progress(rank)
        eta: dict[str, int | None] = {}
        for g in GOAL_RANKS:
            eta[f"eta_top{g}"] = project_days_to_target(rank, kw, store, g, history)
        top10_days = days_to_first_top10(kw, store, history)
        trend = _rank_trend(kw, store, history)
        enriched.append({
            **item,
            "goal_progress": goals,
            "eta_top10": eta.get("eta_top10"),
            "eta_top50": eta.get("eta_top50"),
            "eta_top100": eta.get("eta_top100"),
            "top10_entry_days": top10_days,
            "top10_entry_label": top10_entry_label(kw, store, rank, history),
            "rank_trend": trend,
            "history_points": len(keyword_history_series(kw, store, history)),
        })
    return enriched


def _rank_trend(keyword: str, store_name: str, history: list | None) -> str:
    series = keyword_history_series(keyword, store_name, history)
    ranks = [s["rank"] for s in series if s.get("rank") is not None]
    if len(ranks) < 2:
        return "flat"
    if ranks[-1] < ranks[-2]:
        return "up"
    if ranks[-1] > ranks[-2]:
        return "down"
    return "flat"


def build_progress_board(config: dict | None = None, summary: list[dict] | None = None) -> dict:
    """API용 키워드 진행 보드."""
    from rank_tracker import get_keyword_rank_summary, load_config, rank_depth_limit

    config = config or load_config()
    base = summary or get_keyword_rank_summary(config)
    items = enrich_keyword_summary(base)
    in_top10 = [i for i in items if normalize_rank(i.get("last_rank")) is not None and normalize_rank(i.get("last_rank")) <= 10]
    improving = [i for i in items if i.get("rank_trend") == "up"]
    return {
        "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "scan_depth": rank_depth_limit(config=config),
        "total": len(items),
        "in_top10": len(in_top10),
        "improving": len(improving),
        "items": items,
    }
