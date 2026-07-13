"""Settings, CSV import/export, and stock maintenance page."""

from __future__ import annotations

import logging

import pandas as pd
import streamlit as st

from components.forms import create_stock_section, export_csv, import_csv_rows, parse_import_csv
from services.database import get_stocks, init_db, load_settings, save_settings
from services.settings import default_settings
from utils.logging_config import setup_logging

logger = logging.getLogger(__name__)

st.set_page_config(page_title="設定 - オレ株AI", layout="wide")
setup_logging()
init_db()
st.title("設定")

settings = load_settings()
stocks = get_stocks()

create_stock_section()

st.subheader("表示・取得設定")
with st.form("settings_form"):
    st.subheader("毎日の表示設定")
    cols = st.columns(2)
    dashboard_display_mode = cols[0].selectbox("ダッシュボード表示", ["標準", "コンパクト"], index=["標準", "コンパクト"].index(settings["dashboard_display_mode"]))
    news_display_mode = cols[1].selectbox("ニュース表示", ["カード", "表"], index=["カード", "表"].index(settings["news_display_mode"]))
    cols = st.columns(2)
    briefing_limit = cols[0].number_input("ブリーフィング表示件数", 1, 20, int(settings["briefing_limit"]))
    daily_tasks_limit = cols[1].number_input("今日やること表示件数", 1, 10, int(settings["daily_tasks_limit"]))
    mobile_priority_display = st.checkbox("モバイル優先表示", value=bool(settings["mobile_priority_display"]))
    hide_zero_sections = st.checkbox("0件のセクションを隠す", value=bool(settings["hide_zero_sections"]))

    cols = st.columns(3)
    ranking_limit = cols[0].number_input("ランキング表示件数", min_value=1, max_value=100, step=1, value=int(settings["ranking_limit"]))
    stock_cache_minutes = cols[1].number_input("株価キャッシュ時間（分）", min_value=1, max_value=1440, step=1, value=int(settings["stock_cache_minutes"]))
    buy_watch_near_percent = cols[2].number_input("買い検討価格の接近判定率（%）", min_value=0.0, max_value=100.0, step=0.5, value=float(settings["buy_watch_near_percent"]))

    st.subheader("決算表示設定")
    cols = st.columns(3)
    earnings_dashboard_limit = cols[0].number_input("ダッシュボードの決算表示件数", 1, 100, int(settings["earnings_dashboard_limit"]))
    earnings_near_days = cols[1].number_input("決算接近と判定する日数", 1, 365, int(settings["earnings_near_days"]))
    related_earnings_limit = cols[2].number_input("関連銘柄の決算表示件数", 1, 100, int(settings["related_earnings_limit"]))
    cols = st.columns(2)
    past_earnings_days = cols[0].number_input("過去決算の標準表示期間（日）", 0, 3650, int(settings["past_earnings_days"]))
    show_unconfirmed_earnings = cols[1].checkbox("日付未確認銘柄を表示", value=bool(settings["show_unconfirmed_earnings"]))

    st.subheader("注目スコア設定")
    score = settings["score"].copy()
    cols = st.columns(4)
    score["base_score"] = cols[0].number_input("スコア初期点", value=float(score["base_score"]), step=1.0)
    score["rsi_low"] = cols[1].number_input("RSI閾値 低", value=float(score["rsi_low"]), step=1.0)
    score["rsi_mid_low"] = cols[2].number_input("RSI閾値 中低", value=float(score["rsi_mid_low"]), step=1.0)
    score["rsi_mid"] = cols[3].number_input("RSI閾値 中", value=float(score["rsi_mid"]), step=1.0)
    cols = st.columns(4)
    score["rsi_high"] = cols[0].number_input("RSI閾値 高", value=float(score["rsi_high"]), step=1.0)
    score["ma_deviation_threshold"] = cols[1].number_input("移動平均乖離率閾値（%）", value=float(score["ma_deviation_threshold"]), step=0.5)
    score["volume_ratio_threshold"] = cols[2].number_input("出来高倍率閾値", value=float(score["volume_ratio_threshold"]), step=0.1)
    score["volume_ratio_extra_threshold"] = cols[3].number_input("出来高倍率追加閾値", value=float(score["volume_ratio_extra_threshold"]), step=0.1)
    cols = st.columns(2)
    score["drop_threshold_low"] = cols[0].number_input("下落率閾値 低（%）", value=float(score["drop_threshold_low"]), step=1.0)
    score["drop_threshold_high"] = cols[1].number_input("下落率閾値 高（%）", value=float(score["drop_threshold_high"]), step=1.0)

    point_keys = [
        ("rsi_30_or_less", "RSI 30以下"),
        ("rsi_30_40", "RSI 30超-40以下"),
        ("rsi_40_50", "RSI 40超-50以下"),
        ("rsi_70_or_more", "RSI 70以上"),
        ("ma25_deviation_near", "25日線乖離"),
        ("ma75_deviation_near", "75日線乖離"),
        ("volume_ratio_15", "出来高1.5倍"),
        ("volume_ratio_20_extra", "出来高2.0倍追加"),
        ("drop_10_20", "高値から10-20%下落"),
        ("drop_20_or_more", "高値から20%以上下落"),
        ("ma5_above_ma25", "5日線が25日線超"),
        ("golden_cross_extra", "ゴールデンクロス追加"),
        ("price_below_ma25_ma75", "株価が両MAより下"),
        ("price_above_ma25_ma75", "株価が両MAより上"),
    ]
    for start in range(0, len(point_keys), 4):
        cols = st.columns(4)
        for col, (key, label) in zip(cols, point_keys[start : start + 4]):
            score[key] = col.number_input(label, value=float(score[key]), step=1.0)

    submitted = st.form_submit_button("設定を保存")
    if submitted:
        try:
            save_settings(
                {
                    **settings,
                    "dashboard_display_mode": dashboard_display_mode,
                    "news_display_mode": news_display_mode,
                    "mobile_priority_display": mobile_priority_display,
                    "briefing_limit": briefing_limit,
                    "daily_tasks_limit": daily_tasks_limit,
                    "hide_zero_sections": hide_zero_sections,
                    "ranking_limit": ranking_limit,
                    "stock_cache_minutes": stock_cache_minutes,
                    "buy_watch_near_percent": buy_watch_near_percent,
                    "earnings_dashboard_limit": earnings_dashboard_limit,
                    "earnings_near_days": earnings_near_days,
                    "related_earnings_limit": related_earnings_limit,
                    "past_earnings_days": past_earnings_days,
                    "show_unconfirmed_earnings": show_unconfirmed_earnings,
                    "score": score,
                }
            )
            st.success("設定を保存しました。")
            st.rerun()
        except Exception:
            st.error("設定保存中にエラーが発生しました。logs/app.logを確認してください。")
            logger.exception("設定保存エラー")

