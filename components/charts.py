"""Plotly chart helpers."""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from services.indicators import add_indicators


def price_chart(df: pd.DataFrame, ticker: str, buy_watch_price: float = 0) -> go.Figure:
    """Build a candlestick chart with moving averages."""
    data = add_indicators(df)
    fig = go.Figure()
    fig.add_trace(go.Candlestick(x=data.index, open=data["Open"], high=data["High"], low=data["Low"], close=data["Close"], name=ticker))
    for col, name in [("MA5", "5日線"), ("MA25", "25日線"), ("MA75", "75日線")]:
        fig.add_trace(go.Scatter(x=data.index, y=data[col], mode="lines", name=name))
    if buy_watch_price and buy_watch_price > 0:
        fig.add_hline(y=buy_watch_price, line_dash="dash", annotation_text="買い検討価格")
    fig.update_layout(template="plotly_dark", xaxis_rangeslider_visible=False, height=520, margin=dict(l=10, r=10, t=35, b=10))
    return fig


def technical_charts(df: pd.DataFrame) -> go.Figure:
    """Build volume, RSI, and MACD charts."""
    data = add_indicators(df)
    fig = make_subplots(rows=3, cols=1, shared_xaxes=True, vertical_spacing=0.05, row_heights=[0.35, 0.25, 0.40])
    fig.add_trace(go.Bar(x=data.index, y=data["Volume"], name="出来高"), row=1, col=1)
    fig.add_trace(go.Scatter(x=data.index, y=data["VOLUME_MA20"], name="出来高20日平均"), row=1, col=1)
    fig.add_trace(go.Scatter(x=data.index, y=data["RSI14"], name="RSI 14"), row=2, col=1)
    fig.add_hline(y=70, row=2, col=1, line_dash="dot")
    fig.add_hline(y=30, row=2, col=1, line_dash="dot")
    fig.add_trace(go.Scatter(x=data.index, y=data["MACD"], name="MACD"), row=3, col=1)
    fig.add_trace(go.Scatter(x=data.index, y=data["MACD_SIGNAL"], name="MACDシグナル"), row=3, col=1)
    fig.add_trace(go.Bar(x=data.index, y=data["MACD_HIST"], name="MACDヒストグラム"), row=3, col=1)
    fig.update_layout(template="plotly_dark", height=720, margin=dict(l=10, r=10, t=35, b=10))
    return fig
