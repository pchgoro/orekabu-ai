"""Streamlit UI for safe earnings candidate retrieval and review."""

from __future__ import annotations

import logging
from datetime import date
from typing import Any

import pandas as pd
import streamlit as st

from services.database import get_stocks, load_settings, save_settings
from services.earnings import japan_today
from services.earnings_candidates import (
    approve_candidate, build_fetch_targets, import_candidate_csv, list_candidates,
    list_fetch_results, list_fetch_runs, parse_candidate_csv, review_candidate,
    run_candidate_fetch, purge_reviewed_candidates, validate_candidate_csv_preview,
)
from services.earnings_providers.yfinance_provider import YFinanceEarningsProvider
from services.earnings_reconciliation import candidate_diff

logger = logging.getLogger(__name__)

COMPARISON_LABELS = {
    "new": "新規", "same": "変更なし", "date_changed": "日付変更",
    "time_changed": "時刻変更", "quarter_changed": "四半期変更",
    "conflict": "競合", "past_date": "過去日", "invalid": "不正",
    "unknown": "比較不能",
}
REVIEW_LABELS = {"pending": "未確認", "approved": "承認済み", "rejected": "却下", "held": "保留"}
CONFIDENCE_LABELS = {"high": "高", "medium": "中", "low": "低", "unknown": "不明"}
APPROVAL_ACTIONS = {
    "新規決算として登録": "new_event",
    "既存の予定を更新": "update_existing",
    "日付だけ更新": "date_only",
    "発表時間だけ更新": "time_only",
    "四半期だけ更新": "quarter_only",
    "既存データを維持して承認済みにする": "keep_existing",
}


def render_earnings_auto_fetch() -> None:
    """Render fetch, review, history, and settings sub-tabs."""
    st.caption("外部情報は参考候補です。正式な決算データは、確認して承認するまで変更されません。")
    fetch_tab, candidates_tab, history_tab, settings_tab = st.tabs(["取得実行", "取得候補", "取得履歴", "取得設定"])
    settings = load_settings()
    with fetch_tab:
        _render_fetch(settings)
    with candidates_tab:
        _render_candidates(settings)
    with history_tab:
        _render_history(settings)
    with settings_tab:
        _render_settings(settings)


def _render_fetch(settings: dict[str, Any]) -> None:
    auto = settings["earnings_auto_fetch"]
    stocks = get_stocks()
    if not auto["enabled"]:
        st.warning("自動取得機能は設定で無効になっています。")
        return
    modes = ["個別銘柄", "決算日未登録のみ", "全登録銘柄", "保有株のみ", "監視銘柄のみ", "決算日が一定期間内", "最終取得から一定日数経過"]
    mode = st.selectbox("取得対象", modes)
    labels = {f"{stock['ticker']} {stock['company_name']}": stock for stock in stocks}
    selected_id = None
    if mode == "個別銘柄" and labels:
        selected_id = int(labels[st.selectbox("個別銘柄", list(labels))]["id"])
    cols = st.columns(3)
    include_related = cols[0].checkbox("関連銘柄を含む", value=True)
    within_days = cols[1].number_input("決算までの日数", 0, 365, 30)
    stale_days = cols[2].number_input("最終取得からの日数", 1, 365, 7)
    targets = build_fetch_targets(stocks, mode, selected_id, include_related, int(within_days), int(stale_days))
    limited = targets[: int(auto["max_tickers_per_run"])]
    st.write(f"対象: {len(targets)}件（今回の上限: {len(limited)}件）")
    if targets:
        st.caption("、".join(stock["ticker"] for stock in limited))
    if st.button("決算候補を取得", type="primary", disabled=not limited):
        progress_bar = st.progress(0.0)
        status = st.empty()

        def update_progress(current: int, total: int, ticker: str) -> None:
            progress_bar.progress(current / max(1, total))
            status.write(f"取得中: {ticker} ({current}/{total})")

        try:
            result = run_candidate_fetch(limited, YFinanceEarningsProvider(), settings, progress=update_progress)
            counts = result["counts"]
            status.success(
                f"取得完了: 成功{counts['success']} / 候補{counts['candidates']} / "
                f"変更なし{counts['unchanged']} / キャッシュ{counts['cached']} / 失敗{counts['failed']}"
            )
            for error in result["errors"]:
                st.warning(error)
        except Exception as exc:
            st.error(f"候補取得に失敗しました: {exc}")
            logger.exception("決算候補取得UIエラー")


