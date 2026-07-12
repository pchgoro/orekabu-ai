"""Compare external earnings candidates with protected manual events."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

from services.earnings import japan_today, parse_earnings_date


@dataclass(frozen=True)
class ReconciliationResult:
    """Comparison outcome and the event selected for review."""

    comparison_status: str
    matched_event_id: int | None = None
    warning: str = ""


def reconcile_candidate(
    candidate_date: date | None,
    fiscal_year: int | None,
    fiscal_quarter: str,
    announcement_time: str,
    existing_events: list[dict[str, Any]],
    min_date_difference_days: int = 1,
) -> ReconciliationResult:
    """Classify a candidate without mutating any formal event."""
    if candidate_date is None:
        return ReconciliationResult("invalid", warning="候補日がありません。")
    if candidate_date < japan_today():
        return ReconciliationResult("past_date", warning="候補日は過去日です。")

    future_or_unknown = [
        event for event in existing_events
        if (parsed := parse_earnings_date(event.get("earnings_date"))) is None or parsed >= japan_today()
    ]
    if not future_or_unknown:
        return ReconciliationResult("new")

    plausible = [event for event in future_or_unknown if _is_plausible(event, fiscal_year, fiscal_quarter, candidate_date)]
    if not plausible:
        return ReconciliationResult("new")
    if len(plausible) > 1:
        return ReconciliationResult("conflict", warning="複数の既存決算と一致する可能性があります。")

    event = plausible[0]
    event_id = int(event["id"])
    current_date = parse_earnings_date(event.get("earnings_date"))
    current_quarter = event.get("fiscal_quarter") or "未設定"
    current_time = str(event.get("announcement_time") or "").strip()
    candidate_time = str(announcement_time or "").strip()

    if current_date is None:
        return ReconciliationResult("new", event_id, "日付未確認の既存イベントがあります。")
    date_difference = abs((candidate_date - current_date).days)
    quarter_differs = fiscal_quarter not in ("", "未設定") and current_quarter != fiscal_quarter
    time_differs = bool(candidate_time) and current_time != candidate_time
    differs = date_difference >= max(1, min_date_difference_days) or quarter_differs or time_differs
    if event.get("date_status") == "確定" and differs:
        return ReconciliationResult("conflict", event_id, "既存の確定データと差異があります。")
    if date_difference >= max(1, min_date_difference_days):
        return ReconciliationResult("date_changed", event_id)
    if quarter_differs:
        return ReconciliationResult("quarter_changed", event_id)
    if time_differs:
        return ReconciliationResult("time_changed", event_id)
    return ReconciliationResult("same", event_id)


def candidate_diff(candidate: dict[str, Any]) -> list[dict[str, str]]:
    """Build text-based before/after rows for review UI."""
    fields = [
        ("決算日", "existing_date", "candidate_date"),
        ("発表時間", "existing_time", "announcement_time"),
        ("四半期", "existing_quarter", "fiscal_quarter"),
        ("日付ステータス", "existing_date_status", None),
    ]
    rows = []
    for label, old_key, new_key in fields:
        old = candidate.get(old_key) or "情報なし"
        new = "外部候補" if new_key is None else (candidate.get(new_key) or "情報なし")
        state = "変更なし" if old == new else ("情報なし" if old == "情報なし" or new == "情報なし" else "変更あり")
        rows.append({"項目": label, "現在": str(old), "候補": str(new), "差分": state})
    rows.append({"項目": "取得元", "現在": "手動", "候補": str(candidate.get("provider_name") or "情報なし"), "差分": "情報"})
    return rows


def _is_plausible(event: dict[str, Any], fiscal_year: int | None, quarter: str, candidate_date: date) -> bool:
    event_year = event.get("fiscal_year")
    year_matches = fiscal_year is None or event_year is None or abs(int(event_year) - int(fiscal_year)) <= 1
    event_quarter = event.get("fiscal_quarter") or "未設定"
    quarter_matches = quarter in ("", "未設定") or event_quarter in ("未設定", quarter)
    event_date = parse_earnings_date(event.get("earnings_date"))
    date_close = event_date is None or abs((candidate_date - event_date).days) <= 120
    return year_matches and quarter_matches and date_close
