"""Optional live yfinance integration test."""

from __future__ import annotations

import pytest

from services.earnings_providers.yfinance_provider import YFinanceEarningsProvider


@pytest.mark.integration
def test_yfinance_live_returns_structured_result() -> None:
    result = YFinanceEarningsProvider().fetch_next_earnings("5801.T")
    assert result.ticker == "5801.T"
    assert result.source_name == "yfinance"
    assert result.retrieved_at
    assert result.succeeded or result.error_code
