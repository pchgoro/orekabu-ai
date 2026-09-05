"""Manage theme categories, category price lines, and stock assignments."""

from __future__ import annotations

import streamlit as st

from components.layout import apply_responsive_styles
from components.navigation import company_profile_button
from services.categories import (
    delete_category,
    enrich_rows_with_categories,
    list_categories,
    list_stock_categories,
    save_category,
    save_category_rule,
    set_category_active,
)
from services.database import get_stocks, init_db, load_settings
from services.stock_data import build_analysis_rows
from services.stock_scores import get_trade_rule, save_trade_rule
from utils.formatters import fmt_price, fmt_signed_price
from utils.logging_config import setup_logging

st.set_page_config(page_title="テーマ管理 - オレ株AI", layout="wide")
setup_logging(); init_db()
settings = load_settings()
apply_responsive_styles(settings["display_density"])
st.title("テーマ管理")
st.caption("テーマ・投資分類を銘柄へ複数割り当てし、カテゴリ別の状況を確認します。カテゴリルールは参考ラインであり、売買推奨ではありません。")

rows = build_analysis_rows(get_stocks(), settings)
rows_with_cats = enrich_rows_with_categories(rows)
tabs = st.tabs(["カテゴリ一覧", "カテゴリ編集", "銘柄別一覧", "価格ライン", "投資ルール"])

with tabs[0]:
    categories = list_categories(include_inactive=True)
    if categories:
        cat_holdings = {}
        for r in rows_with_cats:
            if not r.get("is_holding") or not r.get("shares"):
                continue
            curr_price = r.get("current_price") or 0.0
            shares = r.get("shares") or 0
            value = shares * curr_price
            pl = r.get("profit_loss") or (shares * (curr_price - (r.get("average_price") or 0.0)))
            for sc in r.get("stock_categories") or []:
                cat_id = sc["id"]
                if cat_id not in cat_holdings:
                    cat_holdings[cat_id] = {"value": 0.0, "profit_loss": 0.0}
                cat_holdings[cat_id]["value"] += value
                cat_holdings[cat_id]["profit_loss"] += pl

        st.dataframe(
            [{
                "カテゴリ": row["name"], "状態": "有効" if row["is_active"] else "無効",
                "銘柄数": row["stock_count"],
                "評価額": fmt_price(cat_holdings.get(row["id"], {}).get("value", 0.0)),
                "損益": fmt_signed_price(cat_holdings.get(row["id"], {}).get("profit_loss", 0.0)),
                "ニュース": row["news_count"],
                "決算": row["earnings_count"], "開示": row["disclosure_count"],
            } for row in categories],
            use_container_width=True, hide_index=True,
        )
    else:
        st.info("カテゴリはありません。")

with tabs[1]:
    categories = list_categories(include_inactive=True)
    with st.form("create_category", clear_on_submit=True):
        name = st.text_input("新しいカテゴリ名")
        description = st.text_input("説明")
        if st.form_submit_button("カテゴリを追加"):
            try:
                save_category(name, description)
                st.success("カテゴリを追加しました。")
                st.rerun()
            except ValueError as exc:
                st.error(str(exc))
    for row in categories:
        with st.expander(f"{row['name']} ({'有効' if row['is_active'] else '無効'})"):
            with st.form(f"edit_category_{row['id']}"):
                name = st.text_input("カテゴリ名", row["name"])
                description = st.text_area("説明", row["description"])
                if st.form_submit_button("変更を保存"):
                    try:
                        save_category(name, description, row["color_key"], category_id=int(row["id"]))
                        st.success("カテゴリを更新しました。")
                        st.rerun()
                    except ValueError as exc:
                        st.error(str(exc))
            actions = st.columns(2)
            if actions[0].button("無効化" if row["is_active"] else "有効化", key=f"toggle_category_{row['id']}"):
                set_category_active(int(row["id"]), not bool(row["is_active"]))
                st.rerun()
            if actions[1].button("未使用なら削除", key=f"delete_category_{row['id']}"):
                try:
                    delete_category(int(row["id"]))
                    st.rerun()
                except ValueError as exc:
                    st.warning(str(exc))

