"""Display format helpers that avoid leaking raw NaN/None values."""

from __future__ import annotations

import math
from typing import Any


def is_missing(value: Any) -> bool:
    """Return True when a value should be shown as missing data."""
    if value is None:
        return True
    try:
        return not math.isfinite(float(value))
    except (TypeError, ValueError, OverflowError):
        return True


def fmt_price(value: Any) -> str:
    """Format a yen price with thousands separators."""
    if is_missing(value):
        return "データなし"
    return f"{float(value):,.0f}"


def fmt_signed_price(value: Any) -> str:
    """Format a signed yen value."""
    if is_missing(value):
        return "データなし"
    return f"{float(value):+,.0f}"


def fmt_percent(value: Any) -> str:
    """Format a percentage."""
    if is_missing(value):
        return "データなし"
    return f"{float(value):.2f}%"


def fmt_signed_percent(value: Any) -> str:
    """Format a signed percentage."""
    if is_missing(value):
        return "データなし"
    return f"{float(value):+.2f}%"


def fmt_number(value: Any, digits: int = 2) -> str:
    """Format a generic number."""
    if is_missing(value):
        return "データなし"
    return f"{float(value):,.{digits}f}"
