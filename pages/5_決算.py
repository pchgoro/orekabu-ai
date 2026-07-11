"""Manual earnings calendar and directed related-stock management."""

from __future__ import annotations

import calendar
import logging
import sqlite3
from datetime import date, timedelta

import streamlit as st

from components.cards import earnings_metrics
from components.tables import earnings_dataframe, impact_dataframe
from services.database import get_stocks, init_db, load_settings
from services.earnings import (
    add_earnings, delete_earnings, export_earnings_csv, import_earnings_csv,
    earnings_form_date_value, japan_today, list_earnings, parse_earnings_csv, update_earnings,
)
from services.earnings_view_models import earnings_summary, prepare_earnings_rows, sort_earnings_rows
from services.relations import (
    add_relation, delete_relation, export_relations_csv, impact_candidates,
    import_relations_csv, list_relations, parse_relations_csv, update_relation,
)
from utils.constants import EARNINGS_DATE_STATUSES, EARNINGS_QUARTERS, IMPACT_LEVELS, RELATION_TYPES
from utils.logging_config import setup_logging

logger = logging.getLogger(__name__)
st.set_page_config(page_title="決算管理 - オレ株AI", layout="wide")
setup_logging()
init_db()
st.title("決算管理")
st.caption("決算接近は売買推奨ではなく、確認時期を整理するための情報です。決算日は手動登録です。")

stocks = get_stocks()
settings = load_settings()
stock_options = {f"{s['ticker']} {s['company_name']}": s for s in stocks}
events = list_earnings()
prepared = prepare_earnings_rows(events, near_days=int(settings["earnings_near_days"]))
earnings_metrics(earnings_summary(prepared))

calendar_tab, list_tab, form_tab, relations_tab, impacts_tab = st.tabs(["決算カレンダー", "決算一覧", "決算登録", "関連銘柄", "影響予定"])

with calendar_tab:
    today = japan_today()
    if "earnings_month" not in st.session_state:
        st.session_state.earnings_month = today.replace(day=1)
    nav = st.columns([1, 1, 1, 3])
    if nav[0].button("前月"):
        current = st.session_state.earnings_month
        st.session_state.earnings_month = (current - timedelta(days=1)).replace(day=1)
        st.rerun()
    if nav[1].button("当月"):
        st.session_state.earnings_month = today.replace(day=1)
        st.rerun()
    if nav[2].button("翌月"):
        current = st.session_state.earnings_month
        st.session_state.earnings_month = (current.replace(day=28) + timedelta(days=4)).replace(day=1)
        st.rerun()
    selected_month = nav[3].date_input("月選択", value=st.session_state.earnings_month, key="calendar_month_picker").replace(day=1)
    st.session_state.earnings_month = selected_month
    filters = st.columns(4)
    holding_only = filters[0].checkbox("保有株のみ")
    watch_only = filters[1].checkbox("監視銘柄のみ")
    include_related = filters[2].checkbox("関連銘柄を含める", value=True)
    include_planned = filters[3].checkbox("予定を含める", value=True)
    _, last_day = calendar.monthrange(selected_month.year, selected_month.month)
    month_end = selected_month.replace(day=last_day)
    calendar_rows = prepare_earnings_rows(list_earnings(start_date=selected_month, end_date=month_end))
    if holding_only:
        calendar_rows = [r for r in calendar_rows if r.get("is_holding")]
    if watch_only:
        calendar_rows = [r for r in calendar_rows if not r.get("is_holding")]
    if not include_related:
        calendar_rows = [r for r in calendar_rows if r.get("category") != "関連銘柄"]
    if not include_planned:
        calendar_rows = [r for r in calendar_rows if r.get("date_status") == "確定"]
    st.subheader(f"{selected_month.year}年{selected_month.month}月")
    if not calendar_rows:
        st.info("この月の決算予定はありません。")
    for day in sorted({r["earnings_date"] for r in calendar_rows}):
        day_rows = [r for r in calendar_rows if r["earnings_date"] == day]
        st.markdown(f"#### {day}（{day_rows[0]['weekday']}）")
        st.dataframe(earnings_dataframe(day_rows), use_container_width=True, hide_index=True)

