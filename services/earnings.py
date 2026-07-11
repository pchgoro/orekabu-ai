"""Manual earnings event management and Japan-time date calculations."""

from __future__ import annotations

import csv
import io
import logging
from datetime import date, datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd

from services.database import _now, connect, get_stock
from utils.constants import DB_PATH, EARNINGS_DATE_STATUSES, EARNINGS_QUARTERS
from utils.validators import normalize_ticker

logger = logging.getLogger(__name__)
JST = ZoneInfo("Asia/Tokyo")
EARNINGS_CSV_COLUMNS = ["ticker", "fiscal_year", "fiscal_quarter", "earnings_date", "announcement_time", "date_status", "memo"]


def japan_today() -> date:
    """Return today's date in Japan."""
    return datetime.now(JST).date()


def parse_earnings_date(value: Any, allow_empty: bool = True) -> date | None:
    """Parse an ISO date and reject invalid values."""
    if value is None or str(value).strip() == "":
        if allow_empty:
            return None
        raise ValueError("決算日を入力してください。")
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value).strip())
    except ValueError as exc:
        raise ValueError("決算日はYYYY-MM-DD形式で入力してください。") from exc


def earnings_date_info(value: Any, today: date | None = None) -> dict[str, Any]:
    """Return normalized day count and user-facing earnings status."""
    event_date = parse_earnings_date(value)
    if event_date is None:
        return {"days_until": None, "days_label": "日付未確認", "earnings_status": "日付未確認"}
    days = (event_date - (today or japan_today())).days
    if days < 0:
        status, label = "発表済み", "発表済み"
    elif days == 0:
        status, label = "本日決算", "今日"
    elif days == 1:
        status, label = "明日決算", "明日"
    elif days <= 3:
        status, label = "直前", f"あと{days}日"
    elif days <= 7:
        status, label = "今週", f"あと{days}日"
    elif days <= 14:
        status, label = "2週間以内", f"あと{days}日"
    elif days <= 30:
        status, label = "1か月以内", f"あと{days}日"
    else:
        status, label = "先予定", "30日超"
    return {"days_until": days, "days_label": label, "earnings_status": status}


def validate_earnings_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Validate a manual earnings event payload."""
    try:
        fiscal_year = int(payload.get("fiscal_year"))
    except (TypeError, ValueError) as exc:
        raise ValueError("対象年度は西暦で入力してください。") from exc
    if fiscal_year < 1900 or fiscal_year > 2200:
        raise ValueError("対象年度は1900～2200で入力してください。")
    quarter = str(payload.get("fiscal_quarter") or "未設定")
    status = str(payload.get("date_status") or "未確認")
    if quarter not in EARNINGS_QUARTERS:
        raise ValueError("四半期が不正です。")
    if status not in EARNINGS_DATE_STATUSES:
        raise ValueError("日付状態が不正です。")
    event_date = parse_earnings_date(payload.get("earnings_date"))
    if status == "未確認":
        event_date = None
    if status != "未確認" and event_date is None:
        raise ValueError("確定または予定の場合は決算日を入力してください。")
    return {
        "stock_id": int(payload.get("stock_id")),
        "fiscal_year": fiscal_year,
        "fiscal_quarter": quarter,
        "earnings_date": event_date.isoformat() if event_date else None,
        "announcement_time": str(payload.get("announcement_time") or "").strip(),
        "date_status": status,
        "memo": str(payload.get("memo") or "").strip(),
    }


def earnings_form_date_value(date_status: str, value: Any) -> date | None:
    """Return a safe date_input value without filling unknown dates."""
    if date_status == "未確認":
        return None
    return parse_earnings_date(value)


def list_earnings(db_path: Path | str = DB_PATH, start_date: date | None = None, end_date: date | None = None) -> list[dict[str, Any]]:
    """List earnings events with stock metadata and optional date range."""
    clauses, params = [], []
    if start_date:
        clauses.append("e.earnings_date >= ?")
        params.append(start_date.isoformat())
    if end_date:
        clauses.append("e.earnings_date <= ?")
        params.append(end_date.isoformat())
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    with connect(db_path) as conn:
        rows = conn.execute(
            f"""SELECT e.*, s.ticker, s.company_name, s.category, s.is_holding
                FROM earnings_events e JOIN stocks s ON s.id=e.stock_id
                {where}
                ORDER BY e.earnings_date IS NULL, e.earnings_date, s.ticker""",
            params,
        ).fetchall()
    return [dict(row) for row in rows]


def get_stock_earnings(stock_id: int, db_path: Path | str = DB_PATH) -> list[dict[str, Any]]:
    """Return all earnings events for one stock."""
    return [row for row in list_earnings(db_path) if int(row["stock_id"]) == int(stock_id)]


def get_earnings(event_id: int, db_path: Path | str = DB_PATH) -> dict[str, Any] | None:
    """Return one earnings event."""
    with connect(db_path) as conn:
        row = conn.execute("SELECT * FROM earnings_events WHERE id=?", (event_id,)).fetchone()
    return dict(row) if row else None


def add_earnings(payload: dict[str, Any], db_path: Path | str = DB_PATH) -> int:
    """Insert a validated earnings event."""
    item = validate_earnings_payload(payload)
    now = _now()
    with connect(db_path) as conn:
        cursor = conn.execute(
            """INSERT INTO earnings_events
               (stock_id,fiscal_year,fiscal_quarter,earnings_date,announcement_time,date_status,memo,created_at,updated_at)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (*item.values(), now, now),
        )
        return int(cursor.lastrowid)


