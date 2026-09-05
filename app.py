"""オレ株AI dashboard."""

from __future__ import annotations

import streamlit as st

from components.cards import summary_metrics
from components.daily import (
    render_dashboard_focus,
    render_earnings_cards,
    render_stock_cards,
)
from components.layout import apply_responsive_styles
from services.database import get_stocks, init_db, load_settings
from services.earnings import list_earnings
from services.earnings_candidates import candidate_dashboard_summary, list_candidates
from services.earnings_view_models import enrich_stock_rows, prepare_earnings_rows
from services.news import list_articles, list_fetch_runs as list_news_fetch_runs, news_dashboard_summary
from services.daily_briefing import build_briefing, build_daily_tasks
from services.disclosures import dashboard_summary as disclosure_dashboard_summary, list_disclosures
from services.automation import automation_summary
from services.stock_data import build_analysis_rows, make_prompt
from services.investment_playbooks import enrich_rows_with_playbooks
from services.strategy_rules import enrich_rows_with_strategy, strategy_dashboard_summary
from services.stock_scores import enrich_rows_with_ore_scores, score_rankings
from services.view_models import build_buy_watch_rows
from utils.constants import APP_NAME
from utils.logging_config import setup_logging

st.set_page_config(page_title=APP_NAME, layout="wide", initial_sidebar_state="expanded")
setup_logging()
init_db()

st.title(APP_NAME)
st.caption("注目スコアは売買推奨ではなく、確認優先度を示すものです。")
st.page_link("pages/9_企業カルテ.py", label="企業カルテを開く")

settings = load_settings()
apply_responsive_styles(settings["display_density"])
stocks = get_stocks()
rows = enrich_rows_with_ore_scores(enrich_rows_with_strategy(
    enrich_rows_with_playbooks(
        enrich_stock_rows(
            build_analysis_rows(stocks, settings),
            near_days=int(settings["earnings_near_days"]),
        )
    ),
    near_percent=float(settings["strategy_rule_near_percent"]),
))
earnings_rows = [r for r in prepare_earnings_rows(list_earnings(), near_days=int(settings["earnings_near_days"])) if r.get("days_until") is not None and r["days_until"] >= 0]
candidates = list_candidates()
news_rows = list_articles()
news_summary = news_dashboard_summary()
news_runs = list_news_fetch_runs()
rss_failed = int(news_runs[0].get("failed_count") or 0) if news_runs else 0
buy_watch_rows = build_buy_watch_rows(rows, float(settings["buy_watch_near_percent"]))
disclosure_rows = list_disclosures()
disclosure_summary = disclosure_dashboard_summary()
briefing = build_briefing(
    rows, earnings_rows, candidates, news_rows, buy_watch_rows, news_summary,
    rss_failed, disclosure_rows, rows, rows,
)
tasks = build_daily_tasks(
    rows, earnings_rows, candidates, news_rows, buy_watch_rows, rss_failed,
    int(settings["daily_tasks_limit"]), disclosure_rows, rows, rows,
)
strategy_summary = strategy_dashboard_summary(rows)
ore_rankings = score_rankings(rows)
compact = settings["dashboard_display_mode"] == "コンパクト"

render_dashboard_focus(tasks, briefing, news_rows, disclosure_rows)
with st.expander("オレ株スコア", expanded=not compact):
    score_cols = st.columns(3)
    with score_cols[0]:
        st.markdown("#### 今日の注目 TOP10")
        for row in ore_rankings["overall"][:10]:
            st.write(f"{row['ticker']} {row['company_name']} - {row['ore_score']['score']}点 ({row['ore_score']['classification']})")
    with score_cols[1]:
        st.markdown("#### 今日の危険 TOP10")
        danger = sorted(
            ore_rankings["attention"],
            key=lambda row: int(row["ore_score"]["score"]),
        )[:10]
        if danger:
            for row in danger:
                st.write(f"{row['ticker']} {row['company_name']} - {row['ore_score']['score']}点 ({row['ore_score']['classification']})")
        else:
            st.caption("現在、注意・売却候補はありません。")
    with score_cols[2]:
        st.markdown("#### スコア急変")
        sudden = ore_rankings.get("sudden_changes") or []
        if sudden:
            for row in sudden[:10]:
                diff = row["score_diff"]
                sign = "+" if diff > 0 else ""
                st.write(f"{row['ticker']} {row['company_name']} - {row['ore_score']['score']}点 ({sign}{diff}点)")
        else:
            st.caption("前回履歴保存から急変した銘柄はありません。")
    st.page_link("pages/12_オレ株スコア.py", label="オレ株スコアのランキングを開く")
st.caption(
    f"RSS最終取得: {news_summary.get('last_fetch') or '未実行'} / "
    f"直近失敗: {rss_failed}件"
)

