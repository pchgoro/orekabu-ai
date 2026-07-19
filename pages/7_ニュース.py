"""Local RSS, manual, and CSV news management page."""

from __future__ import annotations

import logging
import sqlite3

import streamlit as st

from components.navigation import company_profile_button

from components.tables import news_dataframe
from components.news_cards import render_news_cards
from components.layout import apply_responsive_styles
from services.database import get_stocks, init_db, load_settings
from services.news import (
    add_keyword, add_source, confirm_stock_match, delete_keyword, delete_source, export_csv,
    fetch_enabled_sources, get_article_tags, import_csv, list_articles, list_fetch_runs,
    list_keywords, list_sources, list_stock_matches, make_news_prompt, parse_csv, save_article,
    set_article_tags, update_article, update_source,
)
from services.news_providers.manual_provider import ManualNewsProvider
from services.news_providers.rss_provider import RssNewsProvider
from services.disclosures import links_for_news
from utils.constants import NEWS_CATEGORIES, NEWS_IMPORTANCE_LEVELS, NEWS_SOURCE_TYPES
from utils.logging_config import setup_logging

logger = logging.getLogger(__name__)
st.set_page_config(page_title="ニュース - オレ株AI", layout="wide")
setup_logging(); init_db()
st.title("ニュース")
st.caption("ニュースは判断材料の整理用です。AI要約や売買推奨は行いません。RSS要約のみ保存し、本文全文は保存しません。")
if flash := st.session_state.pop("news_flash", None):
    st.success(flash)

stocks = get_stocks()
settings = load_settings()
apply_responsive_styles(settings["display_density"])
card_mode = settings["news_display_mode"] == "カード" or bool(settings["mobile_priority_display"])
stock_options = {f"{s['ticker']} {s['company_name']}": s for s in stocks}
tabs = st.tabs(["最新", "保有株", "監視銘柄", "未読", "お気に入り", "ソース管理", "キーワード管理", "手動登録", "CSV", "取得履歴"])

for tab, filter_name in zip(tabs[:5], ["最新", "保有株", "監視銘柄", "未読", "お気に入り"]):
    with tab:
        rows = list_articles(filter_name=filter_name)
        if rows:
            if card_mode:
                render_news_cards(rows[:20], f"direct_{filter_name}")
            else:
                st.dataframe(news_dataframe(rows), use_container_width=True, hide_index=True, height=480)
            labels = {f"{r['id']}: {r['title'][:70]}": r for r in rows}
            selected = labels[st.selectbox("管理する記事", list(labels), key=f"article_{filter_name}")]
            article_key = f"{filter_name}_{selected['id']}"
            with st.expander("記事の状態・銘柄候補・タグ・プロンプト", expanded=False):
                if selected.get("url"):
                    st.link_button("元記事を開く", selected["url"])
                read = st.checkbox("既読", value=bool(selected["is_read"]), key=f"read_{article_key}")
                favorite = st.checkbox("お気に入り", value=bool(selected["is_favorite"]), key=f"fav_{article_key}")
                importance = st.selectbox("重要度", NEWS_IMPORTANCE_LEVELS, index=NEWS_IMPORTANCE_LEVELS.index(selected["importance"]), key=f"importance_{article_key}")
                category = st.selectbox("カテゴリ", NEWS_CATEGORIES, index=NEWS_CATEGORIES.index(selected["category"]), key=f"category_{article_key}")
                memo = st.text_area("メモ", value=selected.get("memo") or "", key=f"memo_{article_key}")
                tags = st.text_input("タグ（カンマ区切り）", value=", ".join(get_article_tags(int(selected["id"]))), key=f"tags_{article_key}")
                if st.button("記事情報を保存", key=f"save_{article_key}"):
                    try:
                        update_article(int(selected["id"]), {"is_read": read, "is_favorite": favorite, "importance": importance, "category": category, "memo": memo})
                        set_article_tags(int(selected["id"]), tags.split(",")); st.success("記事情報を保存しました。"); st.rerun()
                    except Exception: st.error("保存できませんでした。ログを確認してください。"); logger.exception("ニュース記事更新失敗 article_id=%s", selected["id"])
                matches = list_stock_matches(article_id=int(selected["id"]))
                if matches:
                    st.write("銘柄候補（ルール一致）")
                    for match in matches:
                        cols = st.columns([3, 4, 2])
                        with cols[0]:
                            st.write(f"{match['ticker']} {match['company_name']}")
                            company_profile_button(
                                match["ticker"],
                                "企業カルテ",
                                key=f"news_match_profile_{article_key}_{match['ticker']}",
                            )
                        cols[1].write(match["match_reason"] or "一致理由なし")
                        if cols[2].button("承認" if not match["confirmed"] else "未承認へ", key=f"match_{article_key}_{match['stock_id']}"):
                            confirm_stock_match(int(selected["id"]), int(match["stock_id"]), not bool(match["confirmed"])); st.rerun()
                related_disclosures = links_for_news(int(selected["id"]))
                if related_disclosures:
                    st.write("関連開示")
                    for disclosure in related_disclosures:
                        st.write(f"{disclosure['ticker']} / {disclosure['disclosure_type']} / {disclosure['title']}")
                st.text_area("ChatGPTニュース分析用プロンプト", make_news_prompt(selected), height=420, key=f"prompt_{article_key}")
        else:
            st.info("該当するニュースはありません。")