def update_earnings(event_id: int, payload: dict[str, Any], db_path: Path | str = DB_PATH) -> None:
    """Update an existing earnings event."""
    item = validate_earnings_payload(payload)
    with connect(db_path) as conn:
        cursor = conn.execute(
            """UPDATE earnings_events SET stock_id=?,fiscal_year=?,fiscal_quarter=?,earnings_date=?,
               announcement_time=?,date_status=?,memo=?,updated_at=? WHERE id=?""",
            (*item.values(), _now(), event_id),
        )
        if cursor.rowcount == 0:
            raise ValueError("更新対象の決算イベントが見つかりません。")


def delete_earnings(event_id: int, db_path: Path | str = DB_PATH) -> None:
    """Delete an earnings event and report missing ids."""
    with connect(db_path) as conn:
        cursor = conn.execute("DELETE FROM earnings_events WHERE id=?", (event_id,))
        if cursor.rowcount == 0:
            raise ValueError("削除対象の決算イベントが見つかりません。")


def upsert_earnings(payload: dict[str, Any], update_existing: bool, db_path: Path | str = DB_PATH) -> str:
    """Insert, update, or skip by stock/year/quarter identity."""
    item = validate_earnings_payload(payload)
    with connect(db_path) as conn:
        row = conn.execute(
            "SELECT id FROM earnings_events WHERE stock_id=? AND fiscal_year=? AND fiscal_quarter=?",
            (item["stock_id"], item["fiscal_year"], item["fiscal_quarter"]),
        ).fetchone()
    if row:
        if not update_existing:
            return "skipped"
        update_earnings(int(row["id"]), item, db_path)
        return "updated"
    add_earnings(item, db_path)
    return "inserted"


def next_earnings_by_stock(db_path: Path | str = DB_PATH, today: date | None = None) -> dict[int, dict[str, Any]]:
    """Return the next dated event, or an undated event, for every stock."""
    today = today or japan_today()
    result: dict[int, dict[str, Any]] = {}
    for row in list_earnings(db_path):
        stock_id = int(row["stock_id"])
        event_date = parse_earnings_date(row.get("earnings_date"))
        if event_date is not None and event_date < today:
            continue
        current = result.get(stock_id)
        if current is None or (current.get("earnings_date") is None and event_date is not None):
            result[stock_id] = row
    return result


def export_earnings_csv(events: list[dict[str, Any]]) -> bytes:
    """Export manual earnings events as UTF-8 BOM CSV."""
    data = [{col: row.get(col, "") or "" for col in EARNINGS_CSV_COLUMNS} for row in events]
    return pd.DataFrame(data, columns=EARNINGS_CSV_COLUMNS).to_csv(index=False).encode("utf-8-sig")


def parse_earnings_csv(uploaded_file: Any) -> tuple[pd.DataFrame, list[str]]:
    """Parse an earnings CSV for preview."""
    try:
        rows = list(csv.DictReader(io.StringIO(uploaded_file.getvalue().decode("utf-8-sig"))))
        frame = pd.DataFrame(rows)
        missing = [col for col in EARNINGS_CSV_COLUMNS if col not in frame.columns]
        return (frame, [f"CSV列が不足しています: {', '.join(missing)}"]) if missing else (frame[EARNINGS_CSV_COLUMNS], [])
    except Exception as exc:
        logger.exception("決算CSV読み込みエラー")
        return pd.DataFrame(), [f"決算CSVを読み込めませんでした: {exc}"]


def import_earnings_csv(frame: pd.DataFrame, update_existing: bool, db_path: Path | str = DB_PATH) -> dict[str, Any]:
    """Import earnings rows independently so one bad row does not abort others."""
    result: dict[str, Any] = {"inserted": 0, "updated": 0, "skipped": 0, "failed": 0, "errors": []}
    for index, row in frame.iterrows():
        try:
            stock = get_stock(normalize_ticker(row.get("ticker")), db_path)
            if stock is None:
                raise ValueError("登録銘柄に存在しないtickerです。")
            status = upsert_earnings({**row.to_dict(), "stock_id": stock["id"]}, update_existing, db_path)
            result[status] += 1
        except Exception as exc:
            result["failed"] += 1
            result["errors"].append(f"{int(index)+2}行目: {exc}")
            logger.exception("決算CSV行エラー line=%s ticker=%s", int(index)+2, row.get("ticker"))
    return result
