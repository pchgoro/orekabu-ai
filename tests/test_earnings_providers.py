"""Tests for provider normalization without external communication."""

from __future__ import annotations

from datetime import date

import pandas as pd

from services.earnings_providers.yfinance_provider import YFinanceEarningsProvider


class FakeTicker:
    def __init__(self, calendar=None, frame=None, error=None):
        self.calendar = calendar
        self.frame = frame
        self.error = error

    def get_earnings_dates(self, limit=8):
        if self.error:
            raise self.error
        return self.frame


def test_provider_future_multiple_and_timezone(monkeypatch) -> None:
    from services.earnings_providers import yfinance_provider as module
    fake = FakeTicker({"Earnings Date": [pd.Timestamp("2099-01-10", tz="Asia/Tokyo"), pd.Timestamp("2099-01-12")]})
    monkeypatch.setattr(module.yf, "Ticker", lambda ticker: fake)
    result = YFinanceEarningsProvider().fetch_next_earnings("5801.T")
    assert result.succeeded
    assert result.earnings_date == date(2099, 1, 10)
    assert result.candidate_dates == (date(2099, 1, 10), date(2099, 1, 12))
    assert result.confidence == "low"


def test_provider_empty_data(monkeypatch) -> None:
    from services.earnings_providers import yfinance_provider as module
    monkeypatch.setattr(module.yf, "Ticker", lambda ticker: FakeTicker({}, pd.DataFrame()))
    result = YFinanceEarningsProvider().fetch_next_earnings("5801.T")
    assert result.error_code == "empty_data"
    assert not result.succeeded


def test_provider_network_error(monkeypatch) -> None:
    from services.earnings_providers import yfinance_provider as module
    monkeypatch.setattr(module.yf, "Ticker", lambda ticker: (_ for _ in ()).throw(TimeoutError("timeout")))
    result = YFinanceEarningsProvider().fetch_next_earnings("5801.T")
    assert result.error_code == "timeout"


def test_provider_past_date_is_returned_for_warning(monkeypatch) -> None:
    from services.earnings_providers import yfinance_provider as module
    monkeypatch.setattr(module.yf, "Ticker", lambda ticker: FakeTicker({"Earnings Date": ["2020-01-01"]}))
    result = YFinanceEarningsProvider().fetch_next_earnings("5801.T")
    assert result.earnings_date == date(2020, 1, 1)


def test_provider_falls_back_to_date_index(monkeypatch) -> None:
    from services.earnings_providers import yfinance_provider as module
    frame = pd.DataFrame({"Reported EPS": [1.0]}, index=[pd.Timestamp("2099-02-01")])
    monkeypatch.setattr(module.yf, "Ticker", lambda ticker: FakeTicker({}, frame))
    assert YFinanceEarningsProvider().fetch_next_earnings("5801.T").earnings_date == date(2099, 2, 1)
