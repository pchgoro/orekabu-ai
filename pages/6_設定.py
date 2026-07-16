"""Settings, CSV import/export, and stock maintenance page."""

from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd
import streamlit as st

from components.forms import create_stock_section, export_csv, import_csv_rows, parse_import_csv
from scripts.run_daily_update import main as run_daily_update
from services.automation import automation_summary, list_run_steps, list_runs
from services.database import get_stocks, init_db, load_settings, save_settings
from services.edinet import api_key_configured
from services.marketspeed_import import (
    build_marketspeed_preview,
    import_marketspeed_preview,
    parse_marketspeed_csv,
)
from services.settings import default_settings
from services.stock_profiles import list_profile_candidates, review_profile_candidate
from utils.logging_config import setup_logging

logger = logging.getLogger(__name__)
ROOT = Path(__file__).resolve().parents[1]

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

    st.subheader("EDINET取得設定")
    cols = st.columns(4)
    edinet_daily_lookback_days = cols[0].number_input(
        "日次取得日数",
        1,
        30,
        int(settings["edinet_daily_lookback_days"]),
    )
    edinet_monthly_lookback_days = cols[1].number_input(
        "月次確認日数",
        1,
        365,
        int(settings["edinet_monthly_lookback_days"]),
    )
    edinet_initial_backfill_days = cols[2].number_input(
        "初回バックフィル日数",
        1,
        365,
        int(settings["edinet_initial_backfill_days"]),
    )
    edinet_fetch_limit = cols[3].number_input(
        "最大保存件数",
        1,
        500,
        int(settings["edinet_fetch_limit"]),
    )

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
                    "edinet_daily_lookback_days": edinet_daily_lookback_days,
                    "edinet_monthly_lookback_days": edinet_monthly_lookback_days,
                    "edinet_initial_backfill_days": edinet_initial_backfill_days,
                    "edinet_fetch_limit": edinet_fetch_limit,
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

