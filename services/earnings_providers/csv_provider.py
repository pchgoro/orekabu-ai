"""CSV row normalization for provider-compatible candidate input."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from services.earnings import parse_earnings_date
from services.earnings_providers.base import EarningsFetchResult
from utils.validators import normalize_ticker


def result_from_csv_row(row: dict[str, Any]) -> EarningsFetchResult:
    """Normalize one CSV row into a provider result."""
    ticker = normalize_ticker(row.get("ticker"))
    event_date = parse_earnings_date(row.get("earnings_date"), allow_empty=False)
    fiscal_year = int(row["fiscal_year"]) if str(row.get("fiscal_year") or "").strip() else None
    return EarningsFetchResult(
        ticker=ticker,
        earnings_date=event_date,
        candidate_dates=(event_date,),
        announcement_time=str(row.get("announcement_time") or "").strip(),
        fiscal_year=fiscal_year,
        fiscal_quarter=str(row.get("fiscal_quarter") or "未設定").strip(),
        source_name=str(row.get("source_name") or "CSV").strip(),
        source_reference=str(row.get("source_reference") or "").strip(),
        retrieved_at=datetime.now().astimezone().isoformat(timespec="seconds"),
        confidence=str(row.get("confidence") or "unknown").strip().lower(),
        raw_payload_summary=str(row.get("memo") or "").strip()[:500],
    )
