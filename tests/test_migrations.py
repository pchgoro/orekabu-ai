"""Tests for non-destructive schema migrations."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from services.database import init_db


def test_existing_phase1_db_migrates_idempotently(tmp_path: Path) -> None:
    db = tmp_path / "old.db"
    conn = sqlite3.connect(db)
    conn.executescript("""
        CREATE TABLE stocks (id INTEGER PRIMARY KEY AUTOINCREMENT, ticker TEXT NOT NULL UNIQUE,
        company_name TEXT NOT NULL, category TEXT NOT NULL, is_holding INTEGER NOT NULL DEFAULT 0,
        shares INTEGER NOT NULL DEFAULT 0, average_price REAL NOT NULL DEFAULT 0,
        buy_watch_price REAL NOT NULL DEFAULT 0, memo TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
        CREATE TABLE app_settings (key TEXT PRIMARY KEY, value TEXT NOT NULL, updated_at TEXT NOT NULL);
        INSERT INTO stocks VALUES (1,'7203.T','トヨタ','監視銘柄',0,0,0,0,'','2026-01-01','2026-01-01');
    """)
    conn.commit(); conn.close()
    init_db(db); init_db(db)
    conn = sqlite3.connect(db)
    assert conn.execute("SELECT ticker FROM stocks").fetchone()[0] == "7203.T"
    assert conn.execute("SELECT version FROM schema_version").fetchone()[0] == 3
    tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"earnings_events", "stock_relations", "earnings_candidates", "earnings_fetch_runs", "earnings_fetch_results"}.issubset(tables)
    conn.close()


def test_schema_version_2_migrates_to_3_without_data_loss(tmp_path: Path) -> None:
    db = tmp_path / "v2.db"
    init_db(db)
    conn = sqlite3.connect(db)
    conn.execute("UPDATE schema_version SET version=2")
    conn.execute("DROP TABLE earnings_fetch_results")
    conn.execute("DROP TABLE earnings_fetch_runs")
    conn.execute("DROP TABLE earnings_candidates")
    before = conn.execute("SELECT COUNT(*) FROM stocks").fetchone()[0]
    conn.commit(); conn.close()
    init_db(db); init_db(db)
    conn = sqlite3.connect(db)
    assert conn.execute("SELECT version FROM schema_version").fetchone()[0] == 3
    assert conn.execute("SELECT COUNT(*) FROM stocks").fetchone()[0] == before
    assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    conn.close()