with list_tab:
    controls = st.columns(3)
    sort_label = controls[0].selectbox("並び替え", ["決算日が近い順", "決算日が遠い順", "銘柄コード順", "会社名順", "保有株優先", "日付未確認優先"])
    quarter_filter = controls[1].multiselect("四半期", EARNINGS_QUARTERS, default=EARNINGS_QUARTERS)
    all_statuses = ["本日決算", "明日決算", "直前", "今週", "2週間以内", "1か月以内", "先予定", "発表済み", "日付未確認"]
    default_statuses = all_statuses[:-2] + (["日付未確認"] if settings["show_unconfirmed_earnings"] else [])
    status_filter = controls[2].multiselect("状態", all_statuses, default=default_statuses)
    types = st.multiselect("保有区分", ["保有株", "監視銘柄", "関連銘柄", "その他"], default=["保有株", "監視銘柄", "関連銘柄", "その他"])
    show_past = st.checkbox("過去の決算も表示", value=False)
    range_cols = st.columns(2)
    period_start = range_cols[0].date_input("期間（開始）", value=today - timedelta(days=int(settings["past_earnings_days"])) if show_past else today, key="earnings_period_start")
    period_end = range_cols[1].date_input("期間（終了）", value=today + timedelta(days=365), key="earnings_period_end")
    visible = [r for r in prepared if r.get("fiscal_quarter") in quarter_filter and r.get("earnings_status") in status_filter and r.get("category") in types]
    visible = [r for r in visible if r.get("earnings_date") is None or period_start <= date.fromisoformat(r["earnings_date"]) <= period_end]
    if show_past:
        visible = [r for r in visible if r.get("days_until") is None or r["days_until"] >= -int(settings["past_earnings_days"])]
    else:
        visible = [r for r in visible if r.get("days_until") is None or r["days_until"] >= 0]
    st.dataframe(earnings_dataframe(sort_earnings_rows(visible, sort_label)), use_container_width=True, hide_index=True, height=560)

