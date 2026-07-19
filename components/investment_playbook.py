"""Investment playbook summary and edit form for the company profile."""

from __future__ import annotations

import logging
from typing import Any

import streamlit as st

from components.ui import render_status_badge
from services.investment_playbooks import (
    EXIT_CONDITION_OPTIONS,
    HOLDING_PERIOD_OPTIONS,
    THEME_OPTIONS,
    delete_playbook,
    save_playbook,
)
from utils.formatters import fmt_percent, fmt_price

LOGGER = logging.getLogger(__name__)


def render_playbook_summary(
    playbook: dict[str, Any] | None,
    evaluation: dict[str, Any],
) -> None:
    """Show configured-rule state without presenting a trade recommendation."""
    st.caption("売買推奨ではなく、事前に設定した投資ルールの現在状態です。")
    render_status_badge(
        evaluation.get("status_label") or "未設定",
        evaluation.get("tone") or "muted",
    )
    columns = st.columns(3)
    columns[0].metric(
        "現在値", fmt_price(evaluation.get("current_price"))
    )
    next_target = evaluation.get("next_target_price")
    columns[1].metric(
        _target_label(evaluation),
        fmt_price(next_target),
    )
    columns[1].caption(
        _distance_text(
            evaluation.get("target_distance"),
            evaluation.get("target_distance_pct"),
            positive_label="あと",
            reached_label="到達済み",
        )
    )
    columns[2].metric(
        "損切り価格", fmt_price(evaluation.get("stop_loss_price"))
    )
    columns[2].caption(
        _distance_text(
            evaluation.get("stop_distance"),
            evaluation.get("stop_distance_pct"),
            positive_label="余裕",
            reached_label="到達済み",
        )
    )
    if playbook and playbook.get("trailing_stop_percent"):
        st.caption(
            "トレーリングストップ: "
            f"{fmt_percent(playbook['trailing_stop_percent'])} "
            "（高値基準値を保存していないため自動判定対象外）"
        )


