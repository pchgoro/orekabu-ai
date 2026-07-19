"""Shared visual language for status, priority, sections, and empty states."""

from __future__ import annotations

from html import escape
from typing import Any

import streamlit as st

PRIORITY_LABELS = {
    "urgent": "今すぐ見る",
    "today": "今日見る",
    "later": "あとで見る",
}


def priority_level(priority: Any) -> str:
    """Map an explainable task priority to the shared three-level vocabulary."""
    try:
        value = int(priority)
    except (TypeError, ValueError):
        value = 99
    if value <= 3:
        return "urgent"
    if value <= 7:
        return "today"
    return "later"


def render_priority_badge(level: str) -> None:
    """Render priority using both text and the shared color system."""
    normalized = level if level in PRIORITY_LABELS else "later"
    st.markdown(
        f'<span class="orekabu-badge orekabu-{normalized}">'
        f'{PRIORITY_LABELS[normalized]}</span>',
        unsafe_allow_html=True,
    )


def render_status_badge(label: str, state: str = "info") -> None:
    """Render a generic state badge without relying on color alone."""
    normalized = status_tone(state)
    st.markdown(
        f'<span class="orekabu-badge orekabu-{normalized}">{label}</span>',
        unsafe_allow_html=True,
    )


def status_tone(state: str) -> str:
    """Normalize legacy states to the Japanese-stock theme vocabulary."""
    aliases = {"danger": "warning", "success": "info"}
    normalized = aliases.get(state, state)
    return normalized if normalized in {"positive", "negative", "warning", "info", "muted"} else "info"


def market_direction(value: Any) -> str:
    """Return the Japanese-market color direction for one numeric value."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "muted"
    if number > 0:
        return "positive"
    if number < 0:
        return "negative"
    return "muted"


def render_market_metric(label: str, display_value: str, numeric_value: Any) -> None:
    """Render a market value using red for gains and green for losses."""
    direction = market_direction(numeric_value)
    st.markdown(
        '<div class="orekabu-market-metric">'
        f'<div class="orekabu-market-label">{escape(str(label))}</div>'
        f'<div class="orekabu-market-value orekabu-text-{direction}">'
        f'{escape(str(display_value))}</div></div>',
        unsafe_allow_html=True,
    )


def render_market_value(label: str, display_value: str, numeric_value: Any) -> None:
    """Render an inline signed value with an explicit label."""
    direction = market_direction(numeric_value)
    st.markdown(
        f'<span class="orekabu-market-inline">{escape(str(label))}: '
        f'<strong class="orekabu-text-{direction}">{escape(str(display_value))}</strong></span>',
        unsafe_allow_html=True,
    )


def section_header(title: str, description: str = "") -> None:
    """Render a consistent operational section heading."""
    st.subheader(title)
    if description:
        st.caption(description)


def empty_state(message: str) -> None:
    """Render a quiet, consistent empty state."""
    st.markdown(f'<div class="orekabu-empty">{message}</div>', unsafe_allow_html=True)


def density_padding(density: str) -> str:
    """Return card padding for a validated display density."""
    return {"コンパクト": "0.65rem", "標準": "0.9rem", "ゆったり": "1.2rem"}.get(
        density, "0.9rem"
    )