with form_tab:
    if not stocks:
        st.info("先に銘柄を登録してください。")
    else:
        date_status = st.selectbox("日付状態", EARNINGS_DATE_STATUSES, index=1, key="earnings_create_status")
        if date_status == "未確認":
            st.info("決算日は未確認です。日付なしで登録します。")
            st.session_state["earnings_create_date"] = None
        with st.form("earnings_create"):
            cols = st.columns(3)
            selected_stock = cols[0].selectbox("銘柄", list(stock_options))
            fiscal_year = cols[1].number_input("対象年度", min_value=1900, max_value=2200, value=today.year, step=1)
            quarter = cols[2].selectbox("四半期", EARNINGS_QUARTERS)
            earnings_date = st.date_input(
                "決算日",
                value=None,
                disabled=date_status == "未確認",
                key="earnings_create_date",
            )
            announcement_time = st.text_input("発表時間", placeholder="15:00、引け後、場中、未定")
            memo = st.text_area("決算前に確認したいメモ")
            create_submitted = st.form_submit_button("決算イベントを登録")
        if create_submitted:
            try:
                stock = stock_options[selected_stock]
                add_earnings({"stock_id": stock["id"], "fiscal_year": fiscal_year, "fiscal_quarter": quarter, "earnings_date": earnings_date, "announcement_time": announcement_time, "date_status": date_status, "memo": memo})
                st.success("決算イベントを登録しました。")
                st.rerun()
            except sqlite3.IntegrityError:
                st.error("同じ銘柄・年度・四半期は登録済みです。下の編集機能から更新してください。")
                logger.exception("決算イベント重複 stock_id=%s year=%s quarter=%s", stock.get("id"), fiscal_year, quarter)
            except (ValueError, TypeError) as exc:
                st.error(str(exc))
            except Exception:
                st.error("決算イベントの登録に失敗しました。logs/app.logを確認してください。")
                logger.exception("決算イベント登録エラー")

    if events:
        labels = {f"{e['ticker']} {e['fiscal_year']} {e['fiscal_quarter']}": e for e in events}
        selected_event_label = st.selectbox("編集する決算イベント", list(labels), key="earnings_edit_select")
        event = labels[selected_event_label]
        with st.expander("選択した決算イベントを編集・削除"):
            if st.session_state.get("earnings_edit_event_id") != int(event["id"]):
                st.session_state["earnings_edit_event_id"] = int(event["id"])
                st.session_state["edit_status"] = event["date_status"]
                st.session_state["edit_date"] = earnings_form_date_value(event["date_status"], event.get("earnings_date"))
            edit_status = st.selectbox("日付状態", EARNINGS_DATE_STATUSES, key="edit_status")
            if edit_status == "未確認":
                st.info("決算日は未確認です。更新時に日付を空にします。")
                st.session_state["edit_date"] = None
            with st.form("earnings_edit"):
                edit_year = st.number_input("対象年度", 1900, 2200, int(event["fiscal_year"]), key="edit_year")
                edit_quarter = st.selectbox("四半期", EARNINGS_QUARTERS, index=EARNINGS_QUARTERS.index(event["fiscal_quarter"]), key="edit_quarter")
                edit_date = st.date_input("決算日", value=None, disabled=edit_status == "未確認", key="edit_date")
                edit_time = st.text_input("発表時間", value=event.get("announcement_time") or "", key="edit_time")
                edit_memo = st.text_area("メモ", value=event.get("memo") or "", key="edit_memo")
                edit_submitted = st.form_submit_button("更新")
            if edit_submitted:
                try:
                    update_earnings(int(event["id"]), {"stock_id": event["stock_id"], "fiscal_year": edit_year, "fiscal_quarter": edit_quarter, "earnings_date": edit_date, "announcement_time": edit_time, "date_status": edit_status, "memo": edit_memo})
                    st.success("決算イベントを更新しました。")
                    st.rerun()
                except Exception as exc:
                    st.error(f"更新できませんでした: {exc}")
                    logger.exception("決算イベント更新エラー event_id=%s", event["id"])
            confirm_delete = st.checkbox("削除することを確認しました", key="earnings_delete_confirm")
            if st.button("決算イベントを削除", disabled=not confirm_delete):
                try:
                    delete_earnings(int(event["id"]))
                    st.success("決算イベントを削除しました。")
                    st.rerun()
                except Exception as exc:
                    st.error(str(exc))
                    logger.exception("決算イベント削除エラー event_id=%s", event["id"])

    st.divider()
    st.download_button("決算CSVをダウンロード", export_earnings_csv(events), "orekabu_earnings.csv", "text/csv")
    earnings_upload = st.file_uploader("決算CSVをインポート", type=["csv"], key="earnings_csv")
    if earnings_upload:
        preview, errors = parse_earnings_csv(earnings_upload)
        for error in errors: st.error(error)
        if not errors:
            st.dataframe(preview, use_container_width=True, hide_index=True)
            update_existing = st.radio("既存データ", ["更新", "スキップ"], horizontal=True, key="earnings_csv_mode") == "更新"
            if st.button("決算CSVインポート実行"):
                result = import_earnings_csv(preview, update_existing)
                st.write(f"成功: {result['inserted']}件 / 更新: {result['updated']}件 / スキップ: {result['skipped']}件 / 失敗: {result['failed']}件")
                for error in result["errors"]: st.error(error)

