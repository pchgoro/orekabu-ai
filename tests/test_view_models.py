"""Tests for page view-model helpers."""

from __future__ import annotations

from services.view_models import build_buy_watch_rows, sort_watchlist


def test_buy_watch_status_and_sorting() -> None:
    rows = [
        {"ticker": "A", "current_price": 104, "buy_watch_price": 100, "score": 50},
        {"ticker": "B", "current_price": 100, "buy_watch_price": 100, "score": 50},
        {"ticker": "C", "current_price": 102, "buy_watch_price": 100, "score": 50},
    ]
    result = build_buy_watch_rows(rows, near_percent=3)
    assert [row["buy_watch_status"] for row in result] == ["到達", "接近中", "未到達"]
    assert [row["ticker"] for row in result] == ["B", "C", "A"]


def test_watchlist_sort_score() -> None:
    rows = [{"ticker": "A", "score": 50}, {"ticker": "B", "score": 80}]
    assert [row["ticker"] for row in sort_watchlist(rows, "スコア順")] == ["B", "A"]
