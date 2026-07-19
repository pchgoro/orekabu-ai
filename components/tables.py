"""Reusable table rendering helpers."""

from __future__ import annotations

from typing import Any

import pandas as pd
import streamlit as st

from utils.formatters import fmt_number, fmt_percent, fmt_price, fmt_signed_percent, fmt_signed_price


def score_reasons_text(row: dict[str, Any]) -> str:
    """Join score reasons for display."""
    return "\n".join(f"・{reason}" for reason in row.get("score_reasons", []))


def dashboard_dataframe(rows: list[dict[str, Any]]) -> pd.DataFrame:
    """Create dashboard dataframe."""
    data = []
    for index, row in enumerate(sorted(rows, key=lambda item: item.get("score", 0), reverse=True), start=1):
        data.append(
            {
                "順位": index,
                "銘柄コード": row.get("ticker"),
                "会社名": row.get("company_name"),
                "現在値": fmt_price(row.get("current_price")),
                "前日比": fmt_signed_price(row.get("change")),
                "前日比率": fmt_signed_percent(row.get("change_pct")),
                "RSI": fmt_number(row.get("RSI14")),
                "25日線乖離率": fmt_percent(row.get("DEV_MA25")),
                "75日線乖離率": fmt_percent(row.get("DEV_MA75")),
                "出来高倍率": fmt_number(row.get("VOLUME_RATIO")),
                "直近高値からの下落率": fmt_percent(row.get("DROP_FROM_HIGH_60")),
                "注目スコア": row.get("score"),
                "判定": row.get("judge"),
                "スコア理由": score_reasons_text(row),
            }
        )
    return pd.DataFrame(data)


def holdings_dataframe(rows: list[dict[str, Any]]) -> pd.DataFrame:
    """Create holdings dataframe without exposing raw missing values."""
    data = []
    for row in rows:
        data.append(
            {
                "銘柄コード": row.get("ticker"),
                "会社名": row.get("company_name"),
                "保有株数": row.get("shares"),
                "平均取得単価": fmt_price(row.get("average_price")),
                "現在値": fmt_price(row.get("current_price")),
                "前日比": fmt_signed_price(row.get("change")),
                "評価額": fmt_price(row.get("market_value")),
                "評価損益": fmt_signed_price(row.get("profit")),
                "損益率": fmt_signed_percent(row.get("profit_pct")),
                "ルール": row.get("playbook_status") or "未設定",
                "利確まで残り": _rule_distance(row.get("playbook_target_distance")),
                "損切りまで残り": _rule_distance(row.get("playbook_stop_distance")),
                "戦略タグ": " / ".join(
                    str(tag.get("name"))
                    for tag in row.get("strategy_tags") or []
                ) or "未設定",
                "戦略状態": row.get("strategy_status") or "未設定",
                "戦略損切": fmt_price(
                    (row.get("strategy_lines") or {}).get("stop_loss_price")
                ),
                "戦略利確": fmt_price(
                    (row.get("strategy_lines") or {}).get("take_profit_price")
                ),
                "戦略買い増し": fmt_price(
                    (row.get("strategy_lines") or {}).get("add_position_price")
                ),
                "戦略ルール由来": row.get("strategy_source") or "未設定",
                "RSI": fmt_number(row.get("RSI14")),
                "注目スコア": row.get("score"),
                "買い検討価格": fmt_price(row.get("buy_watch_price")),
                "次回決算日": row.get("next_earnings_date_display", "未登録"),
                "決算まで": row.get("earnings_days_label", "未登録"),
                "決算状態": row.get("earnings_status", "未登録"),
                "四半期": row.get("earnings_quarter", "未登録"),
                "日付状態": row.get("earnings_date_status", "未登録"),
                "メモ": row.get("memo") or "",
            }
        )
    return pd.DataFrame(data)


