"""Pure notification candidates; this module never sends external notifications."""

from __future__ import annotations

from typing import Any


def build_notification_candidates(
    *,
    buy_watch_rows: list[dict[str, Any]] | None = None,
    earnings_rows: list[dict[str, Any]] | None = None,
    score_rows: list[dict[str, Any]] | None = None,
    volume_threshold: float = 2.0,
    score_jump_threshold: float = 10.0,
) -> list[dict[str, Any]]:
    """Build explainable, deduplicated candidates without sending or persisting them."""
    candidates: list[dict[str, Any]] = []

    for row in buy_watch_rows or []:
        status = row.get("buy_watch_status")
        if status in {"到達", "接近中"}:
            _append(candidates, row, "buy_watch", f"買い検討ライン{status}", status)

    for row in earnings_rows or []:
        days = row.get("days_until")
        if isinstance(days, int) and 0 <= days <= 3:
            _append(candidates, row, "earnings", "決算接近", f"あと{days}日")

    for row in score_rows or []:
        volume = _number(row.get("volume_ratio"))
        if volume is not None and volume >= volume_threshold:
            _append(candidates, row, "volume", "出来高急増", f"{volume:g}倍")
        score = _number(row.get("score"))
        previous = _number(row.get("prev_score"))
        if score is not None and previous is not None and score - previous >= score_jump_threshold:
            _append(candidates, row, "score", "スコア急上昇", f"+{score - previous:g}点")

    return candidates


def _append(candidates: list[dict[str, Any]], row: dict[str, Any], kind: str, title: str, reason: str) -> None:
    ticker = str(row.get("ticker") or "").strip()
    if not ticker:
        return
    candidates.append({
        "ticker": ticker,
        "company_name": str(row.get("company_name") or ticker),
        "kind": kind,
        "title": title,
        "reason": reason,
        "dedupe_key": f"{kind}:{ticker}",
        "priority": {"buy_watch": 0, "earnings": 1, "volume": 2, "score": 3}[kind],
    })


def _number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number == number else None
