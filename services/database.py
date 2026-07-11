"""SQLite access layer for オレ株AI."""

from __future__ import annotations

import json
import logging
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator

from services.settings import default_settings, merge_settings
from services.migrations import migrate
from utils.constants import DB_PATH, SAMPLE_STOCKS
from utils.validators import validate_stock_payload

logger = logging.getLogger(__name__)


@contextmanager
def connect(db_path: Path | str = DB_PATH) -> Iterator[sqlite3.Connection]:
    """Open a SQLite connection with row dictionaries enabled."""
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        logger.exception("SQLite処理でエラーが発生しました")
        raise
    finally:
        conn.close()


def init_db(db_path: Path | str = DB_PATH) -> None:
    """Initialize tables and seed sample stocks when the DB is empty."""
    with connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS stocks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ticker TEXT NOT NULL UNIQUE,
                company_name TEXT NOT NULL,
                category TEXT NOT NULL,
                is_holding INTEGER NOT NULL DEFAULT 0,
                shares INTEGER NOT NULL DEFAULT 0,
                average_price REAL NOT NULL DEFAULT 0,
                buy_watch_price REAL NOT NULL DEFAULT 0,
                memo TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        migrate(conn)
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS app_settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        count = conn.execute("SELECT COUNT(*) FROM stocks").fetchone()[0]
        if count == 0:
            now = _now()
            for stock in SAMPLE_STOCKS:
                payload = validate_stock_payload({**stock, "is_holding": False, "shares": 0, "average_price": 0, "buy_watch_price": 0, "memo": ""})
                conn.execute(
                    """
                    INSERT OR IGNORE INTO stocks
                    (ticker, company_name, category, is_holding, shares, average_price, buy_watch_price, memo, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        payload["ticker"],
                        payload["company_name"],
                        payload["category"],
                        int(payload["is_holding"]),
                        payload["shares"],
                        payload["average_price"],
                        payload["buy_watch_price"],
                        payload["memo"],
                        now,
                        now,
                    ),
                )
        setting_count = conn.execute("SELECT COUNT(*) FROM app_settings WHERE key='settings'").fetchone()[0]
        if setting_count == 0:
            conn.execute(
                "INSERT INTO app_settings (key, value, updated_at) VALUES (?, ?, ?)",
                ("settings", json.dumps(default_settings(), ensure_ascii=False), _now()),
            )


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def get_stocks(db_path: Path | str = DB_PATH) -> list[dict[str, Any]]:
    """Return all registered stocks."""
    with connect(db_path) as conn:
        rows = conn.execute("SELECT * FROM stocks ORDER BY ticker").fetchall()
    return [dict(row) for row in rows]


def get_stock(ticker: str, db_path: Path | str = DB_PATH) -> dict[str, Any] | None:
    """Return one stock by ticker."""
    with connect(db_path) as conn:
        row = conn.execute("SELECT * FROM stocks WHERE ticker = ?", (ticker,)).fetchone()
    return dict(row) if row else None


def add_stock(payload: dict[str, Any], db_path: Path | str = DB_PATH) -> int:
    """Insert a stock after validation."""
    stock = validate_stock_payload(payload)
    now = _now()
    with connect(db_path) as conn:
        cursor = conn.execute(
            """
            INSERT INTO stocks
            (ticker, company_name, category, is_holding, shares, average_price, buy_watch_price, memo, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                stock["ticker"],
                stock["company_name"],
                stock["category"],
                int(stock["is_holding"]),
                stock["shares"],
                stock["average_price"],
                stock["buy_watch_price"],
                stock["memo"],
                now,
                now,
            ),
        )
        return int(cursor.lastrowid)


def update_stock(stock_id: int, payload: dict[str, Any], db_path: Path | str = DB_PATH) -> None:
    """Update a stock by id."""
    stock = validate_stock_payload(payload)
    with connect(db_path) as conn:
        conn.execute(
            """
            UPDATE stocks
            SET ticker=?, company_name=?, category=?, is_holding=?, shares=?, average_price=?,
                buy_watch_price=?, memo=?, updated_at=?
            WHERE id=?
            """,
            (
                stock["ticker"],
                stock["company_name"],
                stock["category"],
                int(stock["is_holding"]),
                stock["shares"],
                stock["average_price"],
                stock["buy_watch_price"],
                stock["memo"],
                _now(),
                stock_id,
            ),
        )


def upsert_stock(payload: dict[str, Any], update_existing: bool, db_path: Path | str = DB_PATH) -> str:
    """Insert or optionally update an existing stock. Returns inserted/updated/skipped."""
    stock = validate_stock_payload(payload)
    existing = get_stock(stock["ticker"], db_path=db_path)
    if existing:
        if not update_existing:
            return "skipped"
        update_stock(int(existing["id"]), stock, db_path=db_path)
        return "updated"
    add_stock(stock, db_path=db_path)
    return "inserted"


def delete_stock(stock_id: int, db_path: Path | str = DB_PATH) -> None:
    """Delete a stock by id."""
    with connect(db_path) as conn:
        conn.execute("DELETE FROM stocks WHERE id=?", (stock_id,))


def set_setting(key: str, value: Any, db_path: Path | str = DB_PATH) -> None:
    """Persist a JSON setting value."""
    with connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO app_settings (key, value, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at
            """,
            (key, json.dumps(value, ensure_ascii=False), _now()),
        )


def get_setting(key: str, default: Any = None, db_path: Path | str = DB_PATH) -> Any:
    """Load and decode a setting value."""
    with connect(db_path) as conn:
        row = conn.execute("SELECT value FROM app_settings WHERE key=?", (key,)).fetchone()
    if row is None:
        return default
    try:
        return json.loads(row["value"])
    except json.JSONDecodeError:
        return row["value"]


def load_settings(db_path: Path | str = DB_PATH) -> dict[str, Any]:
    """Load merged app settings."""
    return merge_settings(get_setting("settings", {}, db_path=db_path))


def save_settings(settings: dict[str, Any], db_path: Path | str = DB_PATH) -> None:
    """Validate and save settings."""
    set_setting("settings", merge_settings(settings), db_path=db_path)