def _render_candidates(settings: dict[str, Any]) -> None:
    rows = list_candidates()
    cols = st.columns(4)
    pending_only = cols[0].checkbox("未確認のみ", value=True)
    comparisons = cols[1].multiselect("比較状態", list(COMPARISON_LABELS), format_func=lambda key: COMPARISON_LABELS[key])
    providers = sorted({row["provider_name"] for row in rows})
    provider_filter = cols[2].multiselect("取得元", providers, default=providers)
    confidence_filter = cols[3].multiselect("信頼度", list(CONFIDENCE_LABELS), default=list(CONFIDENCE_LABELS), format_func=lambda key: CONFIDENCE_LABELS[key])
    holding_filter = st.multiselect("銘柄区分", ["保有株", "監視銘柄"], default=["保有株", "監視銘柄"])
    visible = [row for row in rows if (not pending_only or row["review_status"] == "pending")]
    if not settings["earnings_auto_fetch"]["show_past_candidates"]:
        visible = [row for row in visible if row["comparison_status"] != "past_date"]
    if comparisons:
        visible = [row for row in visible if row["comparison_status"] in comparisons]
    visible = [row for row in visible if row["provider_name"] in provider_filter and row["confidence"] in confidence_filter]
    visible = [row for row in visible if ("保有株" if row.get("is_holding") else "監視銘柄") in holding_filter]
    st.dataframe(_candidate_frame(visible), use_container_width=True, hide_index=True, height=420)

    pending = [row for row in visible if row["review_status"] == "pending"]
    if pending:
        labels = {f"#{row['id']} {row['ticker']} {row.get('candidate_date') or '日付なし'} {COMPARISON_LABELS.get(row['comparison_status'], row['comparison_status'])}": row for row in pending}
        candidate = labels[st.selectbox("詳細確認する候補", list(labels))]
        st.dataframe(pd.DataFrame(candidate_diff(candidate)), use_container_width=True, hide_index=True)
        if candidate.get("raw_payload_summary"):
            st.caption(f"取得要約: {candidate['raw_payload_summary']}")
        action_labels = list(APPROVAL_ACTIONS)
        if candidate.get("matched_earnings_event_id"):
            action_labels.remove("既存の予定を更新")
            action_labels.insert(0, "既存の予定を更新")
        action_label = st.selectbox("承認時の反映方法", action_labels)
        fixed = candidate.get("existing_date_status") == "確定"
        confirm_fixed = st.checkbox("既存の確定データを更新することを確認しました", disabled=not fixed)
        note = st.text_input("確認メモ", key=f"candidate_note_{candidate['id']}")
        buttons = st.columns(3)
        if buttons[0].button("承認", key=f"approve_{candidate['id']}"):
            try:
                approve_candidate(int(candidate["id"]), APPROVAL_ACTIONS[action_label], confirm_fixed, note)
                st.success("候補を承認しました。")
                st.rerun()
            except Exception as exc:
                st.error(str(exc)); logger.exception("候補承認UIエラー candidate_id=%s", candidate["id"])
        if buttons[1].button("保留", key=f"hold_{candidate['id']}"):
            try:
                review_candidate(int(candidate["id"]), "held", note); st.success("候補を保留しました。"); st.rerun()
            except Exception as exc:
                st.error(str(exc)); logger.exception("候補保留UIエラー candidate_id=%s", candidate["id"])
        if buttons[2].button("却下", key=f"reject_{candidate['id']}"):
            try:
                review_candidate(int(candidate["id"]), "rejected", note); st.success("候補を却下しました。"); st.rerun()
            except Exception as exc:
                st.error(str(exc)); logger.exception("候補却下UIエラー candidate_id=%s", candidate["id"])

    eligible = [row for row in pending if row["comparison_status"] == "new" and row.get("candidate_date") and row["candidate_date"] >= japan_today().isoformat() and not row.get("matched_earnings_event_id")]
    with st.expander("安全な新規候補を一括承認"):
        selected = st.multiselect("候補", [row["id"] for row in eligible], format_func=lambda item: next(f"#{r['id']} {r['ticker']} {r['candidate_date']}" for r in eligible if r["id"] == item))
        if st.button("選択した新規候補を一括承認", disabled=not selected):
            failures = []
            for candidate_id in selected:
                try:
                    approve_candidate(int(candidate_id), "new_event")
                except Exception as exc:
                    failures.append(f"#{candidate_id}: {exc}")
            st.success(f"承認: {len(selected)-len(failures)}件")
            for failure in failures:
                st.error(failure)

    st.divider()
    st.subheader("CSV候補取込")
    st.caption("CSVは正式な決算イベントへ直接登録されません。候補として保存されます。")
    uploaded = st.file_uploader("決算候補CSV", type=["csv"], key="candidate_csv")
    if uploaded:
        preview, errors = parse_candidate_csv(uploaded)
        for error in errors:
            st.error(error)
        if not errors:
            valid_preview, invalid_preview = validate_candidate_csv_preview(preview)
            st.write(f"有効行: {len(valid_preview)}件 / 不正行: {len(invalid_preview)}件")
            if not valid_preview.empty:
                st.dataframe(valid_preview, use_container_width=True, hide_index=True)
            if not invalid_preview.empty:
                st.error("不正行はインポート対象外です。")
                st.dataframe(invalid_preview, use_container_width=True, hide_index=True)
            if st.button("候補CSVをインポート", disabled=valid_preview.empty):
                result = import_candidate_csv(valid_preview, settings)
                st.write(f"成功: {result['created']} / 重複: {result['duplicate']} / 警告: {result['warnings']} / 失敗: {result['failed']}")
                for error in result["errors"]:
                    st.error(error)