def render_playbook_form(
    stock_id: int,
    playbook: dict[str, Any] | None,
    *,
    mobile: bool,
) -> None:
    """Render the detailed playbook form used only in the company profile."""
    current = playbook or {}
    current_themes = list(current.get("investment_themes") or [])
    known_themes = [theme for theme in current_themes if theme in THEME_OPTIONS]
    custom_themes = [
        theme for theme in current_themes if theme not in THEME_OPTIONS
    ]
    exits = current.get("exit_conditions") or {}
    holding_value = str(current.get("holding_period") or "")
    holding_mode = (
        holding_value if holding_value in HOLDING_PERIOD_OPTIONS[:-1] else "自由入力"
    )

    with st.form(f"investment_playbook_{stock_id}"):
        buy_reason = st.text_area(
            "買った理由",
            current.get("buy_reason") or "",
            height=120,
            placeholder="購入時に確認した事実、期待、前提を記録します。",
        )
        selected_themes = st.multiselect(
            "投資テーマ",
            THEME_OPTIONS,
            default=known_themes,
        )
        custom_theme_text = st.text_input(
            "その他のテーマ",
            ", ".join(custom_themes),
            placeholder="カンマ区切りで入力",
        )

        st.markdown("#### 利確")
        profit_columns = (
            [st.container(), st.container(), st.container()]
            if mobile
            else st.columns(3)
        )
        with profit_columns[0]:
            target_price_1 = st.number_input(
                "利確① 価格",
                min_value=0.0,
                value=_number(current.get("target_price_1")),
                step=1.0,
            )
            target_price_1_sell_percent = st.number_input(
                "利確① 売却割合（%）",
                min_value=0.0,
                max_value=100.0,
                value=_number(current.get("target_price_1_sell_percent")),
                step=1.0,
            )
        with profit_columns[1]:
            target_price_2 = st.number_input(
                "利確② 価格",
                min_value=0.0,
                value=_number(current.get("target_price_2")),
                step=1.0,
            )
            target_price_2_sell_percent = st.number_input(
                "利確② 売却割合（%）",
                min_value=0.0,
                max_value=100.0,
                value=_number(current.get("target_price_2_sell_percent")),
                step=1.0,
            )
        with profit_columns[2]:
            final_target_price = st.number_input(
                "最終目標 価格",
                min_value=0.0,
                value=_number(current.get("final_target_price")),
                step=1.0,
            )

        st.markdown("#### 損切り")
        stop_columns = (
            [st.container(), st.container()] if mobile else st.columns(2)
        )
        stop_loss_price = stop_columns[0].number_input(
            "損切り価格",
            min_value=0.0,
            value=_number(current.get("stop_loss_price")),
            step=1.0,
        )
        trailing_stop_percent = stop_columns[1].number_input(
            "トレーリングストップ（%）",
            min_value=0.0,
            max_value=100.0,
            value=_number(current.get("trailing_stop_percent")),
            step=0.5,
        )

        st.markdown("#### 保有予定")
        period_mode = st.radio(
            "期間区分",
            HOLDING_PERIOD_OPTIONS,
            index=HOLDING_PERIOD_OPTIONS.index(holding_mode),
            horizontal=not mobile,
        )
        custom_period = st.text_input(
            "保有予定の自由入力",
            holding_value if holding_mode == "自由入力" else "",
            disabled=period_mode != "自由入力",
        )

        st.markdown("#### 売却条件")
        selected_exits = st.multiselect(
            "条件",
            EXIT_CONDITION_OPTIONS,
            default=[
                item
                for item in exits.get("selected", [])
                if item in EXIT_CONDITION_OPTIONS
            ],
        )
        custom_exit = st.text_area(
            "売却条件の自由記述",
            exits.get("custom") or "",
            height=100,
        )
        risk_notes = st.text_area(
            "メモ",
            current.get("risk_notes") or "",
            height=120,
            placeholder="前提が崩れる要因、決算で確認する点、保有中の注意点を記録します。",
        )

        if st.form_submit_button("投資ルールを保存"):
            themes = list(selected_themes)
            themes.extend(_split_custom(custom_theme_text))
            try:
                save_playbook(
                    stock_id,
                    {
                        "buy_reason": buy_reason,
                        "investment_themes": themes,
                        "target_price_1": target_price_1,
                        "target_price_1_sell_percent": target_price_1_sell_percent,
                        "target_price_2": target_price_2,
                        "target_price_2_sell_percent": target_price_2_sell_percent,
                        "final_target_price": final_target_price,
                        "stop_loss_price": stop_loss_price,
                        "trailing_stop_percent": trailing_stop_percent,
                        "holding_period": (
                            custom_period
                            if period_mode == "自由入力"
                            else period_mode
                        ),
                        "exit_conditions": {
                            "selected": selected_exits,
                            "custom": custom_exit,
                        },
                        "risk_notes": risk_notes,
                    },
                )
                st.success("投資ルールを保存しました。")
                st.rerun()
            except Exception as exc:
                LOGGER.exception(
                    "投資ルールの保存に失敗しました。 stock_id=%s", stock_id
                )
                st.error(str(exc))

    if playbook:
        with st.expander("投資ルールを削除"):
            confirmed = st.checkbox(
                "この銘柄の投資ルールだけを削除する",
                key=f"delete_playbook_confirm_{stock_id}",
            )
            if st.button(
                "投資ルールを削除",
                disabled=not confirmed,
                key=f"delete_playbook_{stock_id}",
            ):
                try:
                    delete_playbook(stock_id)
                    st.success("投資ルールを削除しました。")
                    st.rerun()
                except Exception as exc:
                    LOGGER.exception(
                        "投資ルールの削除に失敗しました。 stock_id=%s", stock_id
                    )
                    st.error(str(exc))


def _number(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _split_custom(value: str) -> list[str]:
    return [
        item.strip()
        for item in str(value or "").replace("、", ",").split(",")
        if item.strip()
    ]


def _target_label(evaluation: dict[str, Any]) -> str:
    return {
        "target_price_1": "利確①",
        "target_price_2": "利確②",
        "final_target_price": "最終目標",
    }.get(evaluation.get("next_target_label"), "次の利確")


def _distance_text(
    distance: Any,
    percent: Any,
    *,
    positive_label: str,
    reached_label: str,
) -> str:
    try:
        numeric = float(distance)
        pct = abs(float(percent))
    except (TypeError, ValueError):
        return "未設定"
    if numeric > 0:
        return f"{positive_label} {numeric:,.0f}円（{pct:.2f}%）"
    return f"{reached_label}（{abs(numeric):,.0f}円）"
