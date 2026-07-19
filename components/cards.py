"""Reusable Streamlit card-like metric helpers."""

from __future__ import annotations

from typing import Any

import streamlit as st

from components.ui import render_market_metric
from utils.formatters import fmt_percent, fmt_price, fmt_signed_price


def summary_metrics(stocks: list[dict[str, Any]], rows: list[dict[str, Any]], mobile: bool = False) -> None:
    """Render summary metrics at the top of pages."""
    holdings = [row for row in rows if row.get("is_holding")]
    watching = [stock for stock in stocks if not stock.get("is_holding")]
    market_value = sum(float(row.get("market_value") or 0) for row in holdings)
    profit = sum(float(row.get("profit") or 0) for row in holdings)
    cost = sum(float(row.get("average_price") or 0) * int(row.get("shares") or 0) for row in holdings)
    profit_pct = (profit / cost * 100) if cost else None
    metrics = [("登録銘柄数", len(stocks)), ("保有銘柄数", len(holdings)), ("監視銘柄数", len(watching)), ("評価額合計", fmt_price(market_value))]
    cols = st.columns(2 if mobile else 6)
    for index, (label, value) in enumerate(metrics):
        cols[index % len(cols)].metric(label, value)
    with cols[4 % len(cols)]:
        render_market_metric("評価損益合計", fmt_signed_price(profit), profit)
    with cols[5 % len(cols)]:
        render_market_metric("評価損益率", fmt_percent(profit_pct), profit_pct)


def holding_metrics(rows: list[dict[str, Any]]) -> None:
    """Render holding-only metrics."""
    market_value = sum(float(row.get("market_value") or 0) for row in rows)
    profit = sum(float(row.get("profit") or 0) for row in rows)
    cost = sum(float(row.get("average_price") or 0) * int(row.get("shares") or 0) for row in rows)
    profit_pct = (profit / cost * 100) if cost else None
    cols = st.columns(3)
    cols[0].metric("評価額合計", fmt_price(market_value))
    with cols[1]:
        render_market_metric("評価損益合計", fmt_signed_price(profit), profit)
    with cols[2]:
        render_market_metric("評価損益率", fmt_percent(profit_pct), profit_pct)


def earnings_metrics(summary: dict[str, int]) -> None:
    """Render earnings proximity counters."""
    cols = st.columns(4)
    cols[0].metric("本日決算", summary.get("today", 0))
    cols[1].metric("7日以内", summary.get("within_7", 0))
    cols[2].metric("14日以内", summary.get("within_14", 0))
    cols[3].metric("日付未確認", summary.get("unconfirmed", 0))
