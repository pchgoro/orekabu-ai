"""Reusable daily briefing and mobile-first card renderers."""

from __future__ import annotations

from typing import Any

import streamlit as st

from components.navigation import company_profile_button
from components.ui import (
    empty_state,
    priority_level,
    render_market_metric,
    render_market_value,
    render_priority_badge,
    render_status_badge,
)
from utils.formatters import fmt_number, fmt_price, fmt_signed_price

PAGE_TARGETS = {
    "app": "app.py",
    "決算": "pages/5_決算.py",
    "ニュース": "pages/7_ニュース.py",
    "買い検討ライン": "pages/3_買い検討ライン.py",
    "保有株": "pages/1_保有株.py",
    "監視銘柄": "pages/2_監視銘柄.py",
    "適時開示": "pages/8_適時開示.py",
    "企業カルテ": "pages/9_企業カルテ.py",
    "戦略・カテゴリ": "pages/10_戦略・カテゴリ.py",
    "設定": "pages/6_設定.py",
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
        empty_state("優先して確認する項目はありません。")
        return
    for task in tasks:
        with st.container(border=True):
            cols = st.columns([1.4, 4, 1.5])
            with cols[0]:
                render_priority_badge(priority_level(task["priority"]))
            cols[1].write(f"**{task['label']}**")
            cols[1].caption(task["detail"])
            _task_link(task, cols[2], f"daily_task_{task['priority']}_{task.get('ticker') or task['detail']}")


def render_dashboard_focus(
    tasks: list[dict[str, Any]],
    briefing: list[dict[str, Any]],
    news_rows: list[dict[str, Any]],
    disclosure_rows: list[dict[str, Any]],
) -> None:
    """Render the fixed three-block morning overview."""
    columns = st.columns(3)
    with columns[0]:
        st.subheader("今日やること")
        if tasks:
            for task in tasks[:3]:
                with st.container(border=True):
                    render_priority_badge(priority_level(task["priority"]))
                    st.write(f"**{task['label']}**")
                    st.caption(task["detail"])
                    if task.get("reason_count", 1) > 1:
                        st.caption("確認理由: " + " / ".join(reason["label"] for reason in task["reasons"]))
                    _task_link(
                        task,
                        st,
                        f"dashboard_task_{task['priority']}_{task.get('ticker') or task['detail']}",
                    )
        else:
            empty_state("優先タスクはありません。")

    with columns[1]:
        st.subheader("重要イベント")
        events = [
            item for item in briefing
            if item["count"] and item["state"] in {
                "danger", "warning", "positive", "negative"
            }
        ][:4]
        if events:
            for item in events:
                with st.container(border=True):
                    render_status_badge(_event_badge_label(item["state"]), item["state"])
                    st.write(f"**{item['label']}**: {item['count']}件")
                    if item["page"] != "app":
                        st.page_link(PAGE_TARGETS[item["page"]], label="詳細を見る")
        else:
            empty_state("期限直前・注意イベントはありません。")

    with columns[2]:
        st.subheader("最新材料")
        materials = [
            {
                "title": row.get("title") or "タイトルなし",
                "detail": row.get("published_at") or row.get("retrieved_at") or "日時不明",
                "page": "ニュース",
                "important": row.get("importance") == "高",
            }
            for row in news_rows[:2]
        ]
        materials.extend(
            {
                "title": row.get("title") or "タイトルなし",
                "detail": row.get("disclosed_at") or "日時不明",
                "page": "適時開示",
                "important": row.get("importance") == "高",
            }
            for row in disclosure_rows[:2]
        )
        if materials:
            for material in materials[:4]:
                with st.container(border=True):
                    render_status_badge(
                        "今日見る" if material["important"] else "あとで見る",
                        "warning" if material["important"] else "info",
                    )
                    st.write(f"**{material['title']}**")
                    st.caption(material["detail"])
                    st.page_link(PAGE_TARGETS[material["page"]], label="開く")
        else:
            empty_state("新しいニュース・開示はありません。")


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
            ore_score = row.get("ore_score") or {}
            if ore_score:
                st.caption(
                    f"オレ株スコア: {ore_score.get('score', 0)}点 / "
                    f"{ore_score.get('classification') or '通常'}"
                )
            render_market_metric("前日比", fmt_signed_price(row.get("change")), row.get("change"))
            st.write(f"決算: {row.get('next_earnings_date_display') or '未登録'} / {row.get('earnings_status') or '未登録'}")
            if holding:
                st.write(f"保有株数: {row.get('shares') or 0}")
                render_market_value("評価損益", fmt_signed_price(row.get("profit")), row.get("profit"))
                evaluation = row.get("playbook_evaluation") or {}
                render_status_badge(
                    evaluation.get("status_label") or "未設定",
                    evaluation.get("tone") or "muted",
                )
                st.write(
                    "利確まで残り: "
                    f"{_compact_distance(evaluation.get('target_distance'))}"
                )
                st.write(
                    "損切りまで残り: "
                    f"{_compact_distance(evaluation.get('stop_distance'))}"
                )
                tags = " / ".join(
                    str(tag.get("name"))
                    for tag in row.get("strategy_tags") or []
                )
                strategy = row.get("strategy_lines") or {}
                st.write(f"戦略タグ: {tags or '未設定'}")
                render_status_badge(
                    row.get("strategy_status") or "未設定",
                    strategy.get("tone") or "muted",
                )
                st.write(
                    "戦略ライン: "
                    f"損切 {fmt_price(strategy.get('stop_loss_price'))} / "
                    f"利確 {fmt_price(strategy.get('take_profit_price'))} / "
                    f"買い増し {fmt_price(strategy.get('add_position_price'))}"
                )
            else:
                st.write(f"分類: {row.get('category') or 'その他'} / RSI: {fmt_number(row.get('RSI14'))}")
            st.write(f"メモ: {row.get('memo') or 'なし'}")
            ticker = str(row.get("ticker") or "")
            if ticker:
                company_profile_button(
                    ticker,
                    "企業カルテを開く",
                    key=f"stock_card_profile_{holding}_{ticker}_{row.get('id', '')}",
                )


def render_earnings_cards(rows: list[dict[str, Any]]) -> None:
    """Render earnings essentials as narrow-screen cards."""
    if not rows:
        st.info("表示する決算予定はありません。")
        return
    for row in rows:
        with st.expander(_earnings_title(row), expanded=False):
            days = row.get("days_until")
            render_priority_badge(
                "urgent" if isinstance(days, int) and days <= 3 else
                "today" if isinstance(days, int) and days <= 7 else "later"
            )
            st.write(f"決算日: {row.get('earnings_date_display') or '日付未確認'}")
            st.write(f"状態: {row.get('earnings_status') or '日付未確認'} / {row.get('days_label') or '日付未確認'}")
            st.write(f"四半期: {row.get('fiscal_quarter') or '未設定'} / 発表時間: {row.get('announcement_time_display') or '未定'}")
            st.write(f"メモ: {row.get('memo_display') or 'なし'}")


def _earnings_title(row: dict[str, Any]) -> str:
    return " ".join(part for part in [str(row.get("ticker") or ""), str(row.get("company_name") or "")] if part).strip() or "決算予定"


def _task_link(task: dict[str, Any], target: Any, key: str) -> None:
    """Open a company-specific rule task or a normal page destination."""
    if task.get("page") == "企業カルテ" and task.get("ticker"):
        company_profile_button(str(task["ticker"]), "確認する", key=key)
    else:
        target.page_link(PAGE_TARGETS[task["page"]], label="確認する")


def _event_badge_label(state: str) -> str:
    return {
        "positive": "利確ルール",
        "negative": "損切りルール",
        "danger": "今すぐ見る",
    }.get(state, "今日見る")


def _compact_distance(value: Any) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "未設定"
    if number > 0:
        return f"{number:,.0f}円"
    return "到達"
