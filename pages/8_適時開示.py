"""Manual disclosure management, CSV import, and news linking page."""

from __future__ import annotations

import logging
from datetime import datetime

import streamlit as st

from components.navigation import company_profile_button

from components.layout import apply_responsive_styles
from services.database import get_stocks, init_db
from services.disclosures import (
    DISCLOSURE_DIR,
    delete_disclosure,
    export_csv,
    import_csv,
    list_disclosures,
    list_import_runs,
    list_news_links,
    make_prompt,
    parse_csv,
    save_disclosure,
    save_uploaded_pdf,
    set_news_link,
    set_tags,
    update_disclosure,
)
from services.news import list_articles
from utils.constants import DISCLOSURE_IMPORTANCE_LEVELS, DISCLOSURE_MAX_FILE_SIZE, DISCLOSURE_TYPES
from utils.logging_config import setup_logging

logger = logging.getLogger(__name__)
st.set_page_config(page_title="適時開示 - オレ株AI", layout="wide")
setup_logging(); init_db(); apply_responsive_styles()
st.title("適時開示")
st.caption("適時開示を手動で整理する機能です。売買推奨やTDnetの自動取得、PDF本文解析は行いません。")

stocks = get_stocks()
stock_options = {f"{row['ticker']} {row['company_name']}": row for row in stocks}
tabs = st.tabs(["最新", "保有株", "監視銘柄", "未読", "お気に入り", "手動登録", "CSV", "取込履歴", "設定"])

for tab, filter_name in zip(tabs[:5], ["最新", "保有株", "監視銘柄", "未読", "お気に入り"]):
    with tab:
        rows = list_disclosures(filter_name=filter_name)
        if not rows:
            st.info("該当する開示はありません。")
            continue
        for row in rows[:30]:
            with st.expander(f"{row['ticker']} {row['disclosure_type']} | {row['title']}"):
                company_profile_button(
                    row["ticker"],
                    "企業カルテを開く",
                    key=f"disclosure_profile_{filter_name}_{row['id']}",
                )
                st.write(f"開示日時: {row['disclosed_at']} / 重要度: {row['importance']} / {'既読' if row['is_read'] else '未読'}")
                st.write(row.get("summary") or "要約なし")
                if row.get("source_url"): st.link_button("元ページを開く", row["source_url"])
                if row.get("document_url"): st.link_button("PDF URLを開く", row["document_url"])
                if row.get("local_file_path"): st.caption(f"ローカルPDF: {row['local_file_path']}")
                key = f"disclosure_{filter_name}_{row['id']}"
                read = st.checkbox("既読", bool(row["is_read"]), key=f"read_{key}")
                favorite = st.checkbox("お気に入り", bool(row["is_favorite"]), key=f"fav_{key}")
                importance = st.selectbox("重要度", DISCLOSURE_IMPORTANCE_LEVELS, index=DISCLOSURE_IMPORTANCE_LEVELS.index(row["importance"]), key=f"importance_{key}")
                tags = st.text_input("タグ", row.get("tags") or "", key=f"tags_{key}")
                memo = st.text_area("メモ", row.get("user_memo") or "", key=f"memo_{key}")
                if st.button("開示情報を保存", key=f"save_{key}"):
                    try:
                        update_disclosure(int(row["id"]), {**row, "is_read": read, "is_favorite": favorite, "importance": importance, "user_memo": memo})
                        set_tags(int(row["id"]), tags.split(",")); st.success("保存しました。"); st.rerun()
                    except Exception as exc:
                        st.error(str(exc)); logger.exception("開示更新失敗 disclosure_id=%s", row["id"])
                links = list_news_links(int(row["id"]))
                if links:
                    st.write("関連ニュース候補")
                    for link in links:
                        cols = st.columns([5, 2])
                        cols[0].write(f"{link['title']} / {link['match_reason'] or '手動'}")
                        label = "関連解除" if link["confirmed"] else "関連を承認"
                        if cols[1].button(label, key=f"link_{key}_{link['news_article_id']}"):
                            set_news_link(int(row["id"]), int(link["news_article_id"]), not bool(link["confirmed"])); st.rerun()
                articles = list_articles()
                if articles:
                    news_options = {f"{article['id']}: {article['title'][:60]}": article for article in articles}
                    selected_news = news_options[st.selectbox("ニュースを手動関連付け", list(news_options), key=f"news_{key}")]
                    if st.button("ニュースを関連付ける", key=f"add_news_{key}"):
                        set_news_link(int(row["id"]), int(selected_news["id"]), True); st.rerun()
                st.text_area("ChatGPT開示分析用プロンプト", make_prompt(row), height=420, key=f"prompt_{key}")
                delete_confirm = st.checkbox("削除を確認しました", key=f"delete_confirm_{key}")
                if st.button("開示を削除", disabled=not delete_confirm, key=f"delete_{key}"):
                    try: delete_disclosure(int(row["id"])); st.rerun()
                    except Exception as exc: st.error(str(exc)); logger.exception("開示削除失敗 disclosure_id=%s", row["id"])

