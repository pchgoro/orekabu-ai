"""Official IR source persistence and low-frequency fetch state."""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from services.database import _now, connect
from services.disclosures import validate_web_url
from utils.constants import DB_PATH, IR_SOURCE_TYPES

AUTO_IR_SOURCE_TYPES = {"official_ir_calendar", "official_ir_news"}
JPX_COMPANY_SEARCH_URL = (
    "https://www2.jpx.co.jp/tseHpFront/JJK010010Action.do?Show=Show"
)


def save_ir_source(
    payload: dict[str, Any],
    db_path: Path | str = DB_PATH,
) -> int:
    """Insert or update one source type for a registered stock."""
    stock_id = int(payload.get("stock_id") or 0)
    source_type = str(payload.get("source_type") or "")
    if source_type not in IR_SOURCE_TYPES:
        raise ValueError("IR取得元の種類が不正です。")
    source_url = validate_web_url(payload.get("source_url"), allow_empty=False)
    enabled = int(bool(payload.get("enabled", True)))
    now = _now()
    with connect(db_path) as conn:
        stock = conn.execute("SELECT id FROM stocks WHERE id=?", (stock_id,)).fetchone()
        if stock is None:
            raise ValueError("登録済みの銘柄を指定してください。")
        conn.execute(
            """INSERT INTO stock_ir_sources
            (stock_id,source_type,source_url,enabled,created_at,updated_at)
            VALUES (?,?,?,?,?,?)
            ON CONFLICT(stock_id,source_type) DO UPDATE SET
                source_url=excluded.source_url,
                enabled=excluded.enabled,
                last_checked_at=NULL,
                last_success_at=NULL,
                last_error='',
                updated_at=excluded.updated_at""",
            (stock_id, source_type, source_url, enabled, now, now),
        )
        row = conn.execute(
            "SELECT id FROM stock_ir_sources WHERE stock_id=? AND source_type=?",
            (stock_id, source_type),
        ).fetchone()
    return int(row["id"])


def delete_ir_source(source_id: int, db_path: Path | str = DB_PATH) -> None:
    """Delete one IR source without touching candidates or formal earnings."""
    with connect(db_path) as conn:
        cursor = conn.execute("DELETE FROM stock_ir_sources WHERE id=?", (source_id,))
        if cursor.rowcount != 1:
            raise ValueError("IR取得元が見つかりません。")


def list_ir_sources(db_path: Path | str = DB_PATH) -> list[dict[str, Any]]:
    """List IR sources joined to their registered stocks."""
    with connect(db_path) as conn:
        rows = conn.execute(
            """SELECT i.*,s.ticker,s.company_name,s.is_holding
            FROM stock_ir_sources i
            JOIN stocks s ON s.id=i.stock_id
            ORDER BY s.is_holding DESC,s.ticker,i.source_type"""
        ).fetchall()
    return [dict(row) for row in rows]


def get_ir_source_for_ticker(
    ticker: str,
    db_path: Path | str = DB_PATH,
) -> dict[str, Any] | None:
    """Return the preferred enabled automatic source for one ticker."""
    with connect(db_path) as conn:
        row = conn.execute(
            """SELECT i.*,s.ticker,s.company_name
            FROM stock_ir_sources i
            JOIN stocks s ON s.id=i.stock_id
            WHERE s.ticker=? AND i.enabled=1
              AND i.source_type IN ('official_ir_calendar','official_ir_news')
            ORDER BY CASE i.source_type WHEN 'official_ir_calendar' THEN 0 ELSE 1 END,
                     i.id
            LIMIT 1""",
            (ticker,),
        ).fetchone()
    return dict(row) if row else None


def get_ir_source(source_id: int, db_path: Path | str = DB_PATH) -> dict[str, Any] | None:
    """Return one joined IR source."""
    return next(
        (row for row in list_ir_sources(db_path) if int(row["id"]) == int(source_id)),
        None,
    )


def source_is_due(
    source: dict[str, Any],
    cache_hours: int = 24,
    *,
    force: bool = False,
) -> bool:
    """Return whether a source may be checked without excessive access."""
    if force:
        return True
    last_checked = source.get("last_checked_at")
    if not last_checked:
        return True
    try:
        checked = datetime.fromisoformat(str(last_checked))
    except ValueError:
        return True
    threshold = datetime.now().astimezone() - timedelta(hours=max(24, cache_hours))
    if checked.tzinfo is None:
        checked = checked.astimezone()
    return checked < threshold


