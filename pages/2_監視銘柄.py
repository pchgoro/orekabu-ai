"""Watchlist page."""

from __future__ import annotations

import streamlit as st

from components.forms import create_stock_section, edit_delete_section
from components.tables import watchlist_dataframe
from services.database import get_stocks, init_db, load_settings
from services.stock_data import build_analysis_rows, make_prompt
from services.earnings_view_models import enrich_stock_rows
from services.view_models import filter_watchlist, sort_watchlist
from utils.constants import CATEGORIES
from utils.logging_config import setup_logging

st.set_page_config(page_title="監視銘柄 - オレ株AI", layout="wide")
setup_logging()
init_db()
st.title("監視銘柄")
st.caption("注目スコアは売買推奨ではなく、確認優先度を示すものです。")

stocks = get_stocks()
settings = load_settings()
rows = filter_watchlist(enrich_stock_rows(build_analysis_rows(stocks, settings), near_days=int(settings["earnings_near_days"])))

create_stock_section()
edit_delete_section(rows, "watch")

cols = st.columns(2)
category_filter = cols[0].multiselect("分類で絞り込み", CATEGORIES, default=[c for c in CATEGORIES if c != "保有株"])
sort_label = cols[1].selectbox("並び替え", ["スコア順", "RSI昇順", "RSI降順", "下落率順", "出来高倍率順", "銘柄コード順"])
filtered = [row for row in rows if row.get("category") in category_filter]
filtered = sort_watchlist(filtered, sort_label)

st.dataframe(watchlist_dataframe(filtered), use_container_width=True, hide_index=True, height=560)

with st.expander("ChatGPT分析用プロンプトを表示", expanded=False):
    if filtered:
        labels = {f"{row['ticker']} {row['company_name']}": row for row in filtered}
        selected = st.selectbox("銘柄", list(labels.keys()), key="watch_prompt")
        st.text_area("コピー用プロンプト", make_prompt(labels[selected]), height=520)
    else:
        st.info("監視銘柄がありません。")
