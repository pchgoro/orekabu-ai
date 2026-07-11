"""Chart page."""

from __future__ import annotations

import streamlit as st

from components.charts import price_chart, technical_charts
from services.database import get_stocks, init_db, load_settings
from services.stock_data import cache_bucket, fetch_stock_history, period_to_yfinance
from utils.logging_config import setup_logging

st.set_page_config(page_title="チャート - オレ株AI", layout="wide")
setup_logging()
init_db()
st.title("チャート")

stocks = get_stocks()
if not stocks:
    st.info("登録銘柄がありません。")
    st.stop()

labels = {f"{stock['ticker']} {stock['company_name']}": stock for stock in stocks}
cols = st.columns(2)
selected = cols[0].selectbox("銘柄", list(labels.keys()))
period_label = cols[1].selectbox("期間", ["1か月", "3か月", "6か月", "1年"], index=3)
stock = labels[selected]
settings = load_settings()
df = fetch_stock_history(stock["ticker"], period_to_yfinance(period_label), "1d", cache_bucket(settings.get("stock_cache_minutes", 15)))
if df.empty:
    st.error("株価データを取得できませんでした。ネットワーク状況または銘柄コードを確認してください。")
    st.stop()

st.plotly_chart(price_chart(df, stock["ticker"], float(stock.get("buy_watch_price") or 0)), use_container_width=True)
st.plotly_chart(technical_charts(df), use_container_width=True)
