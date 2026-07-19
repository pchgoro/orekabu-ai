"""Tests for non-destructive schema migrations."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from services.database import init_db
from services.migrations import LATEST_SCHEMA_VERSION, migrate


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
    assert conn.execute("SELECT version FROM schema_version").fetchone()[0] == LATEST_SCHEMA_VERSION
    assert {"company_alias", "market", "industry"}.issubset({row[1] for row in conn.execute("PRAGMA table_info(stocks)")})
    tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"earnings_events", "stock_relations", "earnings_candidates", "earnings_fetch_runs", "earnings_fetch_results", "news_sources", "news_articles", "news_article_stocks", "stock_news_keywords", "news_tags", "news_article_tags", "news_fetch_runs", "news_fetch_results", "disclosures", "disclosure_tags", "disclosure_tag_links", "disclosure_news_links", "disclosure_import_runs", "disclosure_import_results", "edinet_documents", "edinet_fetch_runs", "edinet_fetch_results", "stock_profile_candidates", "automation_runs", "automation_run_steps", "stock_ir_sources", "company_intelligence", "company_notes", "investment_playbooks", "strategy_tags", "stock_strategy_tags", "strategy_rule_sets", "stock_trade_rules"}.issubset(tables)
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
    assert conn.execute("SELECT version FROM schema_version").fetchone()[0] == LATEST_SCHEMA_VERSION
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
    assert conn.execute("SELECT version FROM schema_version").fetchone()[0] == LATEST_SCHEMA_VERSION
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
    assert conn.execute("SELECT version FROM schema_version").fetchone()[0] == LATEST_SCHEMA_VERSION
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
    assert conn.execute("SELECT version FROM schema_version").fetchone()[0] == LATEST_SCHEMA_VERSION
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
        conn.execute(
            "UPDATE schema_version SET version=?",
            (LATEST_SCHEMA_VERSION + 1,),
        )
    with sqlite3.connect(db) as conn:
        with pytest.raises(RuntimeError, match="未対応のDBバージョン"):
            migrate(conn)
    with sqlite3.connect(db) as conn:
        assert conn.execute("SELECT version FROM schema_version").fetchone()[0] == LATEST_SCHEMA_VERSION + 1
        assert conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='disclosure_import_results'").fetchone() is None


def test_schema_version_6_migrates_to_7_idempotently(tmp_path: Path) -> None:
    db = tmp_path / "v6.db"
    init_db(db)
    automation_tables = [
        "automation_run_steps",
        "automation_runs",
        "stock_profile_candidates",
        "edinet_fetch_results",
        "edinet_fetch_runs",
        "edinet_documents",
    ]
    with sqlite3.connect(db) as conn:
        conn.execute("PRAGMA foreign_keys=OFF")
        for table in automation_tables:
            conn.execute(f"DROP TABLE {table}")
        conn.execute("UPDATE schema_version SET version=6")
        before = conn.execute("SELECT ticker,company_name FROM stocks ORDER BY id").fetchall()
    init_db(db)
    init_db(db)
    with sqlite3.connect(db) as conn:
        assert conn.execute("SELECT version FROM schema_version").fetchone()[0] == LATEST_SCHEMA_VERSION
        assert conn.execute("SELECT ticker,company_name FROM stocks ORDER BY id").fetchall() == before
        tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert set(automation_tables).issubset(tables)
        assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"


def test_schema_version_7_migrates_to_8_idempotently(tmp_path: Path) -> None:
    db = tmp_path / "v7.db"
    init_db(db)
    with sqlite3.connect(db) as conn:
        conn.execute("DROP TABLE stock_ir_sources")
        conn.execute("UPDATE schema_version SET version=7")
        before = conn.execute(
            "SELECT ticker,company_name FROM stocks ORDER BY id"
        ).fetchall()
    init_db(db)
    init_db(db)
    with sqlite3.connect(db) as conn:
        assert conn.execute("SELECT version FROM schema_version").fetchone()[0] == LATEST_SCHEMA_VERSION
        assert conn.execute(
            "SELECT ticker,company_name FROM stocks ORDER BY id"
        ).fetchall() == before
        assert conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='stock_ir_sources'"
        ).fetchone()
        assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"


def test_schema_version_8_migrates_to_9_idempotently(tmp_path: Path) -> None:
    db = tmp_path / "v8.db"
    init_db(db)
    with sqlite3.connect(db) as conn:
        conn.execute("DROP TABLE company_notes")
        conn.execute("DROP TABLE company_intelligence")
        conn.execute("UPDATE schema_version SET version=8")
        before = conn.execute(
            "SELECT ticker,company_name FROM stocks ORDER BY id"
        ).fetchall()
    init_db(db)
    init_db(db)
    with sqlite3.connect(db) as conn:
        assert conn.execute("SELECT version FROM schema_version").fetchone()[0] == LATEST_SCHEMA_VERSION
        assert conn.execute(
            "SELECT ticker,company_name FROM stocks ORDER BY id"
        ).fetchall() == before
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        assert {"company_intelligence", "company_notes"}.issubset(tables)
        assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"


def test_schema_version_9_migrates_to_10_idempotently(tmp_path: Path) -> None:
    db = tmp_path / "v9.db"
    init_db(db)
    with sqlite3.connect(db) as conn:
        conn.execute("DROP TABLE investment_playbooks")
        conn.execute("UPDATE schema_version SET version=9")
        before = conn.execute(
            "SELECT ticker,company_name FROM stocks ORDER BY id"
        ).fetchall()
    init_db(db)
    init_db(db)
    with sqlite3.connect(db) as conn:
        assert conn.execute("SELECT version FROM schema_version").fetchone()[0] == LATEST_SCHEMA_VERSION
        assert conn.execute(
            "SELECT ticker,company_name FROM stocks ORDER BY id"
        ).fetchall() == before
        assert conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='investment_playbooks'"
        ).fetchone()
        assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"


def test_schema_version_10_migrates_to_11_idempotently(tmp_path: Path) -> None:
    db = tmp_path / "v10.db"
    init_db(db)
    strategy_tables = [
        "stock_trade_rules",
        "strategy_rule_sets",
        "stock_strategy_tags",
        "strategy_tags",
    ]
    with sqlite3.connect(db) as conn:
        conn.execute("PRAGMA foreign_keys=OFF")
        for table in strategy_tables:
            conn.execute(f"DROP TABLE {table}")
        conn.execute("UPDATE schema_version SET version=10")
        before = conn.execute(
            "SELECT ticker,company_name FROM stocks ORDER BY id"
        ).fetchall()
    init_db(db)
    init_db(db)
    with sqlite3.connect(db) as conn:
        assert conn.execute(
            "SELECT version FROM schema_version"
        ).fetchone()[0] == LATEST_SCHEMA_VERSION
        assert conn.execute(
            "SELECT ticker,company_name FROM stocks ORDER BY id"
        ).fetchall() == before
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        assert set(strategy_tables).issubset(tables)
        assert conn.execute(
            "SELECT COUNT(*) FROM strategy_tags"
        ).fetchone()[0] == 18
        assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