st.subheader("無料取得自動化")
st.caption(
    "RSS、yfinance、EDINET公式API v2を使うローカル処理です。"
    "候補データが確定データを自動上書きすることはありません。"
)
try:
    automation = automation_summary()
    automation_cols = st.columns(3)
    automation_cols[0].metric("最終一括更新", automation["last_run_at"] or "未実行")
    automation_cols[1].metric("新着EDINET", automation["new_edinet"])
    automation_cols[2].metric("処理失敗", automation["last_failed"])
    automation_cols = st.columns(2)
    automation_cols[0].metric("未確認決算候補", automation["pending_earnings"])
    automation_cols[1].metric("企業情報候補", automation["pending_profiles"])
    key_ready = api_key_configured(ROOT / ".env")
    st.write(f"EDINET APIキー: {'設定済み' if key_ready else '未設定'}")
    if not key_ready:
        st.info(
            "EDINET APIキーは未設定です。.env.exampleを.envへコピーし、"
            "EDINET_API_KEYを設定してください。キー本体は画面やログへ表示しません。"
        )

    automation_limit = st.number_input(
        "手動一括更新の処理上限",
        min_value=1,
        max_value=100,
        value=20,
        step=1,
    )
    st.caption("EDINETを利用するには、.envへEDINET_API_KEYを設定してください。")
    if st.button("無料データを手動で一括更新", type="primary"):
        with st.spinner("RSS、決算候補、EDINET、企業情報候補を順番に取得しています..."):
            exit_status = run_daily_update(["--limit", str(int(automation_limit))])
        if exit_status == 0:
            st.success("一括更新が完了しました。")
        else:
            st.warning(
                "一部の処理が完了しませんでした。実行履歴とlogs/app.logを確認してください。"
            )
        st.rerun()

    runs = list_runs(20)
    with st.expander("実行履歴", expanded=False):
        if not runs:
            st.info("実行履歴はまだありません。")
        else:
            st.dataframe(pd.DataFrame(runs), use_container_width=True, hide_index=True)
            selected_run_id = st.selectbox(
                "ステップ詳細",
                [int(run["id"]) for run in runs],
                format_func=lambda run_id: f"実行ID {run_id}",
            )
            st.dataframe(
                pd.DataFrame(list_run_steps(selected_run_id)),
                use_container_width=True,
                hide_index=True,
            )

    st.markdown("#### 企業情報候補の確認")
    status_labels = {
        "pending": "未確認",
        "held": "保留",
        "approved": "承認済み",
        "rejected": "却下済み",
    }
    status_filter = st.selectbox(
        "候補状態",
        ["pending", "held", "approved", "rejected", "all"],
        format_func=lambda value: "すべて" if value == "all" else status_labels[value],
    )
    candidates = list_profile_candidates(
        None if status_filter == "all" else status_filter,
        limit=200,
    )
    if not candidates:
        st.info("該当する企業情報候補はありません。")
    else:
        selected_candidate_id = st.selectbox(
            "確認する候補",
            [int(row["id"]) for row in candidates],
            format_func=lambda candidate_id: next(
                f"{row['ticker']} {row['live_company_name']} / "
                f"{status_labels.get(row['review_status'], row['review_status'])}"
                for row in candidates
                if int(row["id"]) == candidate_id
            ),
        )
        candidate = next(
            row for row in candidates if int(row["id"]) == selected_candidate_id
        )
        field_rows = [
            {
                "項目": label,
                "現在値": candidate.get(f"live_{field}") or "未登録",
                "候補値": candidate.get(field) or "候補なし",
            }
            for field, label in (
                ("company_name", "会社名"),
                ("company_alias", "略称"),
                ("market", "市場"),
                ("industry", "業種"),
            )
        ]
        st.dataframe(pd.DataFrame(field_rows), use_container_width=True, hide_index=True)
        st.caption(
            f"取得元: {candidate['provider_name']} / "
            f"取得日時: {candidate['retrieved_at']} / "
            f"状態: {status_labels.get(candidate['review_status'], candidate['review_status'])}"
        )
        if candidate["review_status"] in {"pending", "held"}:
            with st.form(f"profile_review_{selected_candidate_id}"):
                st.write("承認する項目")
                field_cols = st.columns(2)
                selected_fields: list[str] = []
                for index, (field, label) in enumerate(
                    (
                        ("company_name", "会社名"),
                        ("company_alias", "略称"),
                        ("market", "市場"),
                        ("industry", "業種"),
                    )
                ):
                    if field_cols[index % 2].checkbox(
                        label,
                        value=bool(candidate.get(field)),
                        disabled=not bool(candidate.get(field)),
                    ):
                        selected_fields.append(field)
                action_cols = st.columns(4)
                approve_selected = action_cols[0].form_submit_button("選択項目を承認")
                approve_all = action_cols[1].form_submit_button("全項目を承認")
                hold = action_cols[2].form_submit_button("保留")
                reject = action_cols[3].form_submit_button("却下")
                action_requested = approve_selected or approve_all or hold or reject
                if action_requested:
                    try:
                        if approve_selected:
                            review_profile_candidate(
                                selected_candidate_id,
                                "approve",
                                approved_fields=selected_fields,
                            )
                        elif approve_all:
                            review_profile_candidate(
                                selected_candidate_id,
                                "approve",
                                approved_fields=[
                                    field
                                    for field in (
                                        "company_name",
                                        "company_alias",
                                        "market",
                                        "industry",
                                    )
                                    if candidate.get(field)
                                ],
                            )
                        elif hold:
                            review_profile_candidate(selected_candidate_id, "hold")
                        else:
                            review_profile_candidate(selected_candidate_id, "reject")
                        st.success("企業情報候補の状態を更新しました。")
                        st.rerun()
                    except ValueError as exc:
                        st.error(str(exc))
except Exception:
    st.error("自動取得の状態を読み込めませんでした。logs/app.logを確認してください。")
    logger.exception("無料取得自動化UIエラー")

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

