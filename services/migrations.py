"""Idempotent SQLite schema migrations."""

from __future__ import annotations

import logging
import sqlite3

logger = logging.getLogger(__name__)
LATEST_SCHEMA_VERSION = 13


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

        if version > LATEST_SCHEMA_VERSION:
            raise RuntimeError(f"未対応のDBバージョンです: {version}")

        if version < 2:
            _migrate_to_v2(conn)
            conn.execute("UPDATE schema_version SET version = 2")
            version = 2

        if version < 3:
            _migrate_to_v3(conn)
            conn.execute("UPDATE schema_version SET version = 3")
            version = 3

        if version < 4:
            _migrate_to_v4(conn)
            conn.execute("UPDATE schema_version SET version = 4")
            version = 4

        if version < 5:
            _migrate_to_v5(conn)
            conn.execute("UPDATE schema_version SET version = 5")
            version = 5

        if version < 6:
            _migrate_to_v6(conn)
            conn.execute("UPDATE schema_version SET version = 6")
            version = 6

        if version < 7:
            _migrate_to_v7(conn)
            conn.execute("UPDATE schema_version SET version = 7")
            version = 7

        if version < 8:
            _migrate_to_v8(conn)
            conn.execute("UPDATE schema_version SET version = 8")
            version = 8

        if version < 9:
            _migrate_to_v9(conn)
            conn.execute("UPDATE schema_version SET version = 9")
            version = 9

        if version < 10:
            _migrate_to_v10(conn)
            conn.execute("UPDATE schema_version SET version = 10")
            version = 10

        if version < 11:
            _migrate_to_v11(conn)
            conn.execute("UPDATE schema_version SET version = 11")
            version = 11

        if version < 12:
            _migrate_to_v12(conn)
            conn.execute("UPDATE schema_version SET version = 12")
            version = 12

        if version < 13:
            _migrate_to_v13(conn)
            conn.execute("UPDATE schema_version SET version = 13")
            version = 13

        # CREATE IF NOT EXISTS also repairs a partially created v2 migration.
        _migrate_to_v2(conn)
        _migrate_to_v3(conn)
        _migrate_to_v4(conn)
        _migrate_to_v5(conn)
        _migrate_to_v6(conn)
        _migrate_to_v7(conn)
        _migrate_to_v8(conn)
        _migrate_to_v9(conn)
        _migrate_to_v10(conn)
        _migrate_to_v11(conn)
        _migrate_to_v12(conn)
        _migrate_to_v13(conn)
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


