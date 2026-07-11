"""Input validation and normalization helpers."""

from __future__ import annotations

import math
import re
from typing import Any

from utils.constants import CATEGORIES

TICKER_RE = re.compile(r"^(?:\d{4}|\d{3}[A-Z])(?:\.T)?$")


def normalize_ticker(value: Any) -> str:
    """Normalize Japanese stock tickers to the yfinance .T suffix format."""
    ticker = str(value or "").strip().upper()
    if not TICKER_RE.match(ticker):
        raise ValueError("銘柄コードは数字4桁、または数字3桁と英字1文字で入力してください。")
    return ticker if ticker.endswith(".T") else f"{ticker}.T"


def validate_category(value: str) -> str:
    """Validate stock category."""
    if value not in CATEGORIES:
        raise ValueError("分類が不正です。")
    return value


def validate_non_negative_float(value: Any, field_name: str) -> float:
    """Validate a non-negative float; empty values are treated as zero."""
    if value in (None, ""):
        return 0.0
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name}は0以上の数値で入力してください。") from exc
    if math.isnan(number) or math.isinf(number) or number < 0:
        raise ValueError(f"{field_name}は0以上の数値で入力してください。")
    return number


def validate_non_negative_int(value: Any, field_name: str) -> int:
    """Validate a non-negative integer; empty values are treated as zero."""
    if value in (None, ""):
        return 0
    try:
        number = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name}は0以上の整数で入力してください。") from exc
    if number < 0:
        raise ValueError(f"{field_name}は0以上の整数で入力してください。")
    return number


def parse_bool(value: Any) -> bool:
    """Parse common CSV boolean values."""
    if isinstance(value, bool):
        return value
    text = str(value or "").strip().lower()
    return text in {"1", "true", "yes", "y", "保有", "保有株"}


def validate_stock_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Validate and normalize a stock payload for DB writes."""
    normalized = {
        "ticker": normalize_ticker(payload.get("ticker")),
        "company_name": str(payload.get("company_name") or "").strip(),
        "category": validate_category(str(payload.get("category") or "監視銘柄")),
        "is_holding": bool(payload.get("is_holding", False)),
        "shares": validate_non_negative_int(payload.get("shares"), "保有株数"),
        "average_price": validate_non_negative_float(payload.get("average_price"), "平均取得単価"),
        "buy_watch_price": validate_non_negative_float(payload.get("buy_watch_price"), "買い検討価格"),
        "memo": str(payload.get("memo") or "").strip(),
    }
    if normalized["is_holding"] and normalized["category"] != "保有株":
        normalized["category"] = "保有株"
    if not normalized["company_name"]:
        normalized["company_name"] = normalized["ticker"]
    return normalized