if st.button("設定を初期値へ戻す"):
    try:
        save_settings(default_settings())
        st.success("設定を初期値へ戻しました。")
        st.rerun()
    except Exception:
        st.error("設定初期化中にエラーが発生しました。logs/app.logを確認してください。")
        logger.exception("設定初期化エラー")

st.subheader("CSVエクスポート")
st.download_button(
    "銘柄一覧CSVをダウンロード",
    data=export_csv(stocks),
    file_name="orekabu_stocks.csv",
    mime="text/csv",
)

st.subheader("CSVインポート")
uploaded = st.file_uploader("CSVファイル", type=["csv"])
if uploaded is not None:
    preview, errors = parse_import_csv(uploaded)
    if errors:
        for error in errors:
            st.error(error)
    else:
        st.dataframe(preview, use_container_width=True, hide_index=True)
        update_existing = st.radio("既存tickerがある場合", ["更新", "スキップ"], horizontal=True) == "更新"
        if st.button("インポート実行"):
            result = import_csv_rows(preview, update_existing)
            st.write(f"成功: {result['inserted']}件 / 更新: {result['updated']}件 / スキップ: {result['skipped']}件 / 失敗: {result['failed']}件")
            for error in result["errors"]:
                st.error(error)
            if not result["errors"]:
                st.success("CSVインポートが完了しました。")

st.subheader("登録銘柄一覧")
st.dataframe(pd.DataFrame(stocks), use_container_width=True, hide_index=True)
