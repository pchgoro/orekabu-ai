"""Technical indicator calculations for daily stock prices."""

from __future__ import annotations

import numpy as np
import pandas as pd


def moving_average(series: pd.Series, window: int) -> pd.Series:
    """Calculate a simple moving average."""
    return series.rolling(window=window, min_periods=window).mean()


def rsi(series: pd.Series, period: int = 14) -> pd.Series:
    """Calculate RSI using Wilder-style exponential smoothing."""
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    result = 100 - (100 / (1 + rs))
    return result.mask((avg_loss == 0) & avg_gain.notna(), 100)


def macd(series: pd.Series) -> tuple[pd.Series, pd.Series, pd.Series]:
    """Calculate MACD, signal, and histogram."""
    ema12 = series.ewm(span=12, adjust=False, min_periods=12).mean()
    ema26 = series.ewm(span=26, adjust=False, min_periods=26).mean()
    macd_line = ema12 - ema26
    signal = macd_line.ewm(span=9, adjust=False, min_periods=9).mean()
    hist = macd_line - signal
    return macd_line, signal, hist


def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Add all supported indicators to an OHLCV dataframe."""
    if df is None or df.empty:
        return pd.DataFrame()
    result = df.copy()
    close = result["Close"]
    result["MA5"] = moving_average(close, 5)
    result["MA25"] = moving_average(close, 25)
    result["MA75"] = moving_average(close, 75)
    result["RSI14"] = rsi(close, 14)
    macd_line, signal, hist = macd(close)
    result["MACD"] = macd_line
    result["MACD_SIGNAL"] = signal
    result["MACD_HIST"] = hist
    result["VOLUME_MA20"] = result["Volume"].rolling(window=20, min_periods=20).mean()
    result["VOLUME_RATIO"] = result["Volume"] / result["VOLUME_MA20"].replace(0, np.nan)
    result["HIGH_60"] = result["High"].rolling(window=60, min_periods=1).max()
    result["DROP_FROM_HIGH_60"] = (result["Close"] / result["HIGH_60"] - 1) * 100
    result["DEV_MA25"] = (result["Close"] / result["MA25"] - 1) * 100
    result["DEV_MA75"] = (result["Close"] / result["MA75"] - 1) * 100
    result["MA5_ABOVE_MA25"] = result["MA5"] > result["MA25"]
    result["GOLDEN_CROSS"] = (result["MA5"].shift(1) <= result["MA25"].shift(1)) & (result["MA5"] > result["MA25"])
    return result


def latest_metrics(df: pd.DataFrame) -> dict[str, float | bool | None]:
    """Return latest indicator values as a dictionary."""
    if df is None or df.empty:
        return {}
    row = add_indicators(df).iloc[-1]
    return {key: (None if pd.isna(value) else value) for key, value in row.items()}