with tabs[5]:
    sources = list_sources()
    with st.form("source_create"):
        cols = st.columns(2); source_name = cols[0].text_input("ソース名"); source_type = cols[1].selectbox("種別", NEWS_SOURCE_TYPES)
        source_url = st.text_input("URL"); source_enabled = st.checkbox("有効", value=True); source_memo = st.text_input("メモ")
        source_submit = st.form_submit_button("ソースを登録")
    if source_submit:
        try: add_source({"name": source_name, "source_type": source_type, "url": source_url, "is_enabled": source_enabled, "memo": source_memo}); st.success("登録しました。"); st.rerun()
        except (ValueError, sqlite3.IntegrityError) as exc: st.error(str(exc)); logger.exception("ニュースソース登録失敗 name=%s", source_name)
    if sources:
        st.dataframe(sources, use_container_width=True, hide_index=True)
        source_labels = {f"{s['name']} ({s['source_type']})": s for s in sources}; selected_source = source_labels[st.selectbox("編集するソース", list(source_labels))]
        source_edit_key = f"source_edit_{selected_source['id']}"
        with st.expander("ソースを編集・削除"):
            edit_name = st.text_input("ソース名", selected_source["name"], key=f"{source_edit_key}_name")
            edit_type = st.selectbox("種別", NEWS_SOURCE_TYPES, index=NEWS_SOURCE_TYPES.index(selected_source["source_type"]), key=f"{source_edit_key}_type")
            edit_url = st.text_input("URL", selected_source["url"], key=f"{source_edit_key}_url"); edit_enabled = st.checkbox("有効", bool(selected_source["is_enabled"]), key=f"{source_edit_key}_enabled")
            edit_memo = st.text_input("メモ", selected_source["memo"], key=f"{source_edit_key}_memo")
            if st.button("ソースを更新", key=f"{source_edit_key}_update"):
                try: update_source(int(selected_source["id"]), {"name": edit_name, "source_type": edit_type, "url": edit_url, "is_enabled": edit_enabled, "memo": edit_memo}); st.success("更新しました。"); st.rerun()
                except Exception as exc: st.error(str(exc)); logger.exception("ニュースソース更新失敗 source_id=%s", selected_source["id"])
            delete_confirm = st.checkbox("削除を確認しました", key=f"{source_edit_key}_delete_confirm")
            if st.button("ソースを削除", disabled=not delete_confirm, key=f"{source_edit_key}_delete"): delete_source(int(selected_source["id"])); st.rerun()
    if st.button("有効なRSS/Atomを取得"):
        result = fetch_enabled_sources(lambda source: RssNewsProvider(source["url"]))
        if result["errors"]:
            for error in result["errors"]: st.error(error)
        else:
            st.session_state["news_flash"] = f"新規: {result['inserted']}件 / 重複: {result['duplicates']}件 / 失敗: {result['failed']}件"
            st.rerun()

with tabs[6]:
    keywords = list_keywords()
    if stocks:
        with st.form("keyword_create"):
            keyword_stock = st.selectbox("銘柄", list(stock_options)); keyword = st.text_input("キーワード"); keyword_submit = st.form_submit_button("キーワードを登録")
        if keyword_submit:
            try: add_keyword(int(stock_options[keyword_stock]["id"]), keyword); st.success("登録しました。"); st.rerun()
            except Exception as exc: st.error(str(exc)); logger.exception("ニュースキーワード登録失敗")
    if keywords:
        st.dataframe(keywords, use_container_width=True, hide_index=True)
        keyword_labels = {f"{k['ticker']} / {k['keyword']}": k for k in keywords}; selected_keyword = keyword_labels[st.selectbox("削除するキーワード", list(keyword_labels))]
        if st.button("キーワードを削除"): delete_keyword(int(selected_keyword["id"])); st.rerun()

with tabs[7]:
    with st.form("manual_article"):
        title = st.text_input("タイトル"); url = st.text_input("URL"); published = st.text_input("公開日時（ISO形式、任意）")
        author = st.text_input("著者"); summary = st.text_area("要約"); importance = st.selectbox("重要度", NEWS_IMPORTANCE_LEVELS); category = st.selectbox("カテゴリ", NEWS_CATEGORIES)
        manual_submit = st.form_submit_button("記事を登録")
    if manual_submit:
        try:
            item = ManualNewsProvider({"title": title, "url": url, "published_at": published or None, "author": author, "summary": summary}).fetch()[0]
            status, _ = save_article(item, metadata={"importance": importance, "category": category})
            st.session_state["news_flash"] = "登録しました。" if status == "inserted" else "同じ記事は登録済みです。"
            st.rerun()
        except Exception as exc: st.error(str(exc)); logger.exception("手動ニュース登録失敗")

with tabs[8]:
    kind_labels = {"記事": "articles", "ソース": "sources", "キーワード": "keywords"}; kind_label = st.selectbox("CSV種別", list(kind_labels)); kind = kind_labels[kind_label]
    st.download_button(f"{kind_label}CSVをダウンロード", export_csv(kind), f"orekabu_news_{kind}.csv", "text/csv")
    upload = st.file_uploader(f"{kind_label}CSVをインポート", type=["csv"], key="news_csv")
    if upload:
        preview, errors = parse_csv(upload, kind)
        for error in errors: st.error(error)
        if not errors:
            st.dataframe(preview, use_container_width=True, hide_index=True); update_existing = st.radio("既存データ", ["更新", "スキップ"], horizontal=True) == "更新"
            if st.button("CSVインポート実行"):
                result = import_csv(preview, kind, update_existing); st.write(f"成功: {result['inserted']} / 更新: {result['updated']} / スキップ: {result['skipped']} / 失敗: {result['failed']}")
                for error in result["errors"]: st.error(error)

with tabs[9]:
    runs = list_fetch_runs()
    if runs: st.dataframe(runs, use_container_width=True, hide_index=True)
    else: st.info("取得履歴はありません。")
