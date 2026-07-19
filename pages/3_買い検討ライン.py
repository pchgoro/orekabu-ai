"""Buy watch price page."""

from __future__ import annotations

import streamlit as st

from components.layout import apply_responsive_styles
from components.tables import buy_watch_dataframe
from services.database import get_stocks, init_db, load_settings
from services.stock_data import build_analysis_rows
from services.view_models import build_buy_watch_rows
from utils.logging_config import setup_logging

st.set_page_config(page_title="買い検討ライン - オレ株AI", layout="wide")
setup_logging()
init_db()
st.title("買い検討ライン")
st.caption("注目スコアは売買推奨ではなく、確認優先度を示すものです。")

settings = load_settings()
apply_responsive_styles(settings["display_density"])
near_pct = float(settings.get("buy_watch_near_percent", 3.0))
rows = build_buy_watch_rows(build_analysis_rows(get_stocks(), settings), near_pct)
st.dataframe(buy_watch_dataframe(rows), use_container_width=True, hide_index=True, height=560)