def _rule_distance(value: Any) -> str:
    """Format a compact playbook distance for holdings tables."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "未設定"
    return f"{number:,.0f}円" if number > 0 else "到達"


def watchlist_dataframe(rows: list[dict[str, Any]]) -> pd.DataFrame:
    """Create watchlist dataframe without exposing raw missing values."""
    data = []
    for row in rows:
        data.append(
            {
                "銘柄コード": row.get("ticker"),
                "会社名": row.get("company_name"),
                "分類": row.get("category"),
                "現在値": fmt_price(row.get("current_price")),
                "前日比": fmt_signed_price(row.get("change")),
                "RSI": fmt_number(row.get("RSI14")),
                "MACD": fmt_number(row.get("MACD")),
                "MACDシグナル": fmt_number(row.get("MACD_SIGNAL")),
                "25日線乖離率": fmt_percent(row.get("DEV_MA25")),
                "75日線乖離率": fmt_percent(row.get("DEV_MA75")),
                "出来高倍率": fmt_number(row.get("VOLUME_RATIO")),
                "直近高値からの下落率": fmt_percent(row.get("DROP_FROM_HIGH_60")),
                "注目スコア": row.get("score"),
                "判定": row.get("judge"),
                "次回決算日": row.get("next_earnings_date_display", "未登録"),
                "決算まで": row.get("earnings_days_label", "未登録"),
                "決算状態": row.get("earnings_status", "未登録"),
                "四半期": row.get("earnings_quarter", "未登録"),
                "日付状態": row.get("earnings_date_status", "未登録"),
                "メモ": row.get("memo") or "",
            }
        )
    return pd.DataFrame(data)


def buy_watch_dataframe(rows: list[dict[str, Any]]) -> pd.DataFrame:
    """Create buy-watch dataframe without internal sort keys."""
    data = []
    for row in rows:
        data.append(
            {
                "銘柄コード": row.get("ticker"),
                "会社名": row.get("company_name"),
                "現在値": fmt_price(row.get("current_price")),
                "買い検討価格": fmt_price(row.get("buy_watch_price")),
                "差額": fmt_signed_price(row.get("buy_watch_diff")),
                "差率": fmt_percent(row.get("buy_watch_diff_pct")),
                "到達状態": row.get("buy_watch_status"),
                "注目スコア": row.get("score"),
                "メモ": row.get("memo") or "",
            }
        )
    return pd.DataFrame(data)


def show_dataframe(rows: list[dict[str, Any]], height: int = 520) -> None:
    """Render rows as a Streamlit dataframe."""
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True, height=height)


def earnings_dataframe(rows: list[dict[str, Any]]) -> pd.DataFrame:
    """Create a display table for earnings events."""
    return pd.DataFrame([{
        "銘柄コード": r.get("ticker") or "データなし", "会社名": r.get("company_name") or "データなし",
        "保有区分": r.get("holding_label") or "データなし", "決算日": r.get("earnings_date_display") or "日付未確認",
        "曜日": r.get("weekday") or "データなし", "残り日数": r.get("days_label") or "日付未確認",
        "状態": r.get("earnings_status") or "日付未確認", "年度": r.get("fiscal_year") or "データなし",
        "接近判定": r.get("near_label") or "データなし",
        "四半期": r.get("fiscal_quarter") or "未設定", "発表時間": r.get("announcement_time_display") or "未定",
        "日付状態": r.get("date_status") or "未確認", "メモ": r.get("memo_display") or "",
    } for r in rows])


def impact_dataframe(rows: list[dict[str, Any]]) -> pd.DataFrame:
    """Create a display table for related-company earnings impacts."""
    return pd.DataFrame([{
        "自分の銘柄": f"{r.get('source_ticker','')} {r.get('source_company_name','')}",
        "関連銘柄": f"{r.get('related_ticker','')} {r.get('related_company_name','')}",
        "関係タイプ": r.get("relation_type") or "その他", "影響度": r.get("impact_level") or "データなし",
        "関連銘柄の決算日": r.get("earnings_date") or "日付未確認", "残り日数": r.get("days_label") or "日付未確認",
        "状態": r.get("earnings_status") or "日付未確認", "四半期": r.get("fiscal_quarter") or "未設定",
        "メモ": r.get("memo") or "",
    } for r in rows])


def news_dataframe(rows: list[dict[str, Any]]) -> pd.DataFrame:
    """Create a missing-value-safe news table."""
    return pd.DataFrame([{
        "公開日時": r.get("published_at") or "日時不明",
        "タイトル": r.get("title") or "データなし",
        "ソース": r.get("source_name") or "データなし",
        "関連銘柄候補": r.get("stock_labels") or "なし",
        "状態": "既読" if r.get("is_read") else "未読",
        "お気に入り": "あり" if r.get("is_favorite") else "なし",
        "重要度": r.get("importance") or "通常",
        "カテゴリ": r.get("category") or "その他",
        "URL": r.get("url") or "なし",
        "メモ": r.get("memo") or "",
    } for r in rows])
