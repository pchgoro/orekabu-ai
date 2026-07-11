"""Tests for stock data failure handling and prompt formatting."""

from __future__ import annotations

import numpy as np
import pandas as pd

from services.stock_data import fetch_stock_history, make_prompt


def test_fetch_stock_history_failure_returns_empty(monkeypatch) -> None:
    """A yfinance failure must not propagate and stop the app."""
    from services import stock_data

    def raise_error(*args, **kwargs):
        raise RuntimeError("network down")

    monkeypatch.setattr(stock_data.yf, "download", raise_error)
    df = fetch_stock_history("9999.T", "1y", "1d", 123456789)
    assert isinstance(df, pd.DataFrame)
    assert df.empty


def test_prompt_does_not_expose_nan_or_none() -> None:
    prompt = make_prompt(
        {
            "ticker": "5801.T",
            "company_name": "古河電気工業",
            "current_price": np.nan,
            "change": None,
            "score": 50,
            "score_reasons": ["初期点：+50点"],
        }
    )
    assert "nan" not in prompt.lower()
    assert "None" not in prompt
    assert "データなし" in prompt


def test_prompt_contains_earnings_and_relation_sections() -> None:
    prompt = make_prompt({"ticker":"5801.T","company_name":"古河電気工業","next_earnings_date_display":"2026-07-20","earnings_days_label":"あと9日","earnings_quarter":"Q1","earnings_date_status":"予定","earnings_announcement_time":"15:00","related_earnings":"登録なし","earnings_memo":None,"score_reasons":[]})
    assert "次回決算日" in prompt and "2026-07-20" in prompt
    assert "関連企業の決算から確認できること" in prompt
    assert "None" not in prompt and "nan" not in prompt.lower()


def test_prompt_shows_unconfirmed_for_null_earnings_date() -> None:
    prompt = make_prompt({"ticker":"5801.T","company_name":"古河電気工業","next_earnings_date_display":"日付未確認","earnings_days_label":"日付未確認","earnings_date_status":"未確認","score_reasons":[]})
    assert "次回決算日：\n日付未確認" in prompt
    assert "None" not in prompt and "nan" not in prompt.lower()
