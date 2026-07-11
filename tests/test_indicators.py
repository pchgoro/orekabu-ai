"""Tests for technical indicators."""

from __future__ import annotations

import numpy as np
import pandas as pd

from services.indicators import add_indicators, macd, moving_average, rsi


def sample_df(rows: int = 100) -> pd.DataFrame:
    close = pd.Series(np.linspace(100, 200, rows))
    return pd.DataFrame(
        {
            "Open": close - 1,
            "High": close + 2,
            "Low": close - 2,
            "Close": close,
            "Volume": pd.Series(np.linspace(1000, 2000, rows)),
        }
    )


def test_moving_average() -> None:
    series = pd.Series([1, 2, 3, 4, 5])
    assert moving_average(series, 3).iloc[-1] == 4


def test_rsi() -> None:
    result = rsi(pd.Series(range(1, 40)), 14)
    assert result.iloc[-1] > 90


def test_macd() -> None:
    macd_line, signal, hist = macd(pd.Series(range(1, 80)))
    assert not pd.isna(macd_line.iloc[-1])
    assert not pd.isna(signal.iloc[-1])
    assert not pd.isna(hist.iloc[-1])


def test_add_indicators() -> None:
    result = add_indicators(sample_df())
    assert "VOLUME_RATIO" in result.columns
    assert "DEV_MA25" in result.columns
    assert "DROP_FROM_HIGH_60" in result.columns
    assert not pd.isna(result["MA75"].iloc[-1])


def test_data_shortage() -> None:
    result = add_indicators(sample_df(10))
    assert pd.isna(result["MA25"].iloc[-1])
    assert "RSI14" in result.columns