with tabs[2]:
    rows = build_analysis_rows(get_stocks(), settings)
    categories = list_categories()
    selected_name = st.selectbox("カテゴリで絞り込み", ["すべて", *[row["name"] for row in categories]])
    selected_id = next((int(row["id"]) for row in categories if row["name"] == selected_name), None)
    for row in rows:
        assigned = list_stock_categories(int(row["id"]))
        if selected_id is not None and selected_id not in {int(item["id"]) for item in assigned}:
            continue
        with st.container(border=True):
            st.write(f"**{row['ticker']} {row['company_name']}**")
            st.caption(" / ".join(item["name"] for item in assigned) or "カテゴリ未設定")
            col1, col2, col3 = st.columns(3)
            col1.metric("現在値", fmt_price(row.get("current_price")))
            col2.metric("評価損益", fmt_signed_price(row.get("profit_loss")))
            col3.metric("スコア", row.get("score") if row.get("score") is not None else "データなし")
            company_profile_button(row["ticker"], "企業カルテを開く", key=f"category_profile_{row['id']}")

with tabs[3]:
    categories = list_categories()
    if not categories:
        st.info("先にカテゴリを追加してください。")
    else:
        selected_id = st.selectbox(
            "設定するカテゴリ", [int(row["id"]) for row in categories],
            format_func=lambda category_id: next(row["name"] for row in categories if int(row["id"]) == category_id),
        )
        selected = next(row for row in categories if int(row["id"]) == selected_id)
        with st.form(f"category_rule_{selected_id}"):
            stop_loss = st.number_input("損切りライン", min_value=0.0, value=float(selected.get("stop_loss_price") or 0.0))
            take_profit = st.number_input("利確ライン", min_value=0.0, value=float(selected.get("take_profit_price") or 0.0))
            add_position = st.number_input("買い増しライン", min_value=0.0, value=float(selected.get("add_position_price") or 0.0))
            memo = st.text_area("ルールメモ", selected.get("rule_memo") or "")
            if st.form_submit_button("カテゴリルールを保存"):
                try:
                    save_category_rule(selected_id, {
                        "stop_loss_price": stop_loss or None,
                        "take_profit_price": take_profit or None,
                        "add_position_price": add_position or None,
                        "memo": memo,
                    })
                    st.success("カテゴリルールを保存しました。")
                    st.rerun()
                except ValueError as exc:
                    st.error(str(exc))

with tabs[4]:
    categories = list_categories()
    if not categories:
        st.info("先にカテゴリを追加してください。")
    else:
        selected_id = st.selectbox(
            "設定するカテゴリ", [int(row["id"]) for row in categories],
            format_func=lambda category_id: next(row["name"] for row in categories if int(row["id"]) == category_id),
            key="trade_rule_category",
        )
        rule = get_trade_rule(selected_id) or {}
        with st.form(f"trade_rule_{selected_id}"):
            buy_conditions = st.text_area("買い条件", rule.get("buy_conditions") or "", height=100)
            add_conditions = st.text_area("買い増し条件", rule.get("add_position_conditions") or "", height=100)
            cols = st.columns(3)
            take_profit = cols[0].number_input("利確ライン (%)", min_value=0.0, max_value=100.0, value=float(rule.get("take_profit_percent") or 0.0))
            stop_loss = cols[1].number_input("損切りライン (%)", min_value=0.0, max_value=100.0, value=float(rule.get("stop_loss_percent") or 0.0))
            max_ratio = cols[2].number_input("最大保有比率 (%)", min_value=0.0, max_value=100.0, value=float(rule.get("max_holding_ratio_percent") or 0.0))
            memo = st.text_area("ルールメモ", rule.get("memo") or "", height=80)
            if st.form_submit_button("投資ルールを保存"):
                try:
                    save_trade_rule(selected_id, {
                        "buy_conditions": buy_conditions,
                        "add_position_conditions": add_conditions,
                        "take_profit_percent": take_profit or None,
                        "stop_loss_percent": stop_loss or None,
                        "max_holding_ratio_percent": max_ratio or None,
                        "memo": memo,
                    })
                    st.success("投資ルールを保存しました。")
                    st.rerun()
                except ValueError as exc:
                    st.error(str(exc))
