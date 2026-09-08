"""Compact news cards with direct state controls."""

from __future__ import annotations

from typing import Any

import streamlit as st

from components.navigation import company_profile_button
from components.ui import empty_state, render_priority_badge
from services.news import make_news_prompt, update_article
from utils.constants import NEWS_IMPORTANCE_LEVELS


def render_news_cards(rows: list[dict[str, Any]], key_prefix: str) -> None:
    """Render direct read, favorite, importance, link, and detail actions."""
    if not rows:
        empty_state("該当するニュースはありません。")
        return
    for row in rows:
        article_id = int(row["id"])
        grouped = int(row.get("event_record_count") or 1) > 1
        state = "既読" if row.get("is_read") else "未読"
        with st.container(border=True):
            render_priority_badge(
                "urgent" if row.get("importance") == "高" and not row.get("is_read")
                else "today" if not row.get("is_read") else "later"
            )
            st.markdown(f"**{row.get('title') or 'タイトルなし'}**")
            group_count = int(row.get("event_record_count") or 1)
            grouped_label = f" / 同一材料{group_count}件" if group_count > 1 else ""
            st.caption(f"{state} / 重要度: {row.get('importance') or '通常'} / {row.get('source_name') or 'ソース不明'}{grouped_label}")
            stock_label = str(row.get("stock_labels") or "").split(",")[0].strip()
            if stock_label:
                company_profile_button(
                    stock_label.split()[0],
                    "企業カルテを開く",
                    key=f"{key_prefix}_profile_{article_id}",
                )
            cols = st.columns(2)
            if cols[0].button("未読に戻す" if row.get("is_read") else "既読にする", disabled=grouped, key=f"{key_prefix}_read_{article_id}"):
                _save(row, is_read=not bool(row.get("is_read")))
                st.rerun()
            if cols[1].button("お気に入り解除" if row.get("is_favorite") else "お気に入り登録", disabled=grouped, key=f"{key_prefix}_fav_{article_id}"):
                _save(row, is_favorite=not bool(row.get("is_favorite")))
                st.rerun()
            importance = st.selectbox("重要度", NEWS_IMPORTANCE_LEVELS, index=NEWS_IMPORTANCE_LEVELS.index(row.get("importance") or "通常"), disabled=grouped, key=f"{key_prefix}_importance_{article_id}")
            if importance != row.get("importance"):
                _save(row, importance=importance)
                st.rerun()
            if row.get("url"):
                st.link_button("元記事を開く", row["url"])
            with st.expander("詳細を表示"):
                if grouped:
                    for source_index, provenance in enumerate(row.get("event_provenance") or []):
                        for url_index, source_url in enumerate(provenance.get("urls") or [provenance.get("url")]):
                            if source_url:
                                st.link_button(
                                    f"原典 {source_index + 1}-{url_index + 1}: {provenance.get('source') or 'source'}",
                                    source_url,
                                    key=f"{key_prefix}_provenance_{article_id}_{source_index}_{url_index}",
                                )
                st.write(row.get("summary") or "要約なし")
                st.write(f"関連銘柄: {row.get('stock_labels') or 'なし'}")
                st.write(f"メモ: {row.get('memo') or 'なし'}")
                st.text_area("ChatGPTニュース分析用プロンプト", make_news_prompt(row), height=280, key=f"{key_prefix}_prompt_{article_id}")


def _save(row: dict[str, Any], **changes: Any) -> None:
    payload = {
        "is_read": bool(row.get("is_read")),
        "is_favorite": bool(row.get("is_favorite")),
        "importance": row.get("importance") or "通常",
        "category": row.get("category") or "その他",
        "memo": row.get("memo") or "",
        **changes,
    }
    update_article(int(row["id"]), payload)
