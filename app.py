"""オレ株AI dashboard."""

from __future__ import annotations

import streamlit as st

from components.cards import summary_metrics
from components.tables import dashboard_dataframe, earnings_dataframe, impact_dataframe
from services.database import get_stocks, init_db, load_settings
from services.earnings import list_earnings
from services.earnings_candidates import candidate_dashboard_summary
from services.earnings_view_models import enrich_stock_rows, prepare_earnings_rows
from services.relations import impact_candidates
from services.stock_data import build_analysis_rows, make_prompt
from utils.constants import APP_NAME
from utils.logging_config import setup_logging

st.set_page_config(page_title=APP_NAME, layout="wide", initial_sidebar_state="expanded")
setup_logging()
init_db()

st.title(APP_NAME)
st.caption("注目スコアは売買推奨ではなく、確認優先度を示すものです。")

settings = load_settings()
stocks = get_stocks()
rows = enrich_stock_rows(build_analysis_rows(stocks, settings), near_days=int(settings["earnings_near_days"]))

summary_metrics(stocks, rows)

candidate_summary = candidate_dashboard_summary()
if candidate_summary["pending"] or candidate_summary["last_fetched_at"]:
    with st.expander("決算日取得候補", expanded=candidate_summary["conflicts"] > 0):
        cols = st.columns(5)
        cols[0].metric("未確認候補", candidate_summary["pending"])
        cols[1].metric("日付変更", candidate_summary["date_changed"])
        cols[2].metric("競合", candidate_summary["conflicts"])
        cols[3].metric("最終取得", candidate_summary["last_fetched_at"] or "未実行")
        cols[4].metric("直近失敗", candidate_summary["last_failed"])
        st.caption("候補の確認はサイドバーの「決算」→「決算日自動取得」から行えます。")

st.subheader("今日の注目銘柄ランキング")
limit = int(settings.get("ranking_limit", 10))
ranking = sorted(rows, key=lambda row: row.get("score", 0), reverse=True)[:limit]
st.dataframe(dashboard_dataframe(ranking), use_container_width=True, hide_index=True, height=520)

st.subheader("直近の決算予定")
earnings_rows = [r for r in prepare_earnings_rows(list_earnings(), near_days=int(settings["earnings_near_days"])) if r.get("days_until") is not None and r["days_until"] >= 0]
st.dataframe(earnings_dataframe(earnings_rows[: int(settings["earnings_dashboard_limit"])]), use_container_width=True, hide_index=True)

with st.expander("関連銘柄の注目決算", expanded=False):
    impacts = [r for r in impact_candidates() if r.get("days_until") is not None and r["days_until"] >= 0]
    if impacts:
        st.caption("関連銘柄の決算は影響を断定するものではなく、確認対象を整理するための情報です。")
        st.dataframe(impact_dataframe(impacts[: int(settings["related_earnings_limit"])]), use_container_width=True, hide_index=True)
    else:
        st.info("関連銘柄の決算予定は登録されていません。")

with st.expander("ChatGPT分析用プロンプトを表示", expanded=False):
    if ranking:
        labels = {f"{row['ticker']} {row['company_name']}": row for row in ranking}
        selected = st.selectbox("銘柄", list(labels.keys()))
        prompt = make_prompt(labels[selected])
        st.text_area("コピー用プロンプト", prompt, height=520)
    else:
        st.info("登録銘柄がありません。")