def record_ir_source_result(
    source_id: int,
    *,
    success: bool,
    error: str = "",
    db_path: Path | str = DB_PATH,
) -> None:
    """Persist only timestamps and a short error, never HTML content."""
    now = _now()
    with connect(db_path) as conn:
        cursor = conn.execute(
            """UPDATE stock_ir_sources
            SET last_checked_at=?,
                last_success_at=CASE WHEN ? THEN ? ELSE last_success_at END,
                last_error=?,
                updated_at=?
            WHERE id=?""",
            (now, int(success), now, "" if success else error[:1000], now, source_id),
        )
        if cursor.rowcount != 1:
            raise ValueError("IR取得元が見つかりません。")


def latest_official_candidate(
    stock_id: int,
    db_path: Path | str = DB_PATH,
) -> dict[str, Any] | None:
    """Return the newest future official-IR candidate for cache reuse."""
    with connect(db_path) as conn:
        row = conn.execute(
            """SELECT * FROM earnings_candidates
            WHERE stock_id=? AND provider_name='official_ir'
              AND candidate_date>=date('now','localtime')
            ORDER BY candidate_date,retrieved_at DESC LIMIT 1""",
            (stock_id,),
        ).fetchone()
    return dict(row) if row else None


def ir_source_status_rows(db_path: Path | str = DB_PATH) -> list[dict[str, Any]]:
    """Return holding-focused status rows for the IR source UI."""
    with connect(db_path) as conn:
        rows = conn.execute(
            """SELECT s.id stock_id,s.ticker,s.company_name,s.is_holding,
                   i.id source_id,i.source_type,i.source_url,i.enabled,
                   i.last_checked_at,i.last_success_at,i.last_error,
                   (
                     SELECT r.status FROM earnings_fetch_results r
                     WHERE r.stock_id=s.id ORDER BY r.id DESC LIMIT 1
                   ) latest_fetch_status,
                   (
                     SELECT r.error_code FROM earnings_fetch_results r
                     WHERE r.stock_id=s.id ORDER BY r.id DESC LIMIT 1
                   ) latest_error_code
            FROM stocks s
            LEFT JOIN stock_ir_sources i
              ON i.id=(
                SELECT i2.id FROM stock_ir_sources i2
                WHERE i2.stock_id=s.id
                  AND i2.source_type IN ('official_ir_calendar','official_ir_news')
                ORDER BY CASE i2.source_type
                    WHEN 'official_ir_calendar' THEN 0 ELSE 1 END,
                    i2.id
                LIMIT 1
              )
            WHERE s.is_holding=1
            ORDER BY s.ticker"""
        ).fetchall()
    return [dict(row) for row in rows]


def fetch_ir_source_candidate(
    source_id: int,
    settings: dict[str, Any],
    db_path: Path | str = DB_PATH,
) -> dict[str, Any]:
    """Force one official source check and save only review candidates."""
    from services.database import get_stock
    from services.earnings_candidates import save_candidate
    from services.earnings_providers.official_ir_provider import (
        OfficialIREarningsProvider,
    )

    source = get_ir_source(source_id, db_path)
    if source is None:
        raise ValueError("IR取得元が見つかりません。")
    if source["source_type"] not in AUTO_IR_SOURCE_TYPES:
        raise ValueError("この取得元は自動取得対象ではありません。")
    result = OfficialIREarningsProvider(source).fetch_next_earnings(source["ticker"])
    record_ir_source_result(
        source_id,
        success=result.succeeded,
        error="" if result.succeeded else result.error_message,
        db_path=db_path,
    )
    if not result.succeeded:
        return {
            "success": False,
            "created": 0,
            "duplicates": 0,
            "error_code": result.error_code,
            "message": result.error_message,
        }
    stock = get_stock(source["ticker"], db_path)
    if stock is None:
        raise ValueError("登録銘柄が見つかりません。")
    auto = settings.get("earnings_auto_fetch", settings)
    created = duplicates = 0
    for candidate_date in result.candidate_dates or (result.earnings_date,):
        status, _, _ = save_candidate(
            stock,
            result,
            candidate_date,
            int(auto.get("date_change_min_days", 1)),
            bool(auto.get("save_same_candidates", False)),
            bool(auto.get("include_confirmed_events", True)),
            db_path,
        )
        created += status == "created"
        duplicates += status in {"duplicate", "unchanged"}
    return {
        "success": True,
        "created": created,
        "duplicates": duplicates,
        "error_code": "",
        "message": "",
    }
