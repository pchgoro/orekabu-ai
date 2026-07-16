"""Integrated company intelligence page for one registered stock."""

from __future__ import annotations

import logging

import streamlit as st

from components.layout import apply_responsive_styles
from components.navigation import company_profile_button
from services.company_profile import build_company_profile, search_companies, update_company_metadata
from services.database import init_db, load_settings
from utils.formatters import fmt_number, fmt_price, fmt_signed_price
from utils.logging_config import setup_logging

logger = logging.getLogger(__name__)
st.set_page_config(page_title="企業カルテ - オレ株AI", layout="wide")
setup_logging(); init_db(); apply_responsive_styles()
st.title("企業カルテ")
st.caption("企業情報を横断して確認するためのページです。表示内容は売買推奨ではありません。")

settings = load_settings()
query = st.text_input("銘柄コード・会社名・略称で検索", value=str(st.query_params.get("q", "")))
companies = search_companies(query)
if not companies:
    st.info("一致する登録銘柄がありません。")
    st.stop()

labels = {f"{row['ticker']} {row['company_name']}" + (f"（{row['company_alias']}）" if row.get("company_alias") else ""): row for row in companies}
requested_ticker = str(st.query_params.get("ticker", ""))
selected_index = next((index for index, row in enumerate(labels.values()) if row["ticker"] == requested_ticker), 0)
selected_label = st.selectbox("企業を選択", list(labels), index=selected_index)
selected = labels[selected_label]
st.query_params["ticker"] = selected["ticker"]

try:
    profile = build_company_profile(selected["ticker"], settings)
except Exception as exc:
    st.error(str(exc)); logger.exception("企業カルテ生成失敗 ticker=%s", selected["ticker"]); st.stop()

stock, price = profile["stock"], profile["price"]
mobile = bool(settings.get("mobile_priority_display"))

st.subheader(f"{stock['ticker']} {stock['company_name']}")
if stock.get("company_alias"): st.caption(f"略称: {stock['company_alias']}")

if mobile:
    section_columns = [st.container(), st.container()]
else:
    section_columns = st.columns([1, 1])

with section_columns[0]:
    st.markdown("#### 基本情報")
    st.write(f"市場: {stock.get('market') or '未登録'}")
    st.write(f"業種: {stock.get('industry') or '未登録'}")
    st.write(f"区分: {'保有株' if stock.get('is_holding') else stock.get('category') or '監視銘柄'}")
    st.write(f"保有メモ: {stock.get('memo') or 'なし'}")
    with st.expander("企業情報を編集"):
        alias = st.text_input("略称", stock.get("company_alias") or "", key=f"profile_alias_{stock['id']}")
        market = st.text_input("市場", stock.get("market") or "", key=f"profile_market_{stock['id']}")
        industry = st.text_input("業種", stock.get("industry") or "", key=f"profile_industry_{stock['id']}")
        if st.button("企業情報を保存", key=f"profile_save_{stock['id']}"):
            try:
                update_company_metadata(int(stock["id"]), alias, market, industry)
                st.success("企業情報を保存しました。"); st.rerun()
            except Exception as exc:
                st.error(str(exc)); logger.exception("企業情報更新失敗 stock_id=%s", stock["id"])

with section_columns[1]:
    st.markdown("#### 株価概要")
    metrics = st.columns(2)
    metrics[0].metric("現在値", fmt_price(price.get("current_price")))
    metrics[1].metric("前日比", fmt_signed_price(price.get("change")))
    metrics[0].metric("買いライン", fmt_price(stock.get("buy_watch_price")))
    metrics[1].metric("注目スコア", fmt_number(price.get("score"), 0))
    st.caption(f"更新日時: {price.get('price_updated_at') or '取得失敗・未取得'}")

st.subheader("決算")
earnings_cols = [st.container(), st.container(), st.container()] if mobile else st.columns(3)
next_event = profile.get("next_earnings") or {}
with earnings_cols[0]:
    st.markdown("##### 次回決算")
    st.write(next_event.get("earnings_date") or "未登録")
    st.caption(f"{next_event.get('fiscal_quarter') or '未設定'} / {next_event.get('date_status') or '未確認'}")
with earnings_cols[1]:
    st.markdown("##### 決算候補")
    candidates = profile["earnings_candidates"][:5]
    if candidates:
        for row in candidates: st.write(f"{row.get('candidate_date') or '日付なし'} / {row.get('comparison_status')} / {row.get('review_status')}")
    else: st.caption("候補なし")
with earnings_cols[2]:
    st.markdown("##### 関連決算")
    if profile["related_earnings"]:
        for row in profile["related_earnings"][:5]: st.write(f"{row['related_ticker']} {row.get('earnings_date') or '日付未確認'}")
    else: st.caption("関連決算なし")
with st.expander("過去決算履歴"):
    if profile["earnings_history"]:
        for row in profile["earnings_history"]: st.write(f"{row['earnings_date']} / {row['fiscal_quarter']} / {row['date_status']}")
    else: st.caption("過去決算はありません。")

content_cols = [st.container(), st.container()] if mobile else st.columns(2)
with content_cols[0]:
    st.subheader("ニュース")
    summary = profile["news_summary"]
    st.caption(f"未読 {summary['unread']}件 / 重要 {summary['important']}件 / お気に入り {summary['favorites']}件")
    if profile["news"]:
        for row in profile["news"][:5]:
            st.write(f"{row.get('published_at') or '日時不明'} / {row.get('title') or 'タイトルなし'}")
    else: st.info("承認済み関連ニュースはありません。")
with content_cols[1]:
    st.subheader("適時開示")
    disclosure_summary = profile["disclosure_summary"]
    st.caption(f"未読 {disclosure_summary['unread']}件 / 重要 {disclosure_summary['important']}件")
    if profile["disclosures"]:
        for row in profile["disclosures"][:5]:
            st.write(f"{row.get('disclosed_at') or '日時不明'} / {row.get('disclosure_type')} / {row.get('title')}")
    else: st.info("適時開示はありません。")

st.subheader("関連銘柄")
if profile["relations"]:
    relation_cols = st.columns(2) if not mobile else [st.container()]
    for index, row in enumerate(profile["relations"]):
        with relation_cols[index % len(relation_cols)]:
            st.write(f"{row['direction_label']}: {row['related_ticker']} {row['related_company_name']}")
            st.caption(f"関係: {row['relation_type']} / 影響度: {row['impact_level']}")
            company_profile_button(
                row["related_ticker"],
                "関連企業のカルテを開く",
                key=f"related_profile_{index}_{row['related_ticker']}",
            )
else:
    st.info("関連銘柄はありません。")

st.subheader("タイムライン")
if profile["timeline"]:
    for row in profile["timeline"][:30]:
        st.write(f"{row.get('occurred_at') or '日時不明'} | {row['event_type']} | {row['title']}")
        st.caption(f"状態・重要度: {row['importance']}")
else:
    st.info("タイムラインに表示する情報はありません。")

st.subheader("ChatGPT分析用プロンプト")
st.text_area("企業カルテ分析用プロンプト", profile["prompt"], height=520)
