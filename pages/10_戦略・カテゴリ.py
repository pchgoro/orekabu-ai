"""Strategy tags, reusable rules, bulk application, conflicts, and summaries."""

from __future__ import annotations

import logging

import pandas as pd
import streamlit as st

from components.layout import apply_responsive_styles
from components.navigation import company_profile_button
from components.strategy_rules import RULE_TYPE_LABELS
from services.database import get_stocks, init_db, load_settings
from services.earnings_view_models import enrich_stock_rows
from services.stock_data import build_analysis_rows
from services.strategy_rules import (
    COLOR_KEYS,
    RULE_TYPES,
    TAG_GROUPS,
    aggregate_by_tag,
    apply_bulk_preview,
    attach_strategy_context,
    bulk_assign_tags,
    delete_rule_set,
    delete_tag,
    enrich_rows_with_strategy,
    export_rule_csv,
    export_tag_csv,
    import_rule_csv,
    import_tag_csv,
    list_rule_sets,
    list_tags,
    parse_rule_csv,
    parse_tag_csv,
    preview_bulk_apply,
    save_rule_set,
    save_tag,
    set_tag_active,
)
from utils.formatters import fmt_percent, fmt_price, fmt_signed_percent, fmt_signed_price
from utils.logging_config import setup_logging

logger = logging.getLogger(__name__)


def _stock_display(row: dict[str, object]) -> dict[str, object]:
    """Build one missing-value-safe row for the tag stock list."""
    lines = row.get("strategy_lines") or {}
    tags_text = " / ".join(
        str(tag.get("name")) for tag in row.get("strategy_tags") or []
    )
    return {
        "ticker": row.get("ticker"),
        "会社名": row.get("company_name"),
        "保有数": row.get("shares"),
        "平均取得単価": fmt_price(row.get("average_price")),
        "現在値": fmt_price(row.get("current_price")),
        "評価損益": fmt_signed_price(row.get("profit")),
        "損益率": fmt_signed_percent(row.get("profit_pct")),
        "損切価格": fmt_price(lines.get("stop_loss_price")),
        "利確価格": fmt_price(lines.get("take_profit_price")),
        "買い増し価格": fmt_price(lines.get("add_position_price")),
        "状態": row.get("strategy_status"),
        "ルール由来": row.get("strategy_source"),
        "次回決算": row.get("next_earnings_date_display"),
        "未読ニュース": row.get("unread_news"),
        "重要開示": row.get("important_disclosures"),
        "他タグ": tags_text,
    }


st.set_page_config(page_title="戦略・カテゴリ - オレ株AI", layout="wide")
setup_logging()
init_db()
settings = load_settings()
apply_responsive_styles(settings["display_density"])

st.title("戦略・カテゴリ")
st.caption(
    "タグルールは自動売買や売買推奨ではありません。個別ルールを優先し、"
    "タグ候補の一括適用前には必ずプレビューします。"
)

stocks = get_stocks()
rows = attach_strategy_context(
    enrich_rows_with_strategy(
        enrich_stock_rows(
            build_analysis_rows(stocks, settings),
            near_days=int(settings["earnings_near_days"]),
        ),
        near_percent=float(settings["strategy_rule_near_percent"]),
    )
)
tags = list_tags()
rules = list_rule_sets()
stock_labels = {f"{row['ticker']} {row['company_name']}": row for row in rows}
tag_labels = {
    f"{row['tag_group']} / {row['name']}": row for row in tags
}

tabs = st.tabs(
    ["タグ一覧", "タグ別銘柄", "ルール設定", "一括適用", "競合確認", "集計"]
)