def _migrate_to_v4(conn: sqlite3.Connection) -> None:
    """Add local news ingestion, matching, organization, and fetch audit tables."""
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS news_sources (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            source_type TEXT NOT NULL,
            url TEXT NOT NULL DEFAULT '',
            is_enabled INTEGER NOT NULL DEFAULT 1,
            memo TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS news_articles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_id INTEGER,
            external_id TEXT NOT NULL DEFAULT '',
            title TEXT NOT NULL,
            url TEXT NOT NULL DEFAULT '',
            canonical_url TEXT NOT NULL DEFAULT '',
            published_at TEXT,
            author TEXT NOT NULL DEFAULT '',
            summary TEXT NOT NULL DEFAULT '',
            retrieved_at TEXT NOT NULL,
            deduplication_key TEXT NOT NULL UNIQUE,
            is_read INTEGER NOT NULL DEFAULT 0,
            is_favorite INTEGER NOT NULL DEFAULT 0,
            importance TEXT NOT NULL DEFAULT '通常',
            category TEXT NOT NULL DEFAULT 'その他',
            memo TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY(source_id) REFERENCES news_sources(id) ON DELETE SET NULL
        );
        CREATE TABLE IF NOT EXISTS news_article_stocks (
            article_id INTEGER NOT NULL,
            stock_id INTEGER NOT NULL,
            match_reason TEXT NOT NULL DEFAULT '',
            confirmed INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            PRIMARY KEY(article_id, stock_id),
            FOREIGN KEY(article_id) REFERENCES news_articles(id) ON DELETE CASCADE,
            FOREIGN KEY(stock_id) REFERENCES stocks(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS stock_news_keywords (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            stock_id INTEGER NOT NULL,
            keyword TEXT NOT NULL,
            is_enabled INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(stock_id, keyword),
            FOREIGN KEY(stock_id) REFERENCES stocks(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS news_tags (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS news_article_tags (
            article_id INTEGER NOT NULL,
            tag_id INTEGER NOT NULL,
            PRIMARY KEY(article_id, tag_id),
            FOREIGN KEY(article_id) REFERENCES news_articles(id) ON DELETE CASCADE,
            FOREIGN KEY(tag_id) REFERENCES news_tags(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS news_fetch_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            started_at TEXT NOT NULL,
            finished_at TEXT,
            source_count INTEGER NOT NULL DEFAULT 0,
            article_count INTEGER NOT NULL DEFAULT 0,
            duplicate_count INTEGER NOT NULL DEFAULT 0,
            failed_count INTEGER NOT NULL DEFAULT 0,
            status TEXT NOT NULL,
            error_summary TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS news_fetch_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fetch_run_id INTEGER NOT NULL,
            source_id INTEGER,
            status TEXT NOT NULL,
            article_count INTEGER NOT NULL DEFAULT 0,
            duplicate_count INTEGER NOT NULL DEFAULT 0,
            error_message TEXT NOT NULL DEFAULT '',
            retrieved_at TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY(fetch_run_id) REFERENCES news_fetch_runs(id) ON DELETE CASCADE,
            FOREIGN KEY(source_id) REFERENCES news_sources(id) ON DELETE SET NULL
        );
        CREATE INDEX IF NOT EXISTS idx_news_articles_published ON news_articles(published_at DESC);
        CREATE INDEX IF NOT EXISTS idx_news_articles_state ON news_articles(is_read, is_favorite, importance);
        CREATE INDEX IF NOT EXISTS idx_news_article_stocks_stock ON news_article_stocks(stock_id, confirmed);
        CREATE INDEX IF NOT EXISTS idx_news_fetch_results_run ON news_fetch_results(fetch_run_id);
        """
    )


def _migrate_to_v5(conn: sqlite3.Connection) -> None:
    """Add manually managed disclosures, tags, news links, and import audit tables."""
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS disclosures (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            stock_id INTEGER NOT NULL,
            disclosure_type TEXT NOT NULL,
            title TEXT NOT NULL,
            disclosed_at TEXT NOT NULL,
            source_name TEXT NOT NULL DEFAULT '',
            source_url TEXT NOT NULL DEFAULT '',
            document_url TEXT NOT NULL DEFAULT '',
            local_file_path TEXT NOT NULL DEFAULT '',
            summary TEXT NOT NULL DEFAULT '',
            importance TEXT NOT NULL DEFAULT '通常',
            is_read INTEGER NOT NULL DEFAULT 0,
            is_favorite INTEGER NOT NULL DEFAULT 0,
            user_memo TEXT NOT NULL DEFAULT '',
            external_id TEXT NOT NULL DEFAULT '',
            content_hash TEXT NOT NULL UNIQUE,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY(stock_id) REFERENCES stocks(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS disclosure_tags (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS disclosure_tag_links (
            disclosure_id INTEGER NOT NULL,
            tag_id INTEGER NOT NULL,
            PRIMARY KEY(disclosure_id, tag_id),
            FOREIGN KEY(disclosure_id) REFERENCES disclosures(id) ON DELETE CASCADE,
            FOREIGN KEY(tag_id) REFERENCES disclosure_tags(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS disclosure_news_links (
            disclosure_id INTEGER NOT NULL,
            news_article_id INTEGER NOT NULL,
            match_reason TEXT NOT NULL DEFAULT '',
            confirmed INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            PRIMARY KEY(disclosure_id, news_article_id),
            FOREIGN KEY(disclosure_id) REFERENCES disclosures(id) ON DELETE CASCADE,
            FOREIGN KEY(news_article_id) REFERENCES news_articles(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS disclosure_import_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            started_at TEXT NOT NULL,
            finished_at TEXT,
            row_count INTEGER NOT NULL DEFAULT 0,
            inserted_count INTEGER NOT NULL DEFAULT 0,
            updated_count INTEGER NOT NULL DEFAULT 0,
            skipped_count INTEGER NOT NULL DEFAULT 0,
            failed_count INTEGER NOT NULL DEFAULT 0,
            status TEXT NOT NULL,
            error_summary TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS disclosure_import_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            import_run_id INTEGER NOT NULL,
            row_number INTEGER NOT NULL,
            ticker TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL,
            disclosure_id INTEGER,
            error_message TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            FOREIGN KEY(import_run_id) REFERENCES disclosure_import_runs(id) ON DELETE CASCADE,
            FOREIGN KEY(disclosure_id) REFERENCES disclosures(id) ON DELETE SET NULL
        );
        CREATE UNIQUE INDEX IF NOT EXISTS idx_disclosures_external_id
            ON disclosures(external_id) WHERE external_id <> '';
        CREATE INDEX IF NOT EXISTS idx_disclosures_date ON disclosures(disclosed_at DESC);
        CREATE INDEX IF NOT EXISTS idx_disclosures_stock_state ON disclosures(stock_id, is_read, importance);
        CREATE INDEX IF NOT EXISTS idx_disclosure_news_article ON disclosure_news_links(news_article_id, confirmed);
        CREATE INDEX IF NOT EXISTS idx_disclosure_import_results_run ON disclosure_import_results(import_run_id);
        """
    )


def _migrate_to_v6(conn: sqlite3.Connection) -> None:
    """Add optional company profile metadata without rebuilding stocks."""
    columns = {str(row[1]) for row in conn.execute("PRAGMA table_info(stocks)").fetchall()}
    for name in ("company_alias", "market", "industry"):
        if name not in columns:
            conn.execute(f"ALTER TABLE stocks ADD COLUMN {name} TEXT NOT NULL DEFAULT ''")


def _migrate_to_v7(conn: sqlite3.Connection) -> None:
    """Add free automation candidates and execution audit tables."""
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS edinet_documents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            doc_id TEXT NOT NULL UNIQUE,
            stock_id INTEGER NOT NULL,
            edinet_code TEXT NOT NULL DEFAULT '',
            sec_code TEXT NOT NULL DEFAULT '',
            filer_name TEXT NOT NULL DEFAULT '',
            document_type TEXT NOT NULL,
            submitted_at TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            reference_url TEXT NOT NULL DEFAULT '',
            retrieved_at TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY(stock_id) REFERENCES stocks(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS edinet_fetch_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            started_at TEXT NOT NULL,
            finished_at TEXT,
            target_date TEXT NOT NULL,
            target_count INTEGER NOT NULL DEFAULT 0,
            document_count INTEGER NOT NULL DEFAULT 0,
            inserted_count INTEGER NOT NULL DEFAULT 0,
            duplicate_count INTEGER NOT NULL DEFAULT 0,
            failed_count INTEGER NOT NULL DEFAULT 0,
            status TEXT NOT NULL,
            error_summary TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS edinet_fetch_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fetch_run_id INTEGER NOT NULL,
            stock_id INTEGER,
            ticker TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL,
            document_count INTEGER NOT NULL DEFAULT 0,
            inserted_count INTEGER NOT NULL DEFAULT 0,
            duplicate_count INTEGER NOT NULL DEFAULT 0,
            error_message TEXT NOT NULL DEFAULT '',
            retrieved_at TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY(fetch_run_id) REFERENCES edinet_fetch_runs(id) ON DELETE CASCADE,
            FOREIGN KEY(stock_id) REFERENCES stocks(id) ON DELETE SET NULL
        );
        CREATE TABLE IF NOT EXISTS stock_profile_candidates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            stock_id INTEGER NOT NULL,
            provider_name TEXT NOT NULL,
            company_name TEXT NOT NULL DEFAULT '',
            company_alias TEXT NOT NULL DEFAULT '',
            market TEXT NOT NULL DEFAULT '',
            industry TEXT NOT NULL DEFAULT '',
            current_company_name TEXT NOT NULL DEFAULT '',
            current_company_alias TEXT NOT NULL DEFAULT '',
            current_market TEXT NOT NULL DEFAULT '',
            current_industry TEXT NOT NULL DEFAULT '',
            review_status TEXT NOT NULL DEFAULT 'pending',
            retrieved_at TEXT NOT NULL,
            fingerprint TEXT NOT NULL UNIQUE,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY(stock_id) REFERENCES stocks(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS automation_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            command TEXT NOT NULL,
            started_at TEXT NOT NULL,
            finished_at TEXT,
            dry_run INTEGER NOT NULL DEFAULT 0,
            target_count INTEGER NOT NULL DEFAULT 0,
            success_count INTEGER NOT NULL DEFAULT 0,
            failed_count INTEGER NOT NULL DEFAULT 0,
            status TEXT NOT NULL,
            error_summary TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS automation_run_steps (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            automation_run_id INTEGER NOT NULL,
            step_name TEXT NOT NULL,
            sequence_no INTEGER NOT NULL,
            started_at TEXT NOT NULL,
            finished_at TEXT,
            status TEXT NOT NULL,
            processed_count INTEGER NOT NULL DEFAULT 0,
            inserted_count INTEGER NOT NULL DEFAULT 0,
            duplicate_count INTEGER NOT NULL DEFAULT 0,
            failed_count INTEGER NOT NULL DEFAULT 0,
            message TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            FOREIGN KEY(automation_run_id) REFERENCES automation_runs(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_edinet_documents_stock_date
            ON edinet_documents(stock_id, submitted_at DESC);
        CREATE INDEX IF NOT EXISTS idx_edinet_fetch_results_run
            ON edinet_fetch_results(fetch_run_id);
        CREATE INDEX IF NOT EXISTS idx_profile_candidates_review
            ON stock_profile_candidates(review_status, stock_id);
        CREATE INDEX IF NOT EXISTS idx_automation_runs_started
            ON automation_runs(started_at DESC);
        CREATE INDEX IF NOT EXISTS idx_automation_steps_run
            ON automation_run_steps(automation_run_id, sequence_no);
        """
    )


def _migrate_to_v8(conn: sqlite3.Connection) -> None:
    """Add per-stock official IR sources for reviewable earnings fallbacks."""
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS stock_ir_sources (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            stock_id INTEGER NOT NULL,
            source_type TEXT NOT NULL,
            source_url TEXT NOT NULL,
            enabled INTEGER NOT NULL DEFAULT 1,
            last_checked_at TEXT,
            last_success_at TEXT,
            last_error TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(stock_id, source_type),
            FOREIGN KEY(stock_id) REFERENCES stocks(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_stock_ir_sources_enabled
            ON stock_ir_sources(enabled, source_type, stock_id);
        """
    )


def _migrate_to_v9(conn: sqlite3.Connection) -> None:
    """Add company intelligence notes, themes, story, and checklist state."""
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS company_intelligence (
            stock_id INTEGER PRIMARY KEY,
            themes TEXT NOT NULL DEFAULT '',
            investment_story TEXT NOT NULL DEFAULT '',
            earnings_checked INTEGER NOT NULL DEFAULT 0,
            disclosure_checked INTEGER NOT NULL DEFAULT 0,
            news_checked INTEGER NOT NULL DEFAULT 0,
            edinet_checked INTEGER NOT NULL DEFAULT 0,
            ai_analyzed INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY(stock_id) REFERENCES stocks(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS company_notes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            stock_id INTEGER NOT NULL,
            note TEXT NOT NULL,
            occurred_at TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY(stock_id) REFERENCES stocks(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_company_notes_stock_date
            ON company_notes(stock_id, occurred_at DESC, id DESC);
        """
    )


def _migrate_to_v10(conn: sqlite3.Connection) -> None:
    """Add one user-authored investment playbook per registered stock."""
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS investment_playbooks (
            stock_id INTEGER PRIMARY KEY,
            buy_reason TEXT NOT NULL DEFAULT '',
            investment_theme TEXT NOT NULL DEFAULT '[]',
            target_price_1 REAL,
            target_price_1_sell_percent REAL,
            target_price_2 REAL,
            target_price_2_sell_percent REAL,
            final_target_price REAL,
            stop_loss_price REAL,
            trailing_stop_percent REAL,
            holding_period TEXT NOT NULL DEFAULT '',
            exit_conditions TEXT NOT NULL DEFAULT '{"selected":[],"custom":""}',
            risk_notes TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY(stock_id) REFERENCES stocks(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_investment_playbooks_updated
            ON investment_playbooks(updated_at DESC);
        """
    )


def _migrate_to_v11(conn: sqlite3.Connection) -> None:
    """Add reusable strategy tags, tag rules, assignments, and stock overrides."""
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS strategy_tags (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            tag_group TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            color_key TEXT NOT NULL DEFAULT 'info',
            display_order INTEGER NOT NULL DEFAULT 0,
            is_active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(name, tag_group)
        );
        CREATE TABLE IF NOT EXISTS stock_strategy_tags (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            stock_id INTEGER NOT NULL,
            tag_id INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            UNIQUE(stock_id, tag_id),
            FOREIGN KEY(stock_id) REFERENCES stocks(id) ON DELETE CASCADE,
            FOREIGN KEY(tag_id) REFERENCES strategy_tags(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS strategy_rule_sets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tag_id INTEGER NOT NULL UNIQUE,
            stop_loss_type TEXT NOT NULL DEFAULT 'none',
            stop_loss_value REAL,
            take_profit_type TEXT NOT NULL DEFAULT 'none',
            take_profit_value REAL,
            add_position_type TEXT NOT NULL DEFAULT 'none',
            add_position_value REAL,
            earnings_policy TEXT NOT NULL DEFAULT '',
            priority INTEGER NOT NULL DEFAULT 0,
            memo TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY(tag_id) REFERENCES strategy_tags(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS stock_trade_rules (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            stock_id INTEGER NOT NULL UNIQUE,
            stop_loss_type TEXT NOT NULL DEFAULT 'none',
            stop_loss_value REAL,
            take_profit_type TEXT NOT NULL DEFAULT 'none',
            take_profit_value REAL,
            add_position_type TEXT NOT NULL DEFAULT 'none',
            add_position_value REAL,
            source_type TEXT NOT NULL DEFAULT 'individual',
            source_tag_id INTEGER,
            is_overridden INTEGER NOT NULL DEFAULT 0,
            memo TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY(stock_id) REFERENCES stocks(id) ON DELETE CASCADE,
            FOREIGN KEY(source_tag_id) REFERENCES strategy_tags(id) ON DELETE SET NULL
        );
        CREATE INDEX IF NOT EXISTS idx_strategy_tags_group_order
            ON strategy_tags(tag_group, display_order, name);
        CREATE INDEX IF NOT EXISTS idx_stock_strategy_tags_tag
            ON stock_strategy_tags(tag_id, stock_id);
        CREATE INDEX IF NOT EXISTS idx_strategy_rules_priority
            ON strategy_rule_sets(priority DESC, tag_id);
        CREATE INDEX IF NOT EXISTS idx_stock_trade_rules_source
            ON stock_trade_rules(source_type, source_tag_id);
        """
    )
    now = conn.execute(
        "SELECT COALESCE(MAX(updated_at), datetime('now')) FROM stocks"
    ).fetchone()[0]
    defaults = {
        "theme": ("AI", "半導体", "電力", "データセンター", "防衛", "宇宙", "ロボット"),
        "style": ("グロース", "バリュー", "高配当", "優待"),
        "horizon": ("短期", "中期", "長期"),
        "strategy": ("押し目買い", "決算跨ぎ", "イベント投資", "積立"),
    }
    for group, names in defaults.items():
        for order, name in enumerate(names, start=1):
            conn.execute(
                """INSERT OR IGNORE INTO strategy_tags
                (name,tag_group,description,color_key,display_order,is_active,created_at,updated_at)
                VALUES(?,?,?,?,?,1,?,?)""",
                (name, group, "", "info", order, now, now),
            )


def _migrate_to_v12(conn: sqlite3.Connection) -> None:
    """Add independent theme categories, category price lines, and trade notes."""
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            description TEXT NOT NULL DEFAULT '',
            color_key TEXT NOT NULL DEFAULT 'info',
            is_active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS stock_categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            stock_id INTEGER NOT NULL,
            category_id INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            UNIQUE(stock_id, category_id),
            FOREIGN KEY(stock_id) REFERENCES stocks(id) ON DELETE CASCADE,
            FOREIGN KEY(category_id) REFERENCES categories(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS category_rules (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category_id INTEGER NOT NULL UNIQUE,
            stop_loss_price REAL,
            take_profit_price REAL,
            add_position_price REAL,
            memo TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY(category_id) REFERENCES categories(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS trade_notes (
            stock_id INTEGER PRIMARY KEY,
            holding_reason TEXT NOT NULL DEFAULT '',
            sell_conditions TEXT NOT NULL DEFAULT '',
            memo TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY(stock_id) REFERENCES stocks(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_categories_active_name
            ON categories(is_active, name);
        CREATE INDEX IF NOT EXISTS idx_stock_categories_category_stock
            ON stock_categories(category_id, stock_id);
        """
    )
    now = conn.execute(
        "SELECT COALESCE(MAX(updated_at), datetime('now')) FROM stocks"
    ).fetchone()[0]
    defaults = (
        "AI", "半導体", "半導体素材", "データセンター", "電力", "国策",
        "宇宙", "防衛", "量子", "高配当", "優待", "グロース", "バリュー",
        "短期", "中期", "長期",
    )
    for name in defaults:
        conn.execute(
            """INSERT OR IGNORE INTO categories
            (name,description,color_key,is_active,created_at,updated_at)
            VALUES(?,?,?,1,?,?)""",
            (name, "", "info", now, now),
        )


def _migrate_to_v13(conn: sqlite3.Connection) -> None:
    """Add category trade rules and auditable user score snapshots."""
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS trade_rules (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category_id INTEGER NOT NULL UNIQUE,
            buy_conditions TEXT NOT NULL DEFAULT '',
            add_position_conditions TEXT NOT NULL DEFAULT '',
            take_profit_percent REAL,
            stop_loss_percent REAL,
            max_holding_ratio_percent REAL,
            memo TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY(category_id) REFERENCES categories(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS stock_scores (
            stock_id INTEGER PRIMARY KEY,
            score INTEGER NOT NULL,
            breakdown_json TEXT NOT NULL DEFAULT '[]',
            calculated_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY(stock_id) REFERENCES stocks(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS score_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            stock_id INTEGER NOT NULL,
            score INTEGER NOT NULL,
            breakdown_json TEXT NOT NULL DEFAULT '[]',
            recorded_at TEXT NOT NULL,
            UNIQUE(stock_id, recorded_at),
            FOREIGN KEY(stock_id) REFERENCES stocks(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_score_history_stock_time
            ON score_history(stock_id, recorded_at DESC);
        CREATE INDEX IF NOT EXISTS idx_stock_scores_score
            ON stock_scores(score DESC, updated_at DESC);
        """
    )