st.markdown("### マーケットスピード保有銘柄CSV")
st.caption(
    "楽天証券マーケットスピードの保有銘柄CSV専用です。"
    "現在値、評価損益、PER、PBR、決算日は正式データへ保存しません。"
)
marketspeed_upload = st.file_uploader(
    "マーケットスピードCSVファイル",
    type=["csv"],
    key="marketspeed_portfolio_csv",
)
policy_labels = {
    "update": "既存銘柄を更新",
    "skip": "既存銘柄をスキップ",
    "new_only": "新規のみ追加",
}
marketspeed_policy = st.radio(
    "更新方針",
    list(policy_labels),
    format_func=lambda value: policy_labels[value],
    horizontal=True,
    key="marketspeed_policy",
)
if marketspeed_upload is not None:
    try:
        parsed_market = parse_marketspeed_csv(
            marketspeed_upload.getvalue(),
            marketspeed_upload.name,
        )
        market_preview = build_marketspeed_preview(parsed_market, marketspeed_policy)
        st.caption(f"文字コード: {market_preview['encoding']}")
        summary = market_preview["summary"]
        summary_cols = st.columns(4)
        summary_cols[0].metric("CSV行数", summary["csv_rows"])
        summary_cols[1].metric("銘柄数", summary["stocks"])
        summary_cols[2].metric("新規", summary["new"])
        summary_cols[3].metric("更新", summary["updated"])
        summary_cols = st.columns(4)
        summary_cols[0].metric("同一", summary["same"])
        summary_cols[1].metric("スキップ", summary["skipped"])
        summary_cols[2].metric("重複統合", summary["duplicates"])
        summary_cols[3].metric("エラー", summary["errors"])
        preview_rows = [
            {
                "ticker": row["ticker"],
                "company_name": row["company_name"],
                "口座区分": row["account_summary"],
                "shares": row["shares"],
                "average_price": row["average_price"],
                "現在の会社名": row["current_company_name"],
                "現在の株数": row["current_shares"],
                "現在の平均取得価額": row["current_average_price"],
                "取込後メモ": row["import_memo"],
                "判定": row["decision"],
            }
            for row in market_preview["preview"]
        ]
        st.dataframe(pd.DataFrame(preview_rows), use_container_width=True, hide_index=True)
        if market_preview["errors"]:
            with st.expander("エラー行", expanded=True):
                for error in market_preview["errors"]:
                    st.error(error)
        if market_preview["missing_holdings"]:
            with st.expander("CSVにない保有株候補", expanded=False):
                st.caption("自動で非保有には変更しません。必要な場合だけ手動で確認してください。")
                st.dataframe(
                    pd.DataFrame(
                        [
                            {
                                "ticker": row["ticker"],
                                "company_name": row["company_name"],
                                "shares": row["shares"],
                                "average_price": row["average_price"],
                            }
                            for row in market_preview["missing_holdings"]
                        ]
                    ),
                    use_container_width=True,
                    hide_index=True,
                )
        if st.button("マーケットスピードCSVをインポート", type="primary"):
            result = import_marketspeed_preview(market_preview)
            st.write(
                f"新規: {result['inserted']}件 / 更新: {result['updated']}件 / "
                f"同一: {result['unchanged']}件 / スキップ: {result['skipped']}件 / "
                f"失敗: {result['failed']}件"
            )
            for error in result["errors"]:
                st.error(error)
            if result["failed"] == 0:
                st.success("マーケットスピードCSVのインポートが完了しました。")
            st.rerun()
    except ValueError as exc:
        st.error(str(exc))
    except Exception:
        st.error("マーケットスピードCSVを読み込めませんでした。logs/app.logを確認してください。")
        logger.exception("MarketSpeed CSV UI error")

st.subheader("登録銘柄一覧")
st.dataframe(pd.DataFrame(stocks), use_container_width=True, hide_index=True)