with tabs[0]:
    st.subheader("タグ管理")
    st.dataframe(
        pd.DataFrame(
            [
                {
                    "ID": row["id"],
                    "グループ": row["tag_group"],
                    "タグ": row["name"],
                    "説明": row["description"],
                    "色": row["color_key"],
                    "表示順": row["display_order"],
                    "状態": "有効" if row["is_active"] else "無効",
                    "銘柄数": row["stock_count"],
                }
                for row in tags
            ]
        ),
        hide_index=True,
        use_container_width=True,
    )
    edit_options = ["新規作成", *tag_labels]
    edit_label = st.selectbox("編集対象", edit_options)
    editing = tag_labels.get(edit_label)
    with st.form("strategy_tag_form"):
        cols = st.columns(3)
        name = cols[0].text_input("タグ名", str((editing or {}).get("name") or ""))
        group = cols[1].selectbox(
            "グループ",
            TAG_GROUPS,
            index=TAG_GROUPS.index(str((editing or {}).get("tag_group") or "custom")),
        )
        color = cols[2].selectbox(
            "色",
            COLOR_KEYS,
            index=COLOR_KEYS.index(str((editing or {}).get("color_key") or "info")),
        )
        description = st.text_input(
            "説明", str((editing or {}).get("description") or "")
        )
        order = st.number_input(
            "表示順", min_value=0, max_value=9999,
            value=int((editing or {}).get("display_order") or 0),
        )
        active = st.checkbox(
            "有効", value=bool((editing or {}).get("is_active", True))
        )
        if st.form_submit_button("タグを保存"):
            try:
                save_tag(
                    {
                        "name": name,
                        "tag_group": group,
                        "description": description,
                        "color_key": color,
                        "display_order": order,
                        "is_active": active,
                    },
                    tag_id=int(editing["id"]) if editing else None,
                )
                st.success("タグを保存しました。")
                st.rerun()
            except Exception as exc:
                logger.exception("戦略タグ保存失敗")
                st.error(str(exc))
    if editing:
        action_cols = st.columns(2)
        if action_cols[0].button(
            "無効化" if editing["is_active"] else "有効化",
            key=f"toggle_tag_{editing['id']}",
        ):
            set_tag_active(int(editing["id"]), not bool(editing["is_active"]))
            st.rerun()
        if action_cols[1].button("未使用タグを削除", key=f"delete_tag_{editing['id']}"):
            try:
                delete_tag(int(editing["id"]))
                st.success("タグを削除しました。")
                st.rerun()
            except Exception as exc:
                st.warning(str(exc))

    st.subheader("銘柄への一括割当・解除")
    selected_stocks = st.multiselect("銘柄", list(stock_labels), key="bulk_tag_stocks")
    selected_tags = st.multiselect("タグ", list(tag_labels), key="bulk_tag_tags")
    assign_cols = st.columns(2)
    if assign_cols[0].button("選択タグを割り当て"):
        changed = bulk_assign_tags(
            [stock_labels[label]["id"] for label in selected_stocks],
            [tag_labels[label]["id"] for label in selected_tags],
        )
        st.success(f"{changed}件の関連を追加しました。")
        st.rerun()
    if assign_cols[1].button("選択タグを解除"):
        changed = bulk_assign_tags(
            [stock_labels[label]["id"] for label in selected_stocks],
            [tag_labels[label]["id"] for label in selected_tags],
            remove=True,
        )
        st.success(f"{changed}件の関連を解除しました。")
        st.rerun()

    st.subheader("タグCSV")
    st.download_button(
        "現在のタグ割当をCSV出力",
        export_tag_csv(),
        "strategy_tags.csv",
        "text/csv",
    )
    tag_csv = st.file_uploader("ticker,tags CSV", type=["csv"], key="tag_csv")
    if tag_csv:
        parsed = parse_tag_csv(tag_csv.getvalue())
        st.dataframe(pd.DataFrame(parsed), hide_index=True, use_container_width=True)
        replace = st.checkbox("既存割当をCSV内容で置き換える", value=True)
        if st.button("タグCSVをインポート"):
            result = import_tag_csv(parsed, update_existing=replace)
            st.success(str(result))
            st.rerun()

