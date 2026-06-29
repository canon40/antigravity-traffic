"""트래픽 방문 URL — 미진입 키워드 우선, 순위 진입 키워드 유지."""

from __future__ import annotations

from typing import Any


def collect_traffic_urls(config: dict[str, Any]) -> list[str]:
    """중복 제거된 방문 URL 목록 (폴백용)."""
    seen: set[str] = set()
    urls: list[str] = []

    def add(url: str) -> None:
        u = (url or "").strip()
        if u.startswith(("http://", "https://")) and u not in seen:
            seen.add(u)
            urls.append(u)

    product_by_id: dict[str, str] = {}
    for product in config.get("products") or []:
        if not isinstance(product, dict):
            continue
        pid = str(product.get("id") or "").strip()
        purl = (product.get("url") or "").strip()
        if pid and purl:
            product_by_id[pid] = purl

    for item in config.get("priority_keywords") or []:
        if not isinstance(item, dict):
            continue
        pid = str(item.get("product_id") or "").strip()
        if pid and pid in product_by_id:
            add(product_by_id[pid])
        elif item.get("url"):
            add(str(item["url"]))

    for product in config.get("products") or []:
        if isinstance(product, dict):
            add(str(product.get("url") or ""))

    for row in config.get("product_listings") or []:
        if isinstance(row, dict):
            add(str(row.get("url") or ""))

    for item in config.get("product_urls") or []:
        if isinstance(item, str):
            add(item)
        elif isinstance(item, dict):
            add(str(item.get("url") or ""))

    if not urls:
        store = (config.get("store_name") or "nanumlab").replace(" ", "")
        add(f"https://smartstore.naver.com/{store}")
    return urls


def label_for_url(config: dict[str, Any], url: str) -> str:
    for product in config.get("products") or []:
        if not isinstance(product, dict):
            continue
        if (product.get("url") or "").strip() == url.strip():
            name = (product.get("name") or "").strip()
            pid = str(product.get("id") or "").strip()
            return name or pid or url
    return url.rstrip("/").split("/")[-1]


def pick_traffic_url(
    config: dict[str, Any],
    state: dict[str, Any],
    *,
    advance: bool = True,
) -> tuple[str, dict[str, Any]]:
    """순위 기반 트래픽 대상 선택 (미진입 boost → 유지 maintain)."""
    try:
        from rank_tracker import pick_traffic_target

        picked = pick_traffic_target(config, state)
        url = picked["url"]
        state["last_traffic_product_url"] = url
        state["last_traffic_keyword"] = picked.get("keyword")
        state["last_traffic_mode"] = picked.get("mode")
        state["traffic_referer_url"] = picked.get("referer_url") or "https://m.naver.com/"
        state["traffic_unranked_count"] = picked.get("unranked_count", 0)
        state["traffic_ranked_count"] = picked.get("ranked_count", 0)
        if advance:
            state["traffic_target_index"] = picked.get("next_index", 0)
        return url, state
    except Exception:
        pass

    candidates = collect_traffic_urls(config)
    n = len(candidates)
    offset = int(state.get("traffic_url_offset") or 0) % max(1, n)
    url = candidates[offset]
    if advance and n > 1:
        state["traffic_url_offset"] = (offset + 1) % n
    state["last_traffic_product_url"] = url
    state["traffic_pool_size"] = n
    state["traffic_referer_url"] = "https://m.naver.com/"
    return url, state


def traffic_pool_summary(
    config: dict[str, Any],
    state: dict[str, Any],
) -> dict[str, Any]:
    try:
        from rank_tracker import pick_traffic_target

        picked = pick_traffic_target(config, state)
        return {
            "traffic_pool_size": picked.get("unranked_count", 0) + picked.get("ranked_count", 0),
            "traffic_unranked_count": picked.get("unranked_count", 0),
            "traffic_ranked_count": picked.get("ranked_count", 0),
            "traffic_next_url": picked.get("url"),
            "traffic_next_label": picked.get("keyword") or picked.get("product_name") or "",
            "traffic_mode": picked.get("mode"),
            "referer_url": picked.get("referer_url"),
        }
    except Exception:
        pass

    candidates = collect_traffic_urls(config)
    n = len(candidates)
    offset = int(state.get("traffic_url_offset") or 0) % max(1, n)
    current = candidates[offset] if candidates else ""
    return {
        "traffic_pool_size": n,
        "traffic_url_offset": offset,
        "traffic_next_url": current,
        "traffic_next_label": label_for_url(config, current) if current else "",
        "traffic_urls": candidates,
    }
