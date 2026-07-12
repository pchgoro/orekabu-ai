"""Best-effort yfinance earnings date provider."""

from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Any, Iterable

import pandas as pd
import yfinance as yf

from services.earnings import japan_today
from services.earnings_providers.base import EarningsFetchResult
from utils.validators import normalize_ticker

logger = logging.getLogger(__name__)


class YFinanceEarningsProvider:
    """Normalize unstable yfinance calendar shapes behind one boundary."""

    name = "yfinance"

    def fetch_next_earnings(self, ticker: str) -> EarningsFetchResult:
        """Return future candidates when available, otherwise a safe failure/past result."""
        normalized = normalize_ticker(ticker)
        retrieved_at = datetime.now().astimezone().isoformat(timespec="seconds")
        try:
            obj = yf.Ticker(normalized)
            dates = _dates_from_calendar(getattr(obj, "calendar", None))
            if not dates:
                try:
                    dates = _dates_from_earnings_frame(obj.get_earnings_dates(limit=8))
                except Exception:
                    logger.exception("yfinance決算履歴取得失敗 ticker=%s", normalized)
            unique = tuple(sorted(set(dates)))
            if not unique:
                return EarningsFetchResult(
                    ticker=normalized, source_name=self.name, source_reference=f"yfinance:{normalized}",
                    retrieved_at=retrieved_at, confidence="low", error_code="empty_data",
                    error_message="決算予定日を取得できませんでした。", raw_payload_summary="候補日0件",
                )
            future = tuple(item for item in unique if item >= japan_today())
            selected = future[0] if future else unique[-1]
            candidates = future if future else (selected,)
            return EarningsFetchResult(
                ticker=normalized, earnings_date=selected, candidate_dates=candidates,
                source_name=self.name, source_reference=f"yfinance:{normalized}",
                retrieved_at=retrieved_at, confidence="low",
                raw_payload_summary=f"候補日{len(unique)}件、未来日{len(future)}件",
            )
        except Exception as exc:
            logger.exception("yfinance決算候補取得失敗 ticker=%s", normalized)
            return EarningsFetchResult(
                ticker=normalized, source_name=self.name, source_reference=f"yfinance:{normalized}",
                retrieved_at=retrieved_at, confidence="low", error_code=_error_code(exc),
                error_message="外部サービスから決算予定日を取得できませんでした。",
                raw_payload_summary=type(exc).__name__,
            )


def _dates_from_calendar(value: Any) -> list[date]:
    """Extract only earnings-date fields from common calendar shapes."""
    if value is None:
        return []
    candidates: Any = None
    if isinstance(value, dict):
        candidates = value.get("Earnings Date") or value.get("earningsDate")
    elif isinstance(value, pd.DataFrame) and not value.empty:
        if "Earnings Date" in value.index:
            candidates = value.loc["Earnings Date"].tolist()
        elif "Earnings Date" in value.columns:
            candidates = value["Earnings Date"].tolist()
    return _normalize_dates(candidates)


def _dates_from_earnings_frame(value: Any) -> list[date]:
    """Extract dates from yfinance earnings history without leaking its shape outward."""
    if value is None or not isinstance(value, pd.DataFrame) or value.empty:
        return []
    dates: list[date] = []
    for item in value.index.tolist():
        parsed = _as_date(item)
        if parsed:
            dates.append(parsed)
    return dates


def _normalize_dates(value: Any) -> list[date]:
    if value is None:
        return []
    values: Iterable[Any] = value if isinstance(value, (list, tuple, set, pd.Series)) else [value]
    return [parsed for item in values if (parsed := _as_date(item)) is not None]


def _as_date(value: Any) -> date | None:
    if value is None or value is pd.NaT:
        return None
    try:
        timestamp = pd.Timestamp(value)
        if pd.isna(timestamp):
            return None
        return timestamp.date()
    except (TypeError, ValueError, OverflowError):
        return None


def _error_code(exc: Exception) -> str:
    text = str(exc).lower()
    if "429" in text or "rate" in text:
        return "rate_limited"
    if "timeout" in text:
        return "timeout"
    return "network_error"