with tabs[1]:
    st.subheader("タグ別銘柄")
    filters = st.columns(3)
    group_filter = filters[0].selectbox("タググループ", ["すべて", *TAG_GROUPS])
    available = [
        label for label, row in tag_labels.items()
        if group_filter == "すべて" or row["tag_group"] == group_filter
    ]
    tag_filter = filters[1].selectbox("タグ", ["すべて", *available])
    holding_filter = filters[2].selectbox("区分", ["すべて", "保有株", "監視銘柄"])
    extra_filters = st.columns(3)
    state_filter = extra_filters[0].selectbox(
        "ライン状態",
        ["すべて", "損切到達", "損切接近", "利確到達", "利確接近", "買い増し到達", "買い増し接近", "通常", "未設定", "競合"],
    )
    profit_filter = extra_filters[1].selectbox(
        "損益", ["すべて", "含み益", "含み損", "損益なし"]
    )
    earnings_filter = extra_filters[2].selectbox(
        "決算", ["すべて", "7日以内", "8日以降", "未登録"]
    )
    selected_tag_id = int(tag_labels[tag_filter]["id"]) if tag_filter != "すべて" else None
    filtered = []
    for row in rows:
        row_tag_ids = {int(tag["id"]) for tag in row["strategy_tags"]}
        if selected_tag_id and selected_tag_id not in row_tag_ids:
            continue
        if group_filter != "すべて" and not any(
            tag["tag_group"] == group_filter for tag in row["strategy_tags"]
        ):
            continue
        if holding_filter == "保有株" and not row.get("is_holding"):
            continue
        if holding_filter == "監視銘柄" and row.get("is_holding"):
            continue
        if state_filter != "すべて" and row.get("strategy_status") != state_filter:
            continue
        profit = row.get("profit")
        if profit_filter == "含み益" and not isinstance(profit, (int, float)):
            continue
        if profit_filter == "含み益" and float(profit) <= 0:
            continue
        if profit_filter == "含み損" and (
            not isinstance(profit, (int, float)) or float(profit) >= 0
        ):
            continue
        if profit_filter == "損益なし" and isinstance(profit, (int, float)) and float(profit) != 0:
            continue
        days = row.get("earnings_days_until")
        if earnings_filter == "7日以内" and not (
            isinstance(days, int) and 0 <= days <= 7
        ):
            continue
        if earnings_filter == "8日以降" and not (
            isinstance(days, int) and days >= 8
        ):
            continue
        if earnings_filter == "未登録" and days is not None:
            continue
        filtered.append(row)
    st.dataframe(
        pd.DataFrame([_stock_display(row) for row in filtered]),
        hide_index=True,
        use_container_width=True,
        height=540,
    )
    if filtered:
        open_labels = {f"{row['ticker']} {row['company_name']}": row for row in filtered}
        open_label = st.selectbox("企業カルテを開く", list(open_labels))
        company_profile_button(
            open_labels[open_label]["ticker"],
            "選択した企業カルテを開く",
            key="strategy_company_profile",
        )

with tabs[2]:
    st.subheader("タグルール設定")
    active_tag_labels = {
        label: row for label, row in tag_labels.items() if row["is_active"]
    }
    if not active_tag_labels:
        st.info("有効なタグを作成または有効化するとルールを設定できます。")
    else:
        selected_rule_label = st.selectbox(
            "ルールを設定するタグ", list(active_tag_labels)
        )
        selected_tag = active_tag_labels[selected_rule_label]
        current = next(
            (
                row for row in rules
                if int(row["tag_id"]) == int(selected_tag["id"])
            ),
            {},
        )
        with st.form("tag_rule_form"):
            values: dict[str, object] = {}
            for role, label in (
                ("stop_loss", "損切"),
                ("take_profit", "利確"),
                ("add_position", "買い増し"),
            ):
                cols = st.columns([2, 1])
                current_type = str(current.get(f"{role}_type") or "none")
                values[f"{role}_type"] = cols[0].selectbox(
                    f"{label}種類",
                    RULE_TYPES,
                    index=RULE_TYPES.index(current_type),
                    format_func=lambda value: RULE_TYPE_LABELS[value],
                    key=f"tag_rule_{role}_type",
                )
                values[f"{role}_value"] = cols[1].number_input(
                    f"{label}値",
                    min_value=0.0,
                    step=0.5,
                    value=float(current.get(f"{role}_value") or 0),
                    key=f"tag_rule_{role}_value",
                )
            values["earnings_policy"] = st.text_input(
                "決算方針", str(current.get("earnings_policy") or "")
            )
            values["priority"] = st.number_input(
                "優先度", min_value=-9999, max_value=9999,
                value=int(current.get("priority") or 0),
            )
            values["memo"] = st.text_area(
                "メモ", str(current.get("memo") or "")
            )
            if st.form_submit_button("タグルールを保存"):
                try:
                    save_rule_set(int(selected_tag["id"]), values)
                    st.success("タグルールを保存しました。")
                    st.rerun()
                except Exception as exc:
                    logger.exception(
                        "タグルール保存失敗 tag_id=%s",
                        selected_tag["id"],
                    )
                    st.error(str(exc))
        if current and st.button("このタグルールを削除"):
            delete_rule_set(int(selected_tag["id"]))
            st.rerun()

    st.subheader("ルールCSV")
    st.download_button(
        "現在のタグルールをCSV出力",
        export_rule_csv(),
        "strategy_rules.csv",
        "text/csv",
    )
    rule_csv = st.file_uploader("ルールCSV", type=["csv"], key="rule_csv")
    if rule_csv:
        parsed = parse_rule_csv(rule_csv.getvalue())
        st.dataframe(pd.DataFrame(parsed), hide_index=True, use_container_width=True)
        update = st.checkbox("既存ルールを更新", value=True)
        if st.button("ルールCSVをインポート"):
            st.success(str(import_rule_csv(parsed, update_existing=update)))
            st.rerun()

