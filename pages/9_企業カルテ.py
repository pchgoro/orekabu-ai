"""Integrated company intelligence page for one registered stock."""

from __future__ import annotations

import logging
from datetime import datetime

import streamlit as st

from components.layout import apply_responsive_styles
from components.navigation import (
    COMPANY_PROFILE_REQUESTED_TICKER,
    company_profile_button,
)
from components.investment_playbook import (
    render_playbook_form,
    render_playbook_summary,
)
from components.strategy_rules import (
    render_individual_rule_editor,
    render_stock_tag_editor,
    render_strategy_summary,
    render_tag_badges,
)
from components.ui import empty_state, render_market_metric, render_priority_badge
from services.company_profile import (
    add_company_note,
    build_company_profile,
    delete_company_note,
    save_company_intelligence,
    search_companies,
    update_company_metadata,
)
from services.database import init_db, load_settings
from utils.formatters import fmt_number, fmt_price, fmt_signed_price
from utils.logging_config import setup_logging

logger = logging.getLogger(__name__)
st.set_page_config(page_title="企業カルテ - オレ株AI", layout="wide")
setup_logging(); init_db()
st.title("企業カルテ")
st.caption("企業情報を横断して確認するためのページです。表示内容は売買推奨ではありません。")

settings = load_settings()
apply_responsive_styles(settings["display_density"])
requested_from_navigation = str(
    st.session_state.pop(COMPANY_PROFILE_REQUESTED_TICKER, "") or ""
)
requested_from_query = str(st.query_params.get("ticker", "") or "")
requested_ticker = requested_from_navigation or requested_from_query
search_key = "company_profile_search_query"
selection_key = "company_profile_selected_label"
if requested_from_navigation:
    st.session_state[search_key] = ""
elif search_key not in st.session_state:
    st.session_state[search_key] = str(st.query_params.get("q", "") or "")
query = st.text_input(
    "銘柄コード・会社名・略称で検索",
    key=search_key,
)
companies = search_companies(query)
if not companies:
    st.info("一致する登録銘柄がありません。")
    st.stop()

labels = {f"{row['ticker']} {row['company_name']}" + (f"（{row['company_alias']}）" if row.get("company_alias") else ""): row for row in companies}
selected_index = next((index for index, row in enumerate(labels.values()) if row["ticker"] == requested_ticker), 0)
if requested_from_navigation:
    st.session_state[selection_key] = list(labels)[selected_index]
selected_label = st.selectbox(
    "企業を選択",
    list(labels),
    index=selected_index,
    key=selection_key,
)
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
    with metrics[1]:
        render_market_metric("前日比", fmt_signed_price(price.get("change")), price.get("change"))
    metrics[0].metric("買いライン", fmt_price(stock.get("buy_watch_price")))
    metrics[1].metric("注目スコア", fmt_number(price.get("score"), 0))
    st.caption(f"更新日時: {price.get('price_updated_at') or '取得失敗・未取得'}")

st.subheader("今日の注意点")
attention_items = []
next_event = profile.get("next_earnings") or {}
if next_event.get("days_until") == 0:
    attention_items.append(("urgent", "本日決算", next_event.get("earnings_date")))
elif isinstance(next_event.get("days_until"), int) and next_event["days_until"] <= 7:
    attention_items.append(("today", "決算が接近", next_event.get("earnings_date")))
if profile["news_summary"]["important"]:
    attention_items.append(("urgent", "重要ニュース", f"{profile['news_summary']['important']}件"))
elif profile["news_summary"]["unread"]:
    attention_items.append(("today", "未読ニュース", f"{profile['news_summary']['unread']}件"))
if profile["disclosure_summary"]["important"]:
    attention_items.append(("urgent", "重要な適時開示", f"{profile['disclosure_summary']['important']}件"))
if profile["earnings_candidates"]:
    attention_items.append(("today", "未確認の決算候補", f"{len(profile['earnings_candidates'])}件"))
if attention_items:
    attention_cols = st.columns(2 if mobile else min(3, len(attention_items)))
    for index, (level, label, detail) in enumerate(attention_items):
        with attention_cols[index % len(attention_cols)]:
            with st.container(border=True):
                render_priority_badge(level)
                st.write(f"**{label}**")
                st.caption(str(detail or "詳細未登録"))
else:
    empty_state("今日すぐに確認が必要な項目はありません。")

st.subheader("投資ルール")
render_playbook_summary(
    profile.get("investment_playbook"),
    profile["playbook_evaluation"],
)
with st.expander("投資ルールを編集", expanded=False):
    render_playbook_form(
        int(stock["id"]),
        profile.get("investment_playbook"),
        mobile=mobile,
    )

st.subheader("戦略タグ・共通ルール")
render_tag_badges(profile.get("strategy_tags") or [])
render_strategy_summary(
    {
        "strategy_rule_resolution": profile["strategy_rule_resolution"],
        "strategy_lines": profile["strategy_lines"],
    }
)
strategy_cols = [st.container(), st.container()] if mobile else st.columns(2)
with strategy_cols[0]:
    with st.expander("タグを編集", expanded=False):
        render_stock_tag_editor(stock)
with strategy_cols[1]:
    with st.expander("個別ルールを編集", expanded=False):
        render_individual_rule_editor(
            stock, profile.get("individual_strategy_rule")
        )

