"""Reusable Streamlit controls for strategy tags and trade rules."""

from __future__ import annotations

import logging
from typing import Any

import streamlit as st

from components.ui import render_status_badge
from services.strategy_rules import (
    RULE_TYPES,
    TAG_GROUPS,
    delete_stock_rule,
    list_stock_tags,
    list_tags,
    replace_stock_tags,
    save_stock_rule,
)
from utils.formatters import fmt_price

logger = logging.getLogger(__name__)

RULE_TYPE_LABELS = {
    "none": "設定なし",
    "percent_from_average_price": "平均取得単価からの割合",
    "fixed_price": "固定価格",
    "percent_from_current_price": "現在値からの割合",
}


def render_tag_badges(tags: list[dict[str, Any]]) -> None:
    """Render tags with group names and shared color semantics."""
    if not tags:
        st.caption("タグ未設定")
        return
    for tag in tags:
        render_status_badge(
            f"{tag.get('tag_group')}: {tag.get('name')}",
            str(tag.get("color_key") or "info"),
        )


def render_strategy_summary(row: dict[str, Any]) -> None:
    """Show compact effective rule state and derived prices."""
    resolution = row.get("strategy_rule_resolution") or {}
    lines = row.get("strategy_lines") or {}
    render_status_badge(
        "ルール競合" if resolution.get("conflict") else lines.get("status_label") or "未設定",
        "warning" if resolution.get("conflict") else lines.get("tone") or "muted",
    )
    st.caption(f"由来: {resolution.get('source_label') or '未設定'}")
    cols = st.columns(3)
    cols[0].metric("損切価格", fmt_price(lines.get("stop_loss_price")))
    cols[1].metric("利確価格", fmt_price(lines.get("take_profit_price")))
    cols[2].metric("買い増し価格", fmt_price(lines.get("add_position_price")))


def render_stock_tag_editor(stock: dict[str, Any]) -> None:
    """Edit multiple active tags for one stock."""
    tags = list_tags(include_inactive=False)
    current = {int(row["id"]) for row in list_stock_tags(int(stock["id"]))}
    options = {f"{row['tag_group']} / {row['name']}": int(row["id"]) for row in tags}
    selected_labels = [label for label, tag_id in options.items() if tag_id in current]
    with st.form(f"strategy_tags_stock_{stock['id']}"):
        selected = st.multiselect(
            "戦略・カテゴリタグ",
            list(options),
            default=selected_labels,
        )
        if st.form_submit_button("タグを保存"):
            try:
                replace_stock_tags(
                    int(stock["id"]), [options[label] for label in selected]
                )
                st.success("タグを保存しました。")
                st.rerun()
            except Exception as exc:
                logger.exception("銘柄タグ保存失敗 stock_id=%s", stock["id"])
                st.error(str(exc))


def render_individual_rule_editor(
    stock: dict[str, Any], current_rule: dict[str, Any] | None,
) -> None:
    """Edit or remove one stock-specific override."""
    st.caption("個別上書きはタグルールより優先します。既存の投資ルールは変更しません。")
    with st.form(f"individual_strategy_rule_{stock['id']}"):
        values: dict[str, Any] = {}
        for role, label in (
            ("stop_loss", "損切"),
            ("take_profit", "利確"),
            ("add_position", "買い増し"),
        ):
            cols = st.columns([2, 1])
            current_type = str((current_rule or {}).get(f"{role}_type") or "none")
            selected_type = cols[0].selectbox(
                f"{label}ルール",
                RULE_TYPES,
                index=RULE_TYPES.index(current_type) if current_type in RULE_TYPES else 3,
                format_func=lambda value: RULE_TYPE_LABELS[value],
                key=f"{role}_type_{stock['id']}",
            )
            values[f"{role}_type"] = selected_type
            values[f"{role}_value"] = cols[1].number_input(
                f"{label}値",
                min_value=0.0,
                step=0.5,
                value=float((current_rule or {}).get(f"{role}_value") or 0),
                disabled=selected_type == "none",
                key=f"{role}_value_{stock['id']}",
            )
        values["earnings_policy"] = st.text_input(
            "決算方針", str((current_rule or {}).get("earnings_policy") or "")
        )
        values["memo"] = st.text_area(
            "個別ルールメモ", str((current_rule or {}).get("memo") or "")
        )
        if st.form_submit_button("個別ルールを保存"):
            try:
                save_stock_rule(int(stock["id"]), values)
                st.success("個別ルールを保存しました。")
                st.rerun()
            except Exception as exc:
                logger.exception("個別戦略ルール保存失敗 stock_id=%s", stock["id"])
                st.error(str(exc))
    if current_rule:
        confirmed = st.checkbox(
            "個別ルールを削除してタグ候補へ戻す",
            key=f"delete_individual_rule_confirm_{stock['id']}",
        )
        if st.button(
            "個別ルールを削除",
            disabled=not confirmed,
            key=f"delete_individual_rule_{stock['id']}",
        ):
            try:
                delete_stock_rule(int(stock["id"]))
                st.success("個別ルールを削除しました。")
                st.rerun()
            except Exception as exc:
                logger.exception("個別戦略ルール削除失敗 stock_id=%s", stock["id"])
                st.error(str(exc))