with tabs[3]:
    st.subheader("一括適用")
    st.caption("個別上書きは維持し、競合は適用しません。")
    apply_labels = st.multiselect(
        "対象銘柄", list(stock_labels),
        default=[label for label, row in stock_labels.items() if row.get("is_holding")],
    )
    if st.button("適用プレビューを作成"):
        st.session_state["strategy_apply_preview"] = preview_bulk_apply(
            [stock_labels[label]["id"] for label in apply_labels]
        )
    preview = st.session_state.get("strategy_apply_preview") or []
    if preview:
        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "ticker": row["ticker"],
                        "会社名": row["company_name"],
                        "判定": row["action"],
                        "由来": row["source"],
                    }
                    for row in preview
                ]
            ),
            hide_index=True,
            use_container_width=True,
        )
        selectable = {
            f"{row['ticker']} {row['company_name']}": int(row["stock_id"])
            for row in preview if row["action"] in {"新規", "更新", "同一"}
        }
        selected_apply = st.multiselect(
            "適用する銘柄", list(selectable), default=list(selectable)
        )
        if st.button("選択した候補を適用"):
            result = apply_bulk_preview(
                preview, [selectable[label] for label in selected_apply]
            )
            st.success(str(result))
            st.session_state.pop("strategy_apply_preview", None)
            st.rerun()

with tabs[4]:
    st.subheader("競合確認")
    conflicts = [
        row for row in rows
        if (row.get("strategy_rule_resolution") or {}).get("conflict")
    ]
    if not conflicts:
        st.info("同順位のルール競合はありません。")
    for row in conflicts:
        with st.container(border=True):
            st.write(f"**{row['ticker']} {row['company_name']}**")
            candidates = row["strategy_rule_resolution"]["candidates"]
            st.caption(
                " / ".join(
                    f"{item['tag_group']}:{item['tag_name']} 優先度{item['priority']}"
                    for item in candidates
                )
            )
            company_profile_button(
                row["ticker"], "企業カルテで個別ルールを設定",
                key=f"conflict_profile_{row['id']}",
            )

with tabs[5]:
    st.subheader("タグ別集計")
    st.caption(
        "1銘柄に複数タグを付けられるため、全タグの評価額合計は"
        "ポートフォリオ合計を超える場合があります。"
    )
    aggregates = aggregate_by_tag(rows)
    st.dataframe(
        pd.DataFrame(
            [
                {
                    "グループ": row["tag_group"],
                    "タグ": row["tag"],
                    "銘柄数": row["stock_count"],
                    "保有評価額": fmt_price(row["market_value"]),
                    "評価損益": fmt_signed_price(row["profit_loss"]),
                    "平均損益率": fmt_signed_percent(row["average_profit_rate"]),
                    "ポートフォリオ比率": fmt_percent(row["portfolio_ratio"]),
                    "7日以内決算": row["earnings_7d"],
                    "未読ニュース": row["unread_news"],
                    "重要開示": row["important_disclosures"],
                    "損切接近": row["stop_near"],
                    "利確接近": row["take_near"],
                }
                for row in aggregates
            ]
        ),
        hide_index=True,
        use_container_width=True,
    )
