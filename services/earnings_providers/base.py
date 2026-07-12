"""Provider-neutral earnings fetch contracts."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Protocol


@dataclass(frozen=True)
class EarningsFetchResult:
    """Normalized result returned by an earnings provider."""

    ticker: str
    earnings_date: date | None = None
    candidate_dates: tuple[date, ...] = field(default_factory=tuple)
    announcement_time: str = ""
    fiscal_year: int | None = None
    fiscal_quarter: str = "未設定"
    source_name: str = ""
    source_reference: str = ""
    retrieved_at: str = ""
    confidence: str = "unknown"
    raw_payload_summary: str = ""
    error_code: str = ""
    error_message: str = ""

    @property
    def succeeded(self) -> bool:
        """Return whether at least one candidate date was normalized."""
        return not self.error_code and bool(self.candidate_dates or self.earnings_date)


class EarningsProvider(Protocol):
    """Interface for replaceable earnings date providers."""

    name: str

    def fetch_next_earnings(self, ticker: str) -> EarningsFetchResult:
        """Fetch and normalize candidate earnings dates for one ticker."""
        ...
