"""Display-ready earnings and relation view models."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

from services.earnings import earnings_date_info, next_earnings_by_stock, parse_earnings_date
from services.relations import impact_candidates
from utils.constants import DB_PATH

WEEKDAYS = ["月", "火", "水", "木", "金", "土", "日"]


def format_earnings_date(value: Any, missing: str = "未登録") -> str:
    """Format an earnings date without exposing missing values."""
    parsed = parse_earnings_date(value)
    return parsed.strftime("%Y-%m-%d") if parsed else missing


def format_weekday(value: Any) -> str:
    """Return a Japanese weekday label."""
    parsed = parse_earnings_date(value)
    return f"{WEEKDAYS[parsed.weekday()]}曜日" if parsed else "データなし"


def prepare_earnings_rows(events: list[dict[str, Any]], today: date | None = None, near_days: int = 7) -> list[dict[str, Any]]:
    """Add date labels and stable missing-value display fields."""
    rows = []
    for event in events:
        info = earnings_date_info(event.get("earnings_date"), today)
        days = info["days_until"]
        near_label = "日付未確認" if days is None else ("発表済み" if days < 0 else ("接近" if days <= near_days else "通常"))
        rows.append(
            {
                **event,
                **info,
                "earnings_date_display": format_earnings_date(event.get("earnings_date"), "日付未確認"),
                "weekday": format_weekday(event.get("earnings_date")),
                "announcement_time_display": event.get("announcement_time") or "未定",
                "memo_display": event.get("memo") or "",
                "near_label": near_label,
                "holding_label": "保有" if event.get("is_holding") else (event.get("category") or "監視"),
            }
        )
    return rows


def enrich_stock_rows(rows: list[dict[str, Any]], db_path: Path | str = DB_PATH, today: date | None = None, near_days: int = 7) -> list[dict[str, Any]]:
    """Attach each stock's next earnings and related earnings summary."""
    next_map = next_earnings_by_stock(db_path, today)
    impacts_by_source: dict[int, list[dict[str, Any]]] = {}
    for impact in impact_candidates(db_path):
        impacts_by_source.setdefault(int(impact["source_stock_id"]), []).append(impact)
    result = []
    for row in rows:
        event = next_map.get(int(row["id"]))
        info = earnings_date_info(event.get("earnings_date") if event else None, today)
        related = impacts_by_source.get(int(row["id"]), [])
        related_text = "、".join(
            f"{item['related_ticker']} {item['related_company_name']} ({item['days_label']})"
            for item in related[:5] if item.get("earnings_date")
        ) or "登録なし"
        result.append(
            {
                **row,
                "next_earnings_date": event.get("earnings_date") if event else None,
                "next_earnings_date_display": format_earnings_date(event.get("earnings_date"), "日付未確認") if event else "未登録",
                "earnings_days_until": info["days_until"],
                "earnings_days_label": info["days_label"] if event else "未登録",
                "earnings_status": info["earnings_status"] if event else "未登録",
                "earnings_near_label": ("接近" if info["days_until"] is not None and 0 <= info["days_until"] <= near_days else "通常") if event else "未登録",
                "earnings_quarter": event.get("fiscal_quarter") if event else "未登録",
                "earnings_date_status": event.get("date_status") if event else "未登録",
                "earnings_announcement_time": (event.get("announcement_time") or "未定") if event else "未登録",
                "earnings_memo": (event.get("memo") or "") if event else "",
                "related_earnings": related_text,
            }
        )
    return result


def sort_earnings_rows(rows: list[dict[str, Any]], label: str) -> list[dict[str, Any]]:
    """Sort prepared earnings rows by a user-facing option."""
    if label == "決算日が遠い順":
        return sorted(rows, key=lambda r: (r.get("earnings_date") is None, r.get("earnings_date") or ""), reverse=True)
    if label == "銘柄コード順":
        return sorted(rows, key=lambda r: r.get("ticker") or "")
    if label == "会社名順":
        return sorted(rows, key=lambda r: r.get("company_name") or "")
    if label == "保有株優先":
        return sorted(rows, key=lambda r: (not bool(r.get("is_holding")), r.get("earnings_date") is None, r.get("earnings_date") or ""))
    if label == "日付未確認優先":
        return sorted(rows, key=lambda r: (r.get("earnings_date") is not None, r.get("earnings_date") or ""))
    return sorted(rows, key=lambda r: (r.get("earnings_date") is None, r.get("earnings_date") or ""))


def earnings_summary(rows: list[dict[str, Any]]) -> dict[str, int]:
    """Count dashboard earnings proximity groups."""
    return {
        "today": len({row.get("stock_id") for row in rows if row.get("days_until") == 0}),
        "within_7": len({row.get("stock_id") for row in rows if row.get("days_until") is not None and 0 <= row["days_until"] <= 7}),
        "within_14": len({row.get("stock_id") for row in rows if row.get("days_until") is not None and 0 <= row["days_until"] <= 14}),
        "unconfirmed": len({row.get("stock_id") for row in rows if row.get("earnings_date") is None}),
    }
