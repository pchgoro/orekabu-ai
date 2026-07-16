"""Tests for non-destructive schema migrations."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from services.database import init_db
from services.migrations import migrate


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
    assert conn.execute("SELECT version FROM schema_version").fetchone()[0] == 6
    assert {"company_alias", "market", "industry"}.issubset({row[1] for row in conn.execute("PRAGMA table_info(stocks)")})
    tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"earnings_events", "stock_relations", "earnings_candidates", "earnings_fetch_runs", "earnings_fetch_results", "news_sources", "news_articles", "news_article_stocks", "stock_news_keywords", "news_tags", "news_article_tags", "news_fetch_runs", "news_fetch_results", "disclosures", "disclosure_tags", "disclosure_tag_links", "disclosure_news_links", "disclosure_import_runs", "disclosure_import_results"}.issubset(tables)
    conn.close()


def test_schema_version_2_migrates_to_latest_without_data_loss(tmp_path: Path) -> None:
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
    assert conn.execute("SELECT version FROM schema_version").fetchone()[0] == 6
    assert conn.execute("SELECT COUNT(*) FROM stocks").fetchone()[0] == before
    assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    conn.close()


def test_schema_version_3_migrates_to_4_idempotently(tmp_path: Path) -> None:
    db = tmp_path / "v3.db"
    init_db(db)
    conn = sqlite3.connect(db)
    news_tables = ["news_fetch_results", "news_fetch_runs", "news_article_tags", "news_tags", "stock_news_keywords", "news_article_stocks", "news_articles", "news_sources"]
    conn.execute("PRAGMA foreign_keys=OFF")
    for table in news_tables:
        conn.execute(f"DROP TABLE {table}")
    conn.execute("UPDATE schema_version SET version=3")
    before = conn.execute("SELECT ticker,company_name FROM stocks ORDER BY id").fetchall()
    conn.commit(); conn.close()
    init_db(db); init_db(db)
    conn = sqlite3.connect(db)
    assert conn.execute("SELECT version FROM schema_version").fetchone()[0] == 6
    assert conn.execute("SELECT ticker,company_name FROM stocks ORDER BY id").fetchall() == before
    assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    conn.close()


def test_schema_version_4_migrates_to_5_idempotently(tmp_path: Path) -> None:
    db = tmp_path / "v4.db"
    init_db(db)
    conn = sqlite3.connect(db)
    disclosure_tables = ["disclosure_import_results", "disclosure_import_runs", "disclosure_news_links", "disclosure_tag_links", "disclosure_tags", "disclosures"]
    conn.execute("PRAGMA foreign_keys=OFF")
    for table in disclosure_tables:
        conn.execute(f"DROP TABLE {table}")
    conn.execute("UPDATE schema_version SET version=4")
    before = conn.execute("SELECT ticker,company_name FROM stocks ORDER BY id").fetchall()
    conn.commit(); conn.close()
    init_db(db); init_db(db)
    conn = sqlite3.connect(db)
    assert conn.execute("SELECT version FROM schema_version").fetchone()[0] == 6
    assert conn.execute("SELECT ticker,company_name FROM stocks ORDER BY id").fetchall() == before
    assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    conn.close()


def test_schema_version_5_migrates_to_6_idempotently(tmp_path: Path) -> None:
    db = tmp_path / "v5.db"
    init_db(db)
    conn = sqlite3.connect(db)
    conn.execute("UPDATE stocks SET company_name='保持対象' WHERE id=(SELECT MIN(id) FROM stocks)")
    conn.execute("UPDATE schema_version SET version=5")
    conn.commit(); conn.close()
    init_db(db); init_db(db)
    conn = sqlite3.connect(db)
    assert conn.execute("SELECT version FROM schema_version").fetchone()[0] == 6
    columns = {row[1] for row in conn.execute("PRAGMA table_info(stocks)")}
    assert {"company_alias", "market", "industry"}.issubset(columns)
    assert conn.execute("SELECT COUNT(*) FROM stocks WHERE company_name='保持対象'").fetchone()[0] == 1
    assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    conn.close()


def test_future_schema_is_rejected_without_repair_writes(tmp_path: Path) -> None:
    db = tmp_path / "future.db"
    init_db(db)
    with sqlite3.connect(db) as conn:
        conn.execute("DROP TABLE disclosure_import_results")
        conn.execute("UPDATE schema_version SET version=7")
    with sqlite3.connect(db) as conn:
        with pytest.raises(RuntimeError, match="未対応のDBバージョン"):
            migrate(conn)
    with sqlite3.connect(db) as conn:
        assert conn.execute("SELECT version FROM schema_version").fetchone()[0] == 7
        assert conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='disclosure_import_results'").fetchone() is None
