"""View-model helpers for page sorting and page-specific derived rows."""

from __future__ import annotations

from typing import Any

BUY_WATCH_STATUS_ORDER = {"到達": 0, "接近中": 1, "未到達": 2, "データなし": 9}


def filter_holdings(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return holding rows."""
    return [row for row in rows if row.get("is_holding")]


def filter_watchlist(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return non-holding rows."""
    return [row for row in rows if not row.get("is_holding")]


def sort_watchlist(rows: list[dict[str, Any]], sort_label: str) -> list[dict[str, Any]]:
    """Sort watchlist rows by a user-facing label."""
    sort_map = {
        "スコア順": ("score", True),
        "RSI昇順": ("RSI14", False),
        "RSI降順": ("RSI14", True),
        "下落率順": ("DROP_FROM_HIGH_60", False),
        "出来高倍率順": ("VOLUME_RATIO", True),
        "銘柄コード順": ("ticker", False),
    }
    key, reverse = sort_map.get(sort_label, ("score", True))
    return sorted(rows, key=lambda row: (row.get(key) is None, row.get(key)), reverse=reverse)


def build_buy_watch_rows(rows: list[dict[str, Any]], near_percent: float) -> list[dict[str, Any]]:
    """Build and sort buy-watch rows from analyzed stock rows."""
    result = []
    for row in rows:
        target = float(row.get("buy_watch_price") or 0)
        if target <= 0:
            continue
        price = row.get("current_price")
        diff = price - target if price is not None else None
        diff_pct = (diff / target * 100) if diff is not None and target else None
        if price is None:
            status = "データなし"
        elif price <= target:
            status = "到達"
        elif diff_pct is not None and diff_pct <= near_percent:
            status = "接近中"
        else:
            status = "未到達"
        result.append(
            {
                **row,
                "buy_watch_diff": diff,
                "buy_watch_diff_pct": diff_pct,
                "buy_watch_status": status,
            }
        )
    return sorted(
        result,
        key=lambda row: (
            BUY_WATCH_STATUS_ORDER.get(row.get("buy_watch_status"), 9),
            abs(row.get("buy_watch_diff_pct")) if row.get("buy_watch_diff_pct") is not None else 999999,
        ),
    )
