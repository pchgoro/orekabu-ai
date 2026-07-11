"""Reusable forms for stock CRUD and CSV operations."""

from __future__ import annotations

import csv
import io
import logging
import sqlite3
from typing import Any

import pandas as pd
import streamlit as st

from services.database import add_stock, delete_stock, update_stock, upsert_stock
from utils.constants import CATEGORIES
from utils.validators import parse_bool, validate_stock_payload

logger = logging.getLogger(__name__)

CSV_COLUMNS = ["ticker", "company_name", "category", "is_holding", "shares", "average_price", "buy_watch_price", "memo"]


def stock_form(key: str, stock: dict[str, Any] | None = None) -> dict[str, Any] | None:
    """Render a stock input form and return submitted payload."""
    stock = stock or {}
    with st.form(key):
        cols = st.columns(2)
        ticker = cols[0].text_input("銘柄コード", value=str(stock.get("ticker", "")))
        company_name = cols[1].text_input("会社名", value=str(stock.get("company_name", "")))
        category_default = stock.get("category", "監視銘柄")
        category_index = CATEGORIES.index(category_default) if category_default in CATEGORIES else 1
        category = cols[0].selectbox("分類", CATEGORIES, index=category_index)
        is_holding = cols[1].checkbox("保有株", value=bool(stock.get("is_holding", category == "保有株")))
        shares = cols[0].number_input("保有株数", min_value=0, step=1, value=int(stock.get("shares") or 0))
        average_price = cols[1].number_input("平均取得単価", min_value=0.0, step=1.0, value=float(stock.get("average_price") or 0))
        buy_watch_price = cols[0].number_input("買い検討価格", min_value=0.0, step=1.0, value=float(stock.get("buy_watch_price") or 0))
        memo = st.text_area("メモ", value=str(stock.get("memo", "")), height=90)
        submitted = st.form_submit_button("保存")
    if not submitted:
        return None
    return {
        "ticker": ticker,
        "company_name": company_name,
        "category": "保有株" if is_holding else category,
        "is_holding": is_holding,
        "shares": shares,
        "average_price": average_price,
        "buy_watch_price": buy_watch_price,
        "memo": memo,
    }


def create_stock_section() -> None:
    """Render a create-stock expander."""
    with st.expander("銘柄を登録", expanded=False):
        payload = stock_form("create_stock")
        if payload:
            try:
                add_stock(payload)
                st.success("銘柄を登録しました。")
                st.rerun()
            except sqlite3.IntegrityError:
                st.error("同じ銘柄コードは登録できません。")
                logger.exception("重複登録エラー ticker=%s", payload.get("ticker"))
            except ValueError as exc:
                st.error(str(exc))
            except Exception:
                st.error("登録中にエラーが発生しました。logs/app.logを確認してください。")
                logger.exception("銘柄登録エラー")


def edit_delete_section(stocks: list[dict[str, Any]], key_prefix: str) -> None:
    """Render edit and delete controls for stocks."""
    if not stocks:
        return
    options = {f"{stock['ticker']} {stock['company_name']}": stock for stock in stocks}
    selected_label = st.selectbox("編集する銘柄", list(options.keys()), key=f"{key_prefix}_select")
    stock = options[selected_label]
    with st.expander("選択銘柄を編集・削除", expanded=False):
        payload = stock_form(f"{key_prefix}_edit_{stock['id']}", stock)
        if payload:
            try:
                update_stock(int(stock["id"]), payload)
                st.success("銘柄を更新しました。")
                st.rerun()
            except sqlite3.IntegrityError:
                st.error("同じ銘柄コードは登録できません。")
                logger.exception("更新時の重複エラー ticker=%s", payload.get("ticker"))
            except ValueError as exc:
                st.error(str(exc))
            except Exception:
                st.error("更新中にエラーが発生しました。logs/app.logを確認してください。")
                logger.exception("銘柄更新エラー")
        st.divider()
        confirm = st.checkbox("削除することを確認しました", key=f"{key_prefix}_confirm_{stock['id']}")
        if st.button("削除", disabled=not confirm, key=f"{key_prefix}_delete_{stock['id']}"):
            try:
                delete_stock(int(stock["id"]))
                st.success("銘柄を削除しました。")
                st.rerun()
            except Exception:
                st.error("削除中にエラーが発生しました。logs/app.logを確認してください。")
                logger.exception("銘柄削除エラー stock_id=%s", stock.get("id"))


def export_csv(stocks: list[dict[str, Any]]) -> bytes:
    """Export stocks as UTF-8 BOM CSV bytes."""
    df = pd.DataFrame([{col: stock.get(col, "") for col in CSV_COLUMNS} for stock in stocks])
    return df.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig")


def parse_import_csv(uploaded_file: Any) -> tuple[pd.DataFrame, list[str]]:
    """Read uploaded CSV and return preview plus file-level errors."""
    try:
        content = uploaded_file.getvalue().decode("utf-8-sig")
        rows = list(csv.DictReader(io.StringIO(content)))
        df = pd.DataFrame(rows)
        missing = [col for col in CSV_COLUMNS if col not in df.columns]
        if missing:
            return df, [f"CSV列が不足しています: {', '.join(missing)}"]
        return df[CSV_COLUMNS], []
    except Exception as exc:
        logger.exception("CSV読み込みエラー")
        return pd.DataFrame(), [f"CSVを読み込めませんでした: {exc}"]


def import_csv_rows(df: pd.DataFrame, update_existing: bool) -> dict[str, Any]:
    """Import CSV rows without stopping on invalid rows."""
    result = {"inserted": 0, "updated": 0, "skipped": 0, "failed": 0, "errors": []}
    for index, row in df.iterrows():
        line_no = int(index) + 2
        try:
            payload = validate_stock_payload(
                {
                    **row.to_dict(),
                    "is_holding": parse_bool(row.get("is_holding")),
                }
            )
            status = upsert_stock(payload, update_existing)
            result[status] += 1
        except Exception as exc:
            result["failed"] += 1
            result["errors"].append(f"{line_no}行目: {exc}")
            logger.exception("CSVインポート行エラー line=%s", line_no)
    return result
