"""Pure view-model builders for the daily dashboard briefing."""

from __future__ import annotations

from typing import Any


def build_briefing(
    stock_rows: list[dict[str, Any]], earnings_rows: list[dict[str, Any]],
    candidates: list[dict[str, Any]], news_rows: list[dict[str, Any]],
    buy_watch_rows: list[dict[str, Any]], news_summary: dict[str, Any],
    rss_failed_count: int = 0,
) -> list[dict[str, Any]]:
    """Aggregate explainable daily counts without DB or UI dependencies."""
    pending = [row for row in candidates if row.get("review_status") == "pending"]
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
    ]
    return items


def build_daily_tasks(
    stock_rows: list[dict[str, Any]], earnings_rows: list[dict[str, Any]],
    candidates: list[dict[str, Any]], news_rows: list[dict[str, Any]],
    buy_watch_rows: list[dict[str, Any]], rss_failed_count: int = 0, limit: int = 10,
) -> list[dict[str, Any]]:
    """Create up to ten actions in the documented priority order."""
    tasks: list[dict[str, Any]] = []
    for row in earnings_rows:
        days = row.get("days_until")
        if days == 0:
            tasks.append(_task(1, "本日決算", _stock_label(row), "決算"))
        elif isinstance(days, int) and 1 <= days <= 3:
            tasks.append(_task(2, f"決算まであと{days}日", _stock_label(row), "決算"))
    for row in candidates:
        if row.get("review_status") == "pending" and row.get("comparison_status") in {"conflict", "date_changed"}:
            label = "決算候補の競合" if row.get("comparison_status") == "conflict" else "決算日の変更候補"
            tasks.append(_task(3, label, _stock_label(row), "決算"))
    for row in buy_watch_rows:
        if row.get("buy_watch_status") == "到達":
            tasks.append(_task(4, "買い検討ライン到達", _stock_label(row), "買い検討ライン"))
    for row in news_rows:
        if not row.get("is_read") and row.get("importance") == "高":
            tasks.append(_task(5, "重要ニュースを確認", row.get("title") or "タイトルなし", "ニュース"))
    for row in news_rows:
        if not row.get("is_read") and row.get("has_holding_match"):
            tasks.append(_task(6, "保有株ニュースを確認", row.get("title") or "タイトルなし", "ニュース"))
    for row in sorted(stock_rows, key=lambda item: float(item.get("score") or 0), reverse=True):
        if float(row.get("score") or 0) >= 65:
            target = "保有株" if row.get("is_holding") else "監視銘柄"
            tasks.append(_task(7, f"注目スコア {int(row['score'])}", _stock_label(row), target))
    if rss_failed_count:
        tasks.append(_task(8, "RSS取得失敗を確認", f"{rss_failed_count}件", "ニュース"))
    return sorted(tasks, key=lambda item: item["priority"])[: max(1, min(int(limit), 10))]


def _item(label: str, count: int, page: str, state: str) -> dict[str, Any]:
    return {"label": label, "count": int(count), "page": page, "state": state}


def _task(priority: int, label: str, detail: str, page: str) -> dict[str, Any]:
    return {"priority": priority, "label": label, "detail": detail, "page": page}


def _stock_label(row: dict[str, Any]) -> str:
    return " ".join(part for part in [str(row.get("ticker") or ""), str(row.get("company_name") or "")] if part).strip() or "対象不明"
