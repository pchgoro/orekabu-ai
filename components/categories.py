"""Reusable Streamlit controls for stock theme categories and trade notes."""

from __future__ import annotations

import streamlit as st

from services.categories import (
    get_trade_notes,
    list_categories,
    list_stock_categories,
    replace_stock_categories,
    save_trade_notes,
)


def render_stock_category_editor(stock_id: int) -> None:
    """Render category assignment form for one stock."""
    categories = list_categories()
    assigned = {int(row["id"]) for row in list_stock_categories(stock_id)}
    selected = st.multiselect(
        "カテゴリ",
        options=[int(row["id"]) for row in categories],
        default=[int(row["id"]) for row in categories if int(row["id"]) in assigned],
        format_func=lambda category_id: next(
            row["name"] for row in categories if int(row["id"]) == category_id
        ),
        key=f"stock_categories_{stock_id}",
        help="テーマ・投資スタイル・保有期間などを複数選択できます。",
    )
    if st.button("カテゴリを保存", key=f"save_stock_categories_{stock_id}"):
        replace_stock_categories(stock_id, selected)
        st.success("カテゴリを保存しました。")
        st.rerun()


def render_trade_notes_editor(stock_id: int) -> None:
    """Render one stock's rationale, exit conditions, and free note editor."""
    notes = get_trade_notes(stock_id)
    with st.form(f"trade_notes_{stock_id}"):
        holding_reason = st.text_area(
            "保有理由", notes.get("holding_reason") or "", height=100,
        )
        sell_conditions = st.text_area(
            "売却条件", notes.get("sell_conditions") or "", height=100,
        )
        memo = st.text_area("自由メモ", notes.get("memo") or "", height=120)
        if st.form_submit_button("保有メモを保存"):
            save_trade_notes(
                stock_id,
                {"holding_reason": holding_reason, "sell_conditions": sell_conditions, "memo": memo},
            )
            st.success("保有理由・売却条件・メモを保存しました。")
            st.rerun()


def render_category_badges(categories: list[dict]) -> None:
    """Show assigned category names without requiring an edit interaction."""
    if not categories:
        st.caption("カテゴリは未設定です。")
        return
    st.caption(" / ".join(str(row.get("name") or "") for row in categories))
