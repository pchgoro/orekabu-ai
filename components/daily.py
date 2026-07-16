"""Reusable daily briefing and mobile-first card renderers."""

from __future__ import annotations

from typing import Any

import streamlit as st

from utils.formatters import fmt_number, fmt_price

PAGE_TARGETS = {
    "app": "app.py",
    "決算": "pages/5_決算.py",
    "ニュース": "pages/7_ニュース.py",
    "買い検討ライン": "pages/3_買い検討ライン.py",
    "保有株": "pages/1_保有株.py",
    "監視銘柄": "pages/2_監視銘柄.py",
    "適時開示": "pages/8_適時開示.py",
}


def render_briefing(items: list[dict[str, Any]], limit: int, hide_zero: bool, compact: bool) -> None:
    """Render briefing counts in at most two columns for narrow-screen safety."""
    visible = [item for item in items if item["count"] or not hide_zero][:limit]
    st.subheader("今日のブリーフィング")
    if not visible:
        st.caption("現時点で確認が必要な項目はありません。")
        return
    columns = st.columns(2)
    for index, item in enumerate(visible):
        with columns[index % 2]:
            st.metric(item["label"], item["count"])
            if not compact and item["count"] and item["page"] != "app":
                st.page_link(PAGE_TARGETS[item["page"]], label=f"{item['label']}を開く")


def render_daily_tasks(tasks: list[dict[str, Any]]) -> None:
    """Render prioritized actions with explicit destinations."""
    st.subheader("今日やること")
    if not tasks:
        st.caption("優先して確認する項目はありません。")
        return
    for task in tasks:
        cols = st.columns([1, 4, 2])
        cols[0].write(f"優先 {task['priority']}")
        cols[1].write(f"**{task['label']}** - {task['detail']}")
        cols[2].page_link(PAGE_TARGETS[task["page"]], label="確認する")


def render_stock_cards(rows: list[dict[str, Any]], holding: bool) -> None:
    """Render important stock fields without a wide table."""
    if not rows:
        st.info("表示する銘柄がありません。")
        return
    for row in rows:
        title = f"{row.get('ticker') or '銘柄不明'} {row.get('company_name') or ''}"
        with st.expander(title, expanded=False):
            cols = st.columns(2)
            cols[0].metric("現在値", fmt_price(row.get("current_price")))
            cols[1].metric("注目スコア", fmt_number(row.get("score"), 0))
            st.write(f"決算: {row.get('next_earnings_date_display') or '未登録'} / {row.get('earnings_status') or '未登録'}")
            if holding:
                st.write(f"保有株数: {row.get('shares') or 0} / 評価損益: {fmt_price(row.get('profit'))}")
            else:
                st.write(f"分類: {row.get('category') or 'その他'} / RSI: {fmt_number(row.get('RSI14'))}")
            st.write(f"メモ: {row.get('memo') or 'なし'}")


def render_earnings_cards(rows: list[dict[str, Any]]) -> None:
    """Render earnings essentials as narrow-screen cards."""
    if not rows:
        st.info("表示する決算予定はありません。")
        return
    for row in rows:
        with st.expander(_earnings_title(row), expanded=False):
            st.write(f"決算日: {row.get('earnings_date_display') or '日付未確認'}")
            st.write(f"状態: {row.get('earnings_status') or '日付未確認'} / {row.get('days_label') or '日付未確認'}")
            st.write(f"四半期: {row.get('fiscal_quarter') or '未設定'} / 発表時間: {row.get('announcement_time_display') or '未定'}")
            st.write(f"メモ: {row.get('memo_display') or 'なし'}")


def _earnings_title(row: dict[str, Any]) -> str:
    return " ".join(part for part in [str(row.get("ticker") or ""), str(row.get("company_name") or "")] if part).strip() or "決算予定"
