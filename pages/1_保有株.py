"""Holdings page."""

from __future__ import annotations

import streamlit as st

from components.navigation import company_profile_button

from components.cards import holding_metrics
from components.forms import create_stock_section, edit_delete_section
from components.tables import holdings_dataframe
from components.daily import render_stock_cards
from components.layout import apply_responsive_styles
from services.database import get_stocks, init_db, load_settings
from services.stock_data import build_analysis_rows, make_prompt
from services.earnings_view_models import enrich_stock_rows
from services.view_models import filter_holdings
from utils.logging_config import setup_logging

st.set_page_config(page_title="保有株 - オレ株AI", layout="wide")
setup_logging()
init_db()
apply_responsive_styles()
st.title("保有株")
st.caption("注目スコアは売買推奨ではなく、確認優先度を示すものです。")

stocks = get_stocks()
settings = load_settings()
rows = filter_holdings(enrich_stock_rows(build_analysis_rows(stocks, settings), near_days=int(settings["earnings_near_days"])))
holding_metrics(rows)
if rows:
    profile_labels = {f"{row['ticker']} {row['company_name']}": row for row in rows}
    profile_label = st.selectbox("企業カルテを開く銘柄", list(profile_labels), key="holding_profile")
    company_profile_button(
        profile_labels[profile_label]["ticker"],
        "企業カルテを開く",
        key="holding_profile_open",
    )
create_stock_section()
edit_delete_section(rows, "holding")

if settings["mobile_priority_display"]:
    render_stock_cards(rows, holding=True)
else:
    st.dataframe(holdings_dataframe(rows), use_container_width=True, hide_index=True, height=520)

with st.expander("ChatGPT分析用プロンプトを表示", expanded=False):
    if rows:
        labels = {f"{row['ticker']} {row['company_name']}": row for row in rows}
        selected = st.selectbox("銘柄", list(labels.keys()), key="holding_prompt")
        st.text_area("コピー用プロンプト", make_prompt(labels[selected]), height=520)
    else:
        st.info("保有株がありません。")