with tabs[5]:
    if not stocks:
        st.info("先に銘柄を登録してください。")
    else:
        with st.form("disclosure_manual"):
            stock_label = st.selectbox("銘柄", list(stock_options))
            cols = st.columns(2)
            disclosure_type = cols[0].selectbox("開示種別", DISCLOSURE_TYPES)
            importance = cols[1].selectbox("重要度", DISCLOSURE_IMPORTANCE_LEVELS)
            title = st.text_input("タイトル")
            disclosed_date = st.date_input("開示日")
            disclosed_time = st.time_input("開示時刻")
            source_name = st.text_input("出典")
            source_url = st.text_input("元URL")
            document_url = st.text_input("PDF URL")
            local_path = st.text_input("既存ローカルPDF（data/disclosures配下）")
            upload = st.file_uploader("PDF添付", type=["pdf"])
            summary = st.text_area("短い要約")
            tags = st.text_input("タグ（カンマ区切り）")
            memo = st.text_area("メモ")
            external_id = st.text_input("外部ID（任意）")
            submitted = st.form_submit_button("開示を登録")
        if submitted:
            try:
                stored_path = save_uploaded_pdf(upload.name, upload.getvalue()) if upload else local_path
                status, disclosure_id = save_disclosure({
                    "stock_id": stock_options[stock_label]["id"], "disclosure_type": disclosure_type,
                    "title": title, "disclosed_at": datetime.combine(disclosed_date, disclosed_time),
                    "source_name": source_name, "source_url": source_url, "document_url": document_url,
                    "local_file_path": stored_path, "summary": summary, "importance": importance,
                    "user_memo": memo, "external_id": external_id,
                })
                if status == "duplicate": st.warning("同じ開示は登録済みです。")
                else:
                    set_tags(disclosure_id, tags.split(",")); st.success("開示を登録しました。"); st.rerun()
            except Exception as exc:
                st.error(str(exc)); logger.exception("手動開示登録失敗 ticker=%s", stock_options[stock_label]["ticker"])

with tabs[6]:
    st.download_button("開示CSVをダウンロード", export_csv(), "orekabu_disclosures.csv", "text/csv")
    upload_csv = st.file_uploader("開示CSVをインポート", type=["csv"], key="disclosure_csv")
    if upload_csv:
        preview, errors = parse_csv(upload_csv)
        for error in errors: st.error(error)
        if not errors:
            st.dataframe(preview, use_container_width=True, hide_index=True)
            update_existing = st.radio("重複データ", ["更新", "スキップ"], horizontal=True) == "更新"
            if st.button("開示CSVインポート実行"):
                result = import_csv(preview, update_existing)
                st.write(f"成功: {result['inserted']} / 更新: {result['updated']} / スキップ: {result['skipped']} / 失敗: {result['failed']}")
                for error in result["errors"]: st.error(error)

with tabs[7]:
    runs = list_import_runs()
    if runs: st.dataframe(runs, use_container_width=True, hide_index=True)
    else: st.info("取込履歴はありません。")

with tabs[8]:
    st.write("PDF保存先")
    st.code(str(DISCLOSURE_DIR))
    st.write(f"ファイルサイズ上限: {DISCLOSURE_MAX_FILE_SIZE // 1024 // 1024}MB")
    st.caption("TDnet自動巡回、PDF本文解析、AI要約、通知はこのバージョンでは行いません。")