holdings = [row for row in rows if row.get("is_holding")]
with st.expander("保有株", expanded=not compact):
    if not compact:
        st.subheader("ポートフォリオ概要")
        summary_metrics(stocks, rows, mobile=bool(settings["mobile_priority_display"]))
    render_stock_cards(holdings, holding=True)
    st.page_link("pages/1_保有株.py", label="保有株一覧を開く")

with st.expander("決算", expanded=False):
    render_earnings_cards(earnings_rows[: int(settings["earnings_dashboard_limit"])])
    candidate_summary = candidate_dashboard_summary()
    if candidate_summary["pending"] or candidate_summary["last_fetched_at"]:
        st.markdown("#### 決算日取得候補")
        cols = st.columns(5)
        cols[0].metric("未確認候補", candidate_summary["pending"])
        cols[1].metric("日付変更", candidate_summary["date_changed"])
        cols[2].metric("競合", candidate_summary["conflicts"])
        cols[3].metric("最終取得", candidate_summary["last_fetched_at"] or "未実行")
        cols[4].metric("直近失敗", candidate_summary["last_failed"])
        st.caption("候補の確認はサイドバーの「決算」→「決算日自動取得」から行えます。")
    st.page_link("pages/5_決算.py", label="決算管理を開く")

with st.expander("ニュース", expanded=False):
    if news_rows:
        for row in news_rows[:5]:
            with st.container(border=True):
                st.write(f"**{row.get('title') or 'タイトルなし'}**")
                st.caption(
                    f"{row.get('source_name') or '配信元不明'} / "
                    f"{row.get('published_at') or row.get('retrieved_at') or '日時不明'}"
                )
        st.page_link("pages/7_ニュース.py", label="ニュースを開く")
    else:
        st.caption("ニュースはまだ登録されていません。")

with st.expander("適時開示", expanded=False):
    disclosure_cols = st.columns(2)
    disclosure_cols[0].metric("今日の開示", disclosure_summary["today"])
    disclosure_cols[1].metric("未読開示", disclosure_summary["unread"])
    disclosure_cols[0].metric("重要度高", disclosure_summary["high"])
    disclosure_cols[1].metric("保有株開示", disclosure_summary["holding"])
    if disclosure_rows:
        for disclosure in disclosure_rows[:5]:
            with st.container(border=True):
                st.write(f"**{disclosure['ticker']} {disclosure['title']}**")
                st.caption(
                    f"{disclosure['disclosed_at']} / {disclosure['disclosure_type']}"
                )
        st.page_link("pages/8_適時開示.py", label="適時開示を開く")
    else:
        st.caption("適時開示はまだ登録されていません。")

with st.expander("自動取得状況", expanded=False):
    auto = automation_summary()
    cols = st.columns(2)
    cols[0].metric("最終実行", auto.get("last_run_at") or "未実行")
    cols[1].metric("自動取得失敗", auto.get("last_failed") or 0)
    cols[0].metric("EDINET新着", auto.get("new_edinet") or 0)
    cols[1].metric("未確認決算候補", auto.get("pending_earnings") or 0)
    st.page_link("pages/6_設定.py", label="自動取得設定を開く")

with st.expander("戦略ルール", expanded=False):
    cols = st.columns(3)
    cols[0].metric("損切到達", strategy_summary.get("stop_loss_reached", 0))
    cols[1].metric("損切接近", strategy_summary.get("stop_loss_near", 0))
    cols[2].metric("利確到達", strategy_summary.get("take_profit_reached", 0))
    cols[0].metric("利確接近", strategy_summary.get("take_profit_near", 0))
    cols[1].metric("ルール競合", strategy_summary.get("conflicts", 0))
    cols[2].metric("ルール未設定", strategy_summary.get("unset", 0))
    ratios = strategy_summary.get("top_tag_ratios") or []
    if ratios:
        st.markdown("#### タグ別保有比率上位")
        for item in ratios:
            st.write(
                f"{item['tag']}: {float(item['portfolio_ratio']):.2f}%"
            )
    st.page_link("pages/10_戦略・カテゴリ.py", label="戦略・カテゴリを開く")

with st.expander("注目銘柄・分析プロンプト", expanded=False):
    limit = int(settings.get("ranking_limit", 10))
    ranking = sorted(rows, key=lambda row: row.get("score", 0), reverse=True)[:limit]
    render_stock_cards(ranking, holding=False)
    if ranking:
        labels = {f"{row['ticker']} {row['company_name']}": row for row in ranking}
        selected = st.selectbox("分析する銘柄", list(labels.keys()))
        st.text_area("コピー用プロンプト", make_prompt(labels[selected]), height=420)
