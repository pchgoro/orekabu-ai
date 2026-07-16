"""オレ株AI dashboard."""

from __future__ import annotations

import streamlit as st

from components.cards import summary_metrics
from components.daily import render_briefing, render_daily_tasks, render_earnings_cards, render_stock_cards
from components.layout import apply_responsive_styles
from components.tables import dashboard_dataframe, earnings_dataframe, impact_dataframe, news_dataframe
from services.database import get_stocks, init_db, load_settings
from services.earnings import list_earnings
from services.earnings_candidates import candidate_dashboard_summary, list_candidates
from services.earnings_view_models import enrich_stock_rows, prepare_earnings_rows
from services.relations import impact_candidates
from services.news import list_articles, list_fetch_runs as list_news_fetch_runs, news_dashboard_summary
from services.daily_briefing import build_briefing, build_daily_tasks
from services.disclosures import dashboard_summary as disclosure_dashboard_summary, list_disclosures
from services.stock_data import build_analysis_rows, make_prompt
from services.view_models import build_buy_watch_rows
from utils.constants import APP_NAME
from utils.logging_config import setup_logging

st.set_page_config(page_title=APP_NAME, layout="wide", initial_sidebar_state="expanded")
setup_logging()
init_db()
apply_responsive_styles()

st.title(APP_NAME)
st.caption("注目スコアは売買推奨ではなく、確認優先度を示すものです。")
st.page_link("pages/9_企業カルテ.py", label="企業カルテを開く")

settings = load_settings()
stocks = get_stocks()
rows = enrich_stock_rows(build_analysis_rows(stocks, settings), near_days=int(settings["earnings_near_days"]))
earnings_rows = [r for r in prepare_earnings_rows(list_earnings(), near_days=int(settings["earnings_near_days"])) if r.get("days_until") is not None and r["days_until"] >= 0]
candidates = list_candidates()
news_rows = list_articles()
news_summary = news_dashboard_summary()
news_runs = list_news_fetch_runs()
rss_failed = int(news_runs[0].get("failed_count") or 0) if news_runs else 0
buy_watch_rows = build_buy_watch_rows(rows, float(settings["buy_watch_near_percent"]))
disclosure_rows = list_disclosures()
disclosure_summary = disclosure_dashboard_summary()
briefing = build_briefing(rows, earnings_rows, candidates, news_rows, buy_watch_rows, news_summary, rss_failed, disclosure_rows)
tasks = build_daily_tasks(rows, earnings_rows, candidates, news_rows, buy_watch_rows, rss_failed, int(settings["daily_tasks_limit"]), disclosure_rows)
compact = settings["dashboard_display_mode"] == "コンパクト"

render_briefing(briefing, int(settings["briefing_limit"]), bool(settings["hide_zero_sections"]), compact)
st.caption(f"RSS最終取得: {news_summary.get('last_fetch') or '未実行'} / 直近失敗: {rss_failed}件")
render_daily_tasks(tasks)
st.subheader("適時開示概要")
disclosure_cols = st.columns(2)
disclosure_cols[0].metric("今日の開示", disclosure_summary["today"])
disclosure_cols[1].metric("未読開示", disclosure_summary["unread"])
disclosure_cols[0].metric("重要度高", disclosure_summary["high"])
disclosure_cols[1].metric("保有株開示", disclosure_summary["holding"])
if not compact:
    st.subheader("ポートフォリオ概要")
    summary_metrics(stocks, rows, mobile=bool(settings["mobile_priority_display"]))

with st.expander("最新ニュース", expanded=False):
    latest_news = news_rows[:5]
    if latest_news:
        st.dataframe(news_dataframe(latest_news), use_container_width=True, hide_index=True)
    else:
        st.info("ニュースはまだ登録されていません。")

with st.expander("最新の適時開示", expanded=False):
    if disclosure_rows:
        for disclosure in disclosure_rows[:5]:
            st.write(f"{disclosure['disclosed_at']} / {disclosure['ticker']} / {disclosure['disclosure_type']} / {disclosure['title']}")
        st.page_link("pages/8_適時開示.py", label="適時開示を開く")
    else:
        st.info("適時開示はまだ登録されていません。")

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
if settings["mobile_priority_display"]:
    render_stock_cards(ranking, holding=False)
else:
    st.dataframe(dashboard_dataframe(ranking), use_container_width=True, hide_index=True, height=520)

st.subheader("直近の決算予定")
if settings["mobile_priority_display"]:
    render_earnings_cards(earnings_rows[: int(settings["earnings_dashboard_limit"])])
else:
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
