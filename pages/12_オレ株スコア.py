"""Explainable daily ranking for the user's registered Japanese stocks."""

from __future__ import annotations

import streamlit as st

from components.layout import apply_responsive_styles
from components.navigation import company_profile_button
from services.database import get_stocks, init_db, load_settings
from services.earnings_view_models import enrich_stock_rows
from services.stock_data import build_analysis_rows
from services.stock_scores import enrich_rows_with_ore_scores, record_scores, score_rankings
from utils.formatters import fmt_price, fmt_signed_price
from utils.logging_config import setup_logging

st.set_page_config(page_title="オレ株スコア - オレ株AI", layout="wide")
setup_logging(); init_db()
settings = load_settings()
apply_responsive_styles(settings["display_density"])
st.title("オレ株スコア")
st.caption("カテゴリ・決算・重要ニュース・開示・出来高・損益の確認優先度を100点で整理します。売買推奨ではありません。")

rows = enrich_rows_with_ore_scores(
    enrich_stock_rows(
        build_analysis_rows(get_stocks(), settings),
        near_days=int(settings["earnings_near_days"]),
    )
)
rankings = score_rankings(rows)
if st.button("現在のスコアを履歴へ保存", type="primary"):
    count = record_scores(rows)
    st.success(f"{count}銘柄のスコア履歴を保存しました。")

tabs = st.tabs(["総合", "買い候補", "注意銘柄", "売却候補", "決算注目", "ニュース注目"])
mapping = (
    ("overall", "総合ランキング"), ("buy_candidates", "買い候補"),
    ("attention", "注意銘柄"), ("sell_candidates", "売却候補"),
    ("earnings", "決算注目"), ("news", "ニュース注目"),
)
for tab, (key, title) in zip(tabs, mapping):
    with tab:
        items = rankings[key]
        st.subheader(title)
        if not items:
            st.info("該当銘柄はありません。")
            continue
        for index, row in enumerate(items[:50], start=1):
            score = row["ore_score"]
            with st.container(border=True):
                st.write(f"**{index}. {row['ticker']} {row['company_name']}**  {score['score']}点 / {score['classification']}")
                cols = st.columns(3)
                cols[0].metric("現在値", fmt_price(row.get("current_price")))
                cols[1].metric("評価損益", fmt_signed_price(row.get("profit_loss")))
                cols[2].metric("決算まで", "-" if score.get("days_to_earnings") is None else f"{score['days_to_earnings']}日")
                st.caption(" / ".join(f"{part['points']:+d} {part['reason']}" for part in score["breakdown"]))
                company_profile_button(row["ticker"], "銘柄カルテを開く", key=f"score_profile_{row['id']}_{key}")