def _render_history(settings: dict[str, Any]) -> None:
    runs = list_fetch_runs()
    st.dataframe(pd.DataFrame([{
        "実行日時": row.get("started_at") or "データなし", "取得元": row.get("provider_name") or "データなし",
        "対象件数": row.get("target_count", 0), "成功": row.get("success_count", 0), "候補作成": row.get("candidate_count", 0),
        "変更なし": row.get("unchanged_count", 0), "失敗": row.get("failed_count", 0), "実行状態": row.get("status") or "データなし",
        "エラー概要": row.get("error_summary") or "",
    } for row in runs]), use_container_width=True, hide_index=True)
    if runs:
        labels = {f"#{row['id']} {row['started_at']} {row['provider_name']}": row for row in runs}
        run = labels[st.selectbox("実行詳細", list(labels))]
        results = list_fetch_results(int(run["id"]))
        st.dataframe(pd.DataFrame(results).fillna("データなし"), use_container_width=True, hide_index=True)
        failed_tickers = [row["ticker"] for row in results if row["status"] == "failed"]
        if failed_tickers:
            st.info("失敗銘柄: " + "、".join(failed_tickers))
            if st.button("失敗銘柄だけ再取得"):
                stocks = [stock for stock in get_stocks() if stock["ticker"] in failed_tickers]
                try:
                    result = run_candidate_fetch(stocks, YFinanceEarningsProvider(), settings, force_fetch=True)
                    st.success(f"再取得を実行しました。run_id={result['run_id']}")
                    st.rerun()
                except Exception as exc:
                    st.error(str(exc)); logger.exception("失敗銘柄再取得UIエラー")


def _render_settings(settings: dict[str, Any]) -> None:
    auto = settings["earnings_auto_fetch"].copy()
    with st.form("earnings_auto_settings"):
        cols = st.columns(3)
        auto["enabled"] = cols[0].checkbox("自動取得機能を有効にする", value=bool(auto["enabled"]))
        auto["provider"] = cols[1].selectbox("使用プロバイダー", ["yfinance"])
        auto["max_tickers_per_run"] = cols[2].number_input("一回の最大取得銘柄数", 1, 100, int(auto["max_tickers_per_run"]))
        cols = st.columns(3)
        auto["request_interval_seconds"] = cols[0].number_input("取得間隔（秒）", 1.0, 60.0, float(auto["request_interval_seconds"]), 0.5)
        auto["cache_hours"] = cols[1].number_input("キャッシュ時間（時間）", 1, 168, int(auto["cache_hours"]))
        auto["candidate_retention_days"] = cols[2].number_input("候補保存期間（日）", 1, 3650, int(auto["candidate_retention_days"]))
        cols = st.columns(2)
        auto["show_past_candidates"] = cols[0].checkbox("過去日候補を表示する", value=bool(auto["show_past_candidates"]))
        auto["save_same_candidates"] = cols[1].checkbox("同一候補を保存する", value=bool(auto["save_same_candidates"]))
        cols = st.columns(2)
        auto["date_change_min_days"] = cols[0].number_input("決算日変更の最小差分日数", 1, 365, int(auto["date_change_min_days"]))
        auto["include_confirmed_events"] = cols[1].checkbox("確定データを更新候補に含める", value=bool(auto["include_confirmed_events"]))
        submitted = st.form_submit_button("取得設定を保存")
    if submitted:
        settings["earnings_auto_fetch"] = auto
        try:
            save_settings(settings)
            st.success("取得設定を保存しました。")
            st.rerun()
        except Exception:
            st.error("設定を保存できませんでした。logs/app.logを確認してください。")
            logger.exception("決算自動取得設定保存エラー")
    if st.button("保存期間を過ぎた確認済み候補を整理"):
        try:
            deleted = purge_reviewed_candidates(int(auto["candidate_retention_days"]))
            st.success(f"確認済み候補を{deleted}件整理しました。未確認候補と正式データは保持されています。")
        except Exception:
            st.error("候補を整理できませんでした。logs/app.logを確認してください。")
            logger.exception("確認済み候補整理UIエラー")


def _candidate_frame(rows: list[dict[str, Any]]) -> pd.DataFrame:
    return pd.DataFrame([{
        "銘柄コード": row.get("ticker") or "データなし", "会社名": row.get("company_name") or "データなし",
        "取得候補日": row.get("candidate_date") or "日付なし", "既存決算日": row.get("existing_date") or "未登録",
        "差分": COMPARISON_LABELS.get(row.get("comparison_status"), "不明"), "四半期": row.get("fiscal_quarter") or "未設定",
        "発表時間": row.get("announcement_time") or "未定", "取得元": row.get("provider_name") or "データなし",
        "取得日時": row.get("retrieved_at") or "データなし", "信頼度": CONFIDENCE_LABELS.get(row.get("confidence"), "不明"),
        "比較状態": COMPARISON_LABELS.get(row.get("comparison_status"), "不明"), "確認状態": REVIEW_LABELS.get(row.get("review_status"), "不明"),
        "注意": row.get("review_note") or "",
    } for row in rows])