with relations_tab:
    relations = list_relations()
    st.caption("矢印は『影響を受ける銘柄 ← 関連銘柄』です。双方向は別々に登録します。")
    if len(stocks) < 2:
        st.info("関連銘柄の登録には2銘柄以上必要です。")
    else:
        with st.form("relation_create"):
            cols = st.columns(2)
            source_label = cols[0].selectbox("影響を受ける銘柄", list(stock_options))
            related_label = cols[1].selectbox("関連銘柄", list(stock_options), index=1)
            relation_type = cols[0].selectbox("関係タイプ", RELATION_TYPES)
            impact_level = cols[1].selectbox("影響度", IMPACT_LEVELS, index=1)
            relation_memo = st.text_area("メモ", key="relation_memo")
            relation_submitted = st.form_submit_button("関連銘柄を登録")
        if relation_submitted:
            try:
                add_relation({"source_stock_id": stock_options[source_label]["id"], "related_stock_id": stock_options[related_label]["id"], "relation_type": relation_type, "impact_level": impact_level, "memo": relation_memo})
                st.success("関連銘柄を登録しました。")
                st.rerun()
            except (ValueError, sqlite3.IntegrityError) as exc:
                st.error("同じ関係は登録済みです。" if isinstance(exc, sqlite3.IntegrityError) else str(exc))
                logger.exception("関連銘柄登録エラー")
    impacts = impact_candidates()
    st.dataframe(impact_dataframe(impacts), use_container_width=True, hide_index=True)
    if relations:
        relation_labels = {f"{r['source_ticker']} ← {r['related_ticker']}": r for r in relations}
        selected_relation = relation_labels[st.selectbox("編集する関連", list(relation_labels), key="relation_edit_select")]
        with st.expander("選択した関連銘柄を編集・削除"):
            stock_labels_by_id = {int(s["id"]): label for label, s in stock_options.items()}
            edit_source_label = st.selectbox("影響を受ける銘柄", list(stock_options), index=list(stock_options).index(stock_labels_by_id[int(selected_relation["source_stock_id"])]), key="relation_edit_source")
            edit_related_label = st.selectbox("関連銘柄", list(stock_options), index=list(stock_options).index(stock_labels_by_id[int(selected_relation["related_stock_id"])]), key="relation_edit_related")
            edit_type = st.selectbox("関係タイプ", RELATION_TYPES, index=RELATION_TYPES.index(selected_relation["relation_type"]), key="relation_edit_type")
            edit_impact = st.selectbox("影響度", IMPACT_LEVELS, index=IMPACT_LEVELS.index(selected_relation["impact_level"]), key="relation_edit_impact")
            edit_relation_memo = st.text_area("メモ", value=selected_relation.get("memo") or "", key="relation_edit_memo")
            if st.button("関連銘柄を更新"):
                try:
                    update_relation(int(selected_relation["id"]), {**selected_relation, "source_stock_id": stock_options[edit_source_label]["id"], "related_stock_id": stock_options[edit_related_label]["id"], "relation_type": edit_type, "impact_level": edit_impact, "memo": edit_relation_memo})
                    st.success("関連銘柄を更新しました。")
                    st.rerun()
                except Exception as exc:
                    st.error(str(exc)); logger.exception("関連銘柄更新エラー relation_id=%s", selected_relation["id"])
            relation_delete_confirm = st.checkbox("関連銘柄を削除することを確認しました")
            if st.button("関連銘柄を削除", disabled=not relation_delete_confirm):
                try:
                    delete_relation(int(selected_relation["id"])); st.success("関連銘柄を削除しました。"); st.rerun()
                except Exception as exc:
                    st.error(str(exc)); logger.exception("関連銘柄削除エラー relation_id=%s", selected_relation["id"])
    st.download_button("関連銘柄CSVをダウンロード", export_relations_csv(relations), "orekabu_relations.csv", "text/csv")
    relations_upload = st.file_uploader("関連銘柄CSVをインポート", type=["csv"], key="relations_csv")
    if relations_upload:
        preview, errors = parse_relations_csv(relations_upload)
        for error in errors: st.error(error)
        if not errors:
            st.dataframe(preview, use_container_width=True, hide_index=True)
            update_existing = st.radio("既存データ", ["更新", "スキップ"], horizontal=True, key="relations_csv_mode") == "更新"
            if st.button("関連銘柄CSVインポート実行"):
                result = import_relations_csv(preview, update_existing)
                st.write(f"成功: {result['inserted']}件 / 更新: {result['updated']}件 / スキップ: {result['skipped']}件 / 失敗: {result['failed']}件")
                for error in result["errors"]: st.error(error)

with impacts_tab:
    st.caption("関連銘柄の決算は、自分の銘柄へ必ず影響するものではありません。確認対象を整理するための機能です。")
    impact_rows = impact_candidates()
    if impact_rows:
        st.dataframe(impact_dataframe(impact_rows), use_container_width=True, hide_index=True, height=560)
    else:
        st.info("関連銘柄または関連銘柄の決算予定が登録されていません。")