st.subheader("決算")
earnings_cols = [st.container(), st.container(), st.container()] if mobile else st.columns(3)
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

reference_cols = [st.container(), st.container()] if mobile else st.columns(2)
with reference_cols[0]:
    st.subheader("EDINET")
    if profile["edinet_documents"]:
        for row in profile["edinet_documents"][:5]:
            st.write(
                f"{row.get('submitted_at') or '提出日不明'} / "
                f"{row.get('document_type') or '書類種別不明'}"
            )
            if row.get("description"):
                st.caption(str(row["description"]))
            if row.get("reference_url"):
                st.link_button(
                    "EDINET書類を開く",
                    str(row["reference_url"]),
                    key=f"edinet_link_{row['id']}",
                )
    else:
        st.info("保存済みのEDINET書類はありません。")

with reference_cols[1]:
    st.subheader("関連銘柄")
    if profile["relations"]:
        for index, row in enumerate(profile["relations"]):
            st.write(f"{row['direction_label']}: {row['related_ticker']} {row['related_company_name']}")
            st.caption(f"関係: {row['relation_type']} / 影響度: {row['impact_level']}")
            company_profile_button(
                row["related_ticker"],
                "関連企業のカルテを開く",
                key=f"related_profile_{index}_{row['related_ticker']}",
            )
    else:
        st.info("関連銘柄はありません。")

st.subheader("テーマ・投資ストーリー")
intelligence = profile["intelligence"]
with st.form(f"company_intelligence_{stock['id']}"):
    intelligence_cols = [st.container(), st.container()] if mobile else st.columns([1, 2])
    with intelligence_cols[0]:
        themes = st.text_area(
            "テーマ",
            intelligence.get("themes") or "",
            height=120,
            placeholder="AI、データセンター、電線",
        )
        st.caption("カンマ、読点、改行で複数テーマを入力できます。")
    with intelligence_cols[1]:
        investment_story = st.text_area(
            "投資ストーリー",
            intelligence.get("investment_story") or "",
            height=160,
            placeholder="注目する理由、前提、反証条件、確認したい指標を記録します。",
        )

    st.markdown("#### チェックリスト")
    checklist_cols = [st.container() for _ in range(5)] if mobile else st.columns(5)
    checklist_values = {
        "earnings_checked": checklist_cols[0].checkbox(
            "決算確認", bool(intelligence.get("earnings_checked"))
        ),
        "disclosure_checked": checklist_cols[1].checkbox(
            "適時開示確認", bool(intelligence.get("disclosure_checked"))
        ),
        "news_checked": checklist_cols[2].checkbox(
            "ニュース確認", bool(intelligence.get("news_checked"))
        ),
        "edinet_checked": checklist_cols[3].checkbox(
            "EDINET確認", bool(intelligence.get("edinet_checked"))
        ),
        "ai_analyzed": checklist_cols[4].checkbox(
            "AI分析実施", bool(intelligence.get("ai_analyzed"))
        ),
    }
    if st.form_submit_button("企業カルテ情報を保存"):
        try:
            save_company_intelligence(
                int(stock["id"]), themes, investment_story, checklist_values
            )
            st.success("テーマ、投資ストーリー、チェックリストを保存しました。")
            st.rerun()
        except Exception as exc:
            st.error(str(exc))
            logger.exception("企業カルテ情報保存失敗 stock_id=%s", stock["id"])

st.subheader("メモ")
with st.form(f"company_note_{stock['id']}", clear_on_submit=True):
    note_cols = [st.container(), st.container()] if mobile else st.columns([1, 3])
    note_date = note_cols[0].date_input("日付", value=datetime.now().date())
    note_text = note_cols[1].text_area(
        "時系列メモ",
        height=100,
        placeholder="確認した事実、仮説、次回確認事項を記録します。",
    )
    if st.form_submit_button("メモを追加"):
        try:
            add_company_note(
                int(stock["id"]),
                note_text,
                f"{note_date.isoformat()}T00:00:00",
            )
            st.success("メモを追加しました。")
            st.rerun()
        except Exception as exc:
            st.error(str(exc))
            logger.exception("企業メモ追加失敗 stock_id=%s", stock["id"])

if profile["notes"]:
    with st.expander(f"保存済みメモ（{len(profile['notes'])}件）"):
        for row in profile["notes"]:
            note_cols = st.columns([5, 1])
            note_cols[0].write(f"{row['occurred_at']} / {row['note']}")
            if note_cols[1].button("削除", key=f"delete_company_note_{row['id']}"):
                try:
                    delete_company_note(int(row["id"]))
                    st.rerun()
                except Exception as exc:
                    st.error(str(exc))
                    logger.exception("企業メモ削除失敗 note_id=%s", row["id"])

st.subheader("タイムライン")
if profile["timeline"]:
    for row in profile["timeline"][:30]:
        st.write(f"{row.get('occurred_at') or '日時不明'} | {row['event_type']} | {row['title']}")
        st.caption(f"状態・重要度: {row['importance']}")
else:
    st.info("タイムラインに表示する情報はありません。")

st.subheader("ChatGPT分析用プロンプト")
st.text_area("企業カルテ分析用プロンプト", profile["prompt"], height=520)
