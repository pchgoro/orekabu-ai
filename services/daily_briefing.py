"""Pure view-model builders for the daily dashboard briefing."""

from __future__ import annotations

from typing import Any


def build_briefing(
    stock_rows: list[dict[str, Any]], earnings_rows: list[dict[str, Any]],
    candidates: list[dict[str, Any]], news_rows: list[dict[str, Any]],
    buy_watch_rows: list[dict[str, Any]], news_summary: dict[str, Any],
    rss_failed_count: int = 0, disclosure_rows: list[dict[str, Any]] | None = None,
    playbook_rows: list[dict[str, Any]] | None = None,
    strategy_rows: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Aggregate explainable daily counts without DB or UI dependencies."""
    pending = [row for row in candidates if row.get("review_status") == "pending"]
    disclosures = disclosure_rows or []
    rules = [row for row in (playbook_rows or []) if row.get("is_holding")]
    strategies = [row for row in (strategy_rows or []) if row.get("is_holding")]
    items = [
        _item("本日決算", sum(row.get("days_until") == 0 for row in earnings_rows), "決算", "danger"),
        _item("7日以内の決算", sum(isinstance(row.get("days_until"), int) and 0 <= row["days_until"] <= 7 for row in earnings_rows), "決算", "warning"),
        _item("未確認の決算候補", len(pending), "決算", "warning"),
        _item("日付変更候補", sum(row.get("comparison_status") == "date_changed" for row in pending), "決算", "warning"),
        _item("競合候補", sum(row.get("comparison_status") == "conflict" for row in pending), "決算", "danger"),
        _item("今日のニュース", int(news_summary.get("today", 0)), "ニュース", "normal"),
        _item("未読ニュース", int(news_summary.get("unread", 0)), "ニュース", "normal"),
        _item("重要ニュース", sum(not row.get("is_read") and row.get("importance") == "高" for row in news_rows), "ニュース", "danger"),
        _item("お気に入り", int(news_summary.get("favorites", 0)), "ニュース", "normal"),
        _item("買い検討ライン到達", sum(row.get("buy_watch_status") == "到達" for row in buy_watch_rows), "買い検討ライン", "danger"),
        _item("買い検討ライン接近", sum(row.get("buy_watch_status") == "接近中" for row in buy_watch_rows), "買い検討ライン", "warning"),
        _item("注目スコア65以上", sum(float(row.get("score") or 0) >= 65 for row in stock_rows), "app", "warning"),
        _item("株価取得失敗", sum(row.get("data_status") != "OK" for row in stock_rows), "app", "danger"),
        _item("RSS取得失敗", int(rss_failed_count), "ニュース", "danger"),
        _item("今日の開示", sum(str(row.get("disclosed_at") or "")[:10] == _today() for row in disclosures), "適時開示", "normal"),
        _item("未読開示", sum(not row.get("is_read") for row in disclosures), "適時開示", "warning"),
        _item("重要度高の開示", sum(row.get("importance") == "高" for row in disclosures), "適時開示", "danger"),
        _item("保有株開示", sum(bool(row.get("is_holding")) for row in disclosures), "適時開示", "normal"),
        _item("利確ライン到達", sum((row.get("playbook_evaluation") or {}).get("take_profit_reached") for row in rules), "企業カルテ", "positive"),
        _item("利確まで5%以内", sum((row.get("playbook_evaluation") or {}).get("take_profit_near") for row in rules), "企業カルテ", "warning"),
        _item("損切りライン到達", sum((row.get("playbook_evaluation") or {}).get("stop_loss_reached") for row in rules), "企業カルテ", "negative"),
        _item("損切りまで5%以内", sum((row.get("playbook_evaluation") or {}).get("stop_loss_near") for row in rules), "企業カルテ", "warning"),
        _item("投資ルール未設定", sum(not (row.get("playbook_evaluation") or {}).get("configured") for row in rules), "企業カルテ", "muted"),
        _item("戦略損切到達", sum(bool((row.get("strategy_lines") or {}).get("stop_loss_reached")) for row in strategies), "戦略・カテゴリ", "negative"),
        _item("戦略損切接近", sum(bool((row.get("strategy_lines") or {}).get("stop_loss_near")) for row in strategies), "戦略・カテゴリ", "warning"),
        _item("戦略利確到達", sum(bool((row.get("strategy_lines") or {}).get("take_profit_reached")) for row in strategies), "戦略・カテゴリ", "positive"),
        _item("戦略利確接近", sum(bool((row.get("strategy_lines") or {}).get("take_profit_near")) for row in strategies), "戦略・カテゴリ", "warning"),
        _item("戦略ルール競合", sum(bool((row.get("strategy_rule_resolution") or {}).get("conflict")) for row in strategies), "戦略・カテゴリ", "danger"),
        _item(
            "戦略ルール未設定",
            sum(
                not (row.get("strategy_rule_resolution") or {}).get("conflict")
                and not (row.get("strategy_lines") or {}).get("configured")
                for row in strategies
            ),
            "戦略・カテゴリ",
            "muted",
        ),
    ]
    return items


def build_daily_tasks(
    stock_rows: list[dict[str, Any]], earnings_rows: list[dict[str, Any]],
    candidates: list[dict[str, Any]], news_rows: list[dict[str, Any]],
    buy_watch_rows: list[dict[str, Any]], rss_failed_count: int = 0, limit: int = 10,
    disclosure_rows: list[dict[str, Any]] | None = None,
    playbook_rows: list[dict[str, Any]] | None = None,
    strategy_rows: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Create up to ten actions in the documented priority order."""
    tasks: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()

    def append_task(
        priority: int, label: str, detail: str, page: str, kind: str,
        identity: Any, ticker: str = "",
    ) -> None:
        """Keep the first, highest-priority task for the same logical target."""
        key = (kind, str(identity or detail))
        if key not in seen:
            seen.add(key)
            tasks.append(_task(priority, label, detail, page, ticker))

    rules = [row for row in (playbook_rows or []) if row.get("is_holding")]
    strategies = [row for row in (strategy_rows or []) if row.get("is_holding")]
    unset_strategies: list[dict[str, Any]] = []
    for row in strategies:
        resolution = row.get("strategy_rule_resolution") or {}
        lines = row.get("strategy_lines") or {}
        ticker = str(row.get("ticker") or "")
        if resolution.get("conflict"):
            append_task(
                0, "戦略ルール競合", _stock_label(row), "企業カルテ",
                "strategy", _row_identity(row), ticker,
            )
        elif lines.get("stop_loss_reached"):
            append_task(
                -8, "戦略損切ライン到達", _stock_label(row), "企業カルテ",
                "strategy", _row_identity(row), ticker,
            )
        elif lines.get("take_profit_reached"):
            append_task(
                -7, "戦略利確ライン到達", _stock_label(row), "企業カルテ",
                "strategy", _row_identity(row), ticker,
            )
        elif not lines.get("configured"):
            unset_strategies.append(row)
    unset_rules: list[dict[str, Any]] = []
    for row in rules:
        evaluation = row.get("playbook_evaluation") or {}
        ticker = str(row.get("ticker") or "")
        if not evaluation.get("configured"):
            unset_rules.append(row)
        elif evaluation.get("stop_loss_reached"):
            append_task(-4, "損切りライン到達", _stock_label(row), "企業カルテ", "playbook", _row_identity(row), ticker)
        elif evaluation.get("take_profit_reached"):
            append_task(-3, "利確ライン到達", _stock_label(row), "企業カルテ", "playbook", _row_identity(row), ticker)
        elif evaluation.get("stop_loss_near"):
            append_task(-2, "損切りまで5%以内", _stock_label(row), "企業カルテ", "playbook", _row_identity(row), ticker)
        elif evaluation.get("take_profit_near"):
            append_task(-1, "利確まで5%以内", _stock_label(row), "企業カルテ", "playbook", _row_identity(row), ticker)

    for row in earnings_rows:
        days = row.get("days_until")
        if days == 0:
            append_task(1, "本日決算", _stock_label(row), "決算", "earnings", _row_identity(row))
        elif isinstance(days, int) and 1 <= days <= 3:
            append_task(2, f"決算まであと{days}日", _stock_label(row), "決算", "earnings", _row_identity(row))
    for comparison_status, priority, label in (
        ("conflict", 3, "決算候補の競合"),
        ("date_changed", 4, "決算日の変更候補"),
    ):
        for row in candidates:
            if row.get("review_status") == "pending" and row.get("comparison_status") == comparison_status:
                append_task(priority, label, _stock_label(row), "決算", "candidate", _row_identity(row))
    for row in buy_watch_rows:
        if row.get("buy_watch_status") == "到達":
            append_task(5, "買い検討ライン到達", _stock_label(row), "買い検討ライン", "buy_watch", _row_identity(row))
    for row in news_rows:
        if not row.get("is_read") and row.get("importance") == "高":
            append_task(6, "重要ニュースを確認", row.get("title") or "タイトルなし", "ニュース", "news", _news_identity(row))
    for row in news_rows:
        if not row.get("is_read") and row.get("has_holding_match"):
            append_task(7, "保有株ニュースを確認", row.get("title") or "タイトルなし", "ニュース", "news", _news_identity(row))
    for row in sorted(stock_rows, key=lambda item: float(item.get("score") or 0), reverse=True):
        if float(row.get("score") or 0) >= 65:
            target = "保有株" if row.get("is_holding") else "監視銘柄"
            append_task(8, f"注目スコア {int(row['score'])}", _stock_label(row), target, "score", _row_identity(row))
    for row in stock_rows:
        ore_score = row.get("ore_score") or {}
        classification = ore_score.get("classification")
        if classification == "売却候補":
            append_task(5, "オレ株スコア: 売却候補", _stock_label(row), "企業カルテ", "ore_score", f"sell:{_row_identity(row)}")
        elif classification == "買い候補":
            append_task(8, "オレ株スコア: 買い候補", _stock_label(row), "企業カルテ", "ore_score", f"buy:{_row_identity(row)}")

        if row.get("is_holding"):
            if ore_score.get("stop_loss_reached"):
                append_task(5, "ルール逸脱: カテゴリ損切りライン到達", _stock_label(row), "企業カルテ", "ore_score_rule", f"stop:{_row_identity(row)}")
            if ore_score.get("take_profit_reached"):
                append_task(5, "ルール逸脱: カテゴリ利確ライン到達", _stock_label(row), "企業カルテ", "ore_score_rule", f"profit:{_row_identity(row)}")

    total_portfolio_value = sum((r.get("shares") or 0) * (r.get("current_price") or 0.0) for r in stock_rows if r.get("is_holding"))
    if total_portfolio_value > 0:
        cat_portfolio_values = {}
        cat_max_ratios = {}
        for r in stock_rows:
            if not r.get("is_holding") or not r.get("shares"):
                continue
            val = (r.get("shares") or 0) * (r.get("current_price") or 0.0)
            ore_score = r.get("ore_score") or {}
            for cat in ore_score.get("categories") or []:
                cat_name = cat["name"]
                cat_portfolio_values[cat_name] = cat_portfolio_values.get(cat_name, 0.0) + val
            for rule in ore_score.get("trade_rules") or []:
                cat_name = next((c["name"] for c in ore_score.get("categories") or [] if c["id"] == rule["category_id"]), None)
                if cat_name and rule.get("max_holding_ratio_percent") is not None:
                    cat_max_ratios[cat_name] = float(rule["max_holding_ratio_percent"])

        for cat_name, max_ratio in cat_max_ratios.items():
            curr_ratio = (cat_portfolio_values.get(cat_name, 0.0) / total_portfolio_value) * 100.0
            if curr_ratio > max_ratio:
                append_task(
                    5,
                    "カテゴリ比率超過",
                    f"{cat_name} ({curr_ratio:.1f}% > 最大{max_ratio:.1f}%)",
                    "テーマ管理",
                    "category_ratio",
                    cat_name
                )

    if rss_failed_count:
        append_task(9, "RSS取得失敗を確認", f"{rss_failed_count}件", "ニュース", "rss", "latest")
    disclosures = disclosure_rows or []
    disclosure_rules = (
        ("業績予想修正", 10, "業績予想修正を確認"),
        ("配当修正", 11, "配当修正を確認"),
        ("決算短信", 12, "決算短信を確認"),
    )
    for disclosure_type, priority, label in disclosure_rules:
        for row in disclosures:
            if not row.get("is_read") and row.get("disclosure_type") == disclosure_type:
                append_task(priority, label, _stock_label(row), "適時開示", "disclosure", _row_identity(row))
    for row in disclosures:
        if not row.get("is_read") and row.get("importance") == "高" and row.get("is_holding"):
            append_task(13, "保有株の重要開示を確認", _stock_label(row), "適時開示", "disclosure", _row_identity(row))
    if unset_rules:
        ticker = str(unset_rules[0].get("ticker") or "") if len(unset_rules) == 1 else ""
        append_task(
            7,
            "投資ルール未設定",
            f"{len(unset_rules)}銘柄",
            "企業カルテ" if ticker else "保有株",
            "playbook_unset",
            "all",
            ticker,
        )
    if unset_strategies:
        ticker = (
            str(unset_strategies[0].get("ticker") or "")
            if len(unset_strategies) == 1 else ""
        )
        append_task(
            14,
            "戦略ルール未設定",
            f"{len(unset_strategies)}銘柄",
            "企業カルテ" if ticker else "戦略・カテゴリ",
            "strategy_unset",
            "all",
            ticker,
        )
    return sorted(tasks, key=lambda item: item["priority"])[: max(1, min(int(limit), 10))]


def _item(label: str, count: int, page: str, state: str) -> dict[str, Any]:
    return {"label": label, "count": int(count), "page": page, "state": state}


def _task(
    priority: int, label: str, detail: str, page: str, ticker: str = "",
) -> dict[str, Any]:
    return {
        "priority": priority,
        "label": label,
        "detail": detail,
        "page": page,
        "ticker": ticker,
    }


def _stock_label(row: dict[str, Any]) -> str:
    return " ".join(part for part in [str(row.get("ticker") or ""), str(row.get("company_name") or "")] if part).strip() or "対象不明"


def _row_identity(row: dict[str, Any]) -> Any:
    """Return a stable identity while remaining safe for incomplete view-model rows."""
    return row.get("id") or row.get("candidate_id") or row.get("ticker") or _stock_label(row)


def _news_identity(row: dict[str, Any]) -> Any:
    """Identify an article consistently across importance and holding-match rules."""
    return row.get("id") or row.get("deduplication_key") or row.get("url") or row.get("title") or "タイトルなし"


def _today() -> str:
    from datetime import datetime
    return datetime.now().date().isoformat()
