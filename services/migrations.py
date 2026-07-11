"""Idempotent SQLite schema migrations."""

from __future__ import annotations

import logging
import sqlite3

logger = logging.getLogger(__name__)
LATEST_SCHEMA_VERSION = 2


def migrate(conn: sqlite3.Connection) -> None:
    """Apply all pending migrations without rebuilding existing tables."""
    try:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS schema_version (version INTEGER NOT NULL)"
        )
        row = conn.execute("SELECT version FROM schema_version LIMIT 1").fetchone()
        if row is None:
            conn.execute("INSERT INTO schema_version (version) VALUES (1)")
            version = 1
        else:
            version = int(row[0])

        if version < 2:
            _migrate_to_v2(conn)
            conn.execute("UPDATE schema_version SET version = 2")
            version = 2

        # CREATE IF NOT EXISTS also repairs a partially created v2 migration.
        _migrate_to_v2(conn)
        if version != LATEST_SCHEMA_VERSION:
            raise RuntimeError(f"未対応のDBバージョンです: {version}")
    except Exception:
        logger.exception("DBマイグレーション失敗 target_version=%s", LATEST_SCHEMA_VERSION)
        raise


def _migrate_to_v2(conn: sqlite3.Connection) -> None:
    """Add manual earnings and directed stock relations."""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS earnings_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            stock_id INTEGER NOT NULL,
            fiscal_year INTEGER NOT NULL,
            fiscal_quarter TEXT NOT NULL,
            earnings_date TEXT,
            announcement_time TEXT NOT NULL DEFAULT '',
            date_status TEXT NOT NULL,
            memo TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(stock_id, fiscal_year, fiscal_quarter),
            FOREIGN KEY(stock_id) REFERENCES stocks(id) ON DELETE CASCADE
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS stock_relations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_stock_id INTEGER NOT NULL,
            related_stock_id INTEGER NOT NULL,
            relation_type TEXT NOT NULL,
            impact_level TEXT NOT NULL,
            memo TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(source_stock_id, related_stock_id),
            CHECK(source_stock_id <> related_stock_id),
            FOREIGN KEY(source_stock_id) REFERENCES stocks(id) ON DELETE CASCADE,
            FOREIGN KEY(related_stock_id) REFERENCES stocks(id) ON DELETE CASCADE
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_earnings_date ON earnings_events(earnings_date)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_relations_source ON stock_relations(source_stock_id)")
