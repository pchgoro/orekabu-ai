"""Idempotent SQLite schema migrations."""

from __future__ import annotations

import logging
import sqlite3

logger = logging.getLogger(__name__)
LATEST_SCHEMA_VERSION = 3


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

        if version < 3:
            _migrate_to_v3(conn)
            conn.execute("UPDATE schema_version SET version = 3")
            version = 3

        # CREATE IF NOT EXISTS also repairs a partially created v2 migration.
        _migrate_to_v2(conn)
        _migrate_to_v3(conn)
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


def _migrate_to_v3(conn: sqlite3.Connection) -> None:
    """Add reviewable earnings candidates and fetch audit history."""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS earnings_candidates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            stock_id INTEGER NOT NULL,
            provider_name TEXT NOT NULL,
            source_reference TEXT NOT NULL DEFAULT '',
            candidate_date TEXT,
            announcement_time TEXT NOT NULL DEFAULT '',
            fiscal_year INTEGER,
            fiscal_quarter TEXT NOT NULL DEFAULT '未設定',
            confidence TEXT NOT NULL DEFAULT 'unknown',
            comparison_status TEXT NOT NULL,
            review_status TEXT NOT NULL DEFAULT 'pending',
            matched_earnings_event_id INTEGER,
            retrieved_at TEXT NOT NULL,
            reviewed_at TEXT,
            review_note TEXT NOT NULL DEFAULT '',
            raw_payload_summary TEXT NOT NULL DEFAULT '',
            fingerprint TEXT NOT NULL UNIQUE,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY(stock_id) REFERENCES stocks(id) ON DELETE CASCADE,
            FOREIGN KEY(matched_earnings_event_id) REFERENCES earnings_events(id) ON DELETE SET NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS earnings_fetch_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            provider_name TEXT NOT NULL,
            started_at TEXT NOT NULL,
            finished_at TEXT,
            target_count INTEGER NOT NULL DEFAULT 0,
            success_count INTEGER NOT NULL DEFAULT 0,
            candidate_count INTEGER NOT NULL DEFAULT 0,
            unchanged_count INTEGER NOT NULL DEFAULT 0,
            failed_count INTEGER NOT NULL DEFAULT 0,
            status TEXT NOT NULL,
            error_summary TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS earnings_fetch_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fetch_run_id INTEGER NOT NULL,
            stock_id INTEGER NOT NULL,
            ticker TEXT NOT NULL,
            status TEXT NOT NULL,
            candidate_id INTEGER,
            error_code TEXT NOT NULL DEFAULT '',
            error_message TEXT NOT NULL DEFAULT '',
            retrieved_at TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY(fetch_run_id) REFERENCES earnings_fetch_runs(id) ON DELETE CASCADE,
            FOREIGN KEY(stock_id) REFERENCES stocks(id) ON DELETE CASCADE,
            FOREIGN KEY(candidate_id) REFERENCES earnings_candidates(id) ON DELETE SET NULL
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_candidates_review ON earnings_candidates(review_status, comparison_status)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_candidates_stock ON earnings_candidates(stock_id, candidate_date)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_fetch_results_run ON earnings_fetch_results(fetch_run_id)")
