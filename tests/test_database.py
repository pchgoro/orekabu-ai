"""Tests for database layer."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from services.database import add_stock, delete_stock, get_stock, get_stocks, init_db, load_settings, save_settings, set_setting, update_stock
from services.settings import default_settings


def test_db_init(tmp_path: Path) -> None:
    db = tmp_path / "test.db"
    init_db(db)
    init_db(db)
    stocks = get_stocks(db)
    assert len(stocks) == 3
    assert load_settings(db)["ranking_limit"] == 10


def test_crud_and_duplicate(tmp_path: Path) -> None:
    db = tmp_path / "test.db"
    init_db(db)
    stock_id = add_stock({"ticker": "7203", "company_name": "トヨタ", "category": "監視銘柄"}, db)
    assert get_stock("7203.T", db)["company_name"] == "トヨタ"
    update_stock(stock_id, {"ticker": "7203", "company_name": "Toyota", "category": "その他"}, db)
    assert get_stock("7203.T", db)["category"] == "その他"
    with pytest.raises(sqlite3.IntegrityError):
        add_stock({"ticker": "7203", "company_name": "重複", "category": "監視銘柄"}, db)
    delete_stock(stock_id, db)
    assert get_stock("7203.T", db) is None


def test_settings_save(tmp_path: Path) -> None:
    db = tmp_path / "test.db"
    init_db(db)
    settings = load_settings(db)
    settings["ranking_limit"] = 20
    save_settings(settings, db)
    assert load_settings(db)["ranking_limit"] == 20


def test_settings_reset_to_default(tmp_path: Path) -> None:
    db = tmp_path / "test.db"
    init_db(db)
    settings = load_settings(db)
    settings["ranking_limit"] = 20
    save_settings(settings, db)
    save_settings(default_settings(), db)
    assert load_settings(db)["ranking_limit"] == 10


def test_auto_fetch_settings_are_clamped(tmp_path: Path) -> None:
    db = tmp_path / "test.db"
    init_db(db)
    settings = load_settings(db)
    settings["earnings_auto_fetch"].update({"max_tickers_per_run": 999, "request_interval_seconds": 0, "cache_hours": 0})
    save_settings(settings, db)
    auto = load_settings(db)["earnings_auto_fetch"]
    assert auto["max_tickers_per_run"] == 100
    assert auto["request_interval_seconds"] == 1.0
    assert auto["cache_hours"] == 1


def test_edinet_settings_defaults_and_ranges(tmp_path: Path) -> None:
    db = tmp_path / "edinet-settings.db"
    init_db(db)
    defaults = load_settings(db)
    assert defaults["edinet_daily_lookback_days"] == 3
    assert defaults["edinet_monthly_lookback_days"] == 30
    assert defaults["edinet_initial_backfill_days"] == 90
    assert defaults["edinet_fetch_limit"] == 20

    defaults.update(
        {
            "edinet_daily_lookback_days": 999,
            "edinet_monthly_lookback_days": 0,
            "edinet_initial_backfill_days": 366,
            "edinet_fetch_limit": 9999,
        }
    )
    save_settings(defaults, db)
    loaded = load_settings(db)
    assert loaded["edinet_daily_lookback_days"] == 30
    assert loaded["edinet_monthly_lookback_days"] == 1
    assert loaded["edinet_initial_backfill_days"] == 365
    assert loaded["edinet_fetch_limit"] == 500


def test_daily_ux_settings_merge_and_preserve_existing_settings(tmp_path: Path) -> None:
    db = tmp_path / "daily.db"; init_db(db)
    settings = load_settings(db)
    settings["earnings_auto_fetch"]["max_tickers_per_run"] = 7
    settings.update({"dashboard_display_mode":"コンパクト","display_density":"ゆったり","news_display_mode":"表","mobile_priority_display":True,"briefing_limit":99,"daily_tasks_limit":99,"hide_zero_sections":False,"strategy_rule_near_percent":99})
    save_settings(settings, db)
    loaded = load_settings(db)
    assert loaded["dashboard_display_mode"] == "コンパクト"
    assert loaded["display_density"] == "ゆったり"
    assert loaded["strategy_rule_near_percent"] == 20.0
    assert loaded["news_display_mode"] == "表"
    assert loaded["briefing_limit"] == 20 and loaded["daily_tasks_limit"] == 10
    assert loaded["earnings_auto_fetch"]["max_tickers_per_run"] == 7


def test_invalid_persisted_settings_fall_back_without_breaking_startup(tmp_path: Path) -> None:
    db = tmp_path / "invalid-settings.db"; init_db(db)
    set_setting("settings", {
        "briefing_limit": "not-a-number",
        "stock_cache_minutes": None,
        "buy_watch_near_percent": "nan",
        "mobile_priority_display": "false",
        "earnings_auto_fetch": "broken",
        "score": {"base_score": "inf", "rsi_low": "invalid"},
    }, db)
    loaded = load_settings(db)
    assert loaded["briefing_limit"] == 10
    assert loaded["stock_cache_minutes"] == 15
    assert loaded["buy_watch_near_percent"] == 3.0
    assert loaded["mobile_priority_display"] is False
    assert loaded["earnings_auto_fetch"]["max_tickers_per_run"] == 20
    assert loaded["score"]["base_score"] == 50.0
    assert loaded["score"]["rsi_low"] == 30.0


def test_environment_db_override_uses_isolated_database(tmp_path: Path, monkeypatch) -> None:
    isolated = tmp_path / "isolated.db"
    monkeypatch.setenv("OREKABU_DB_PATH", str(isolated))
    init_db()
    assert isolated.exists()
    assert len(get_stocks()) == 3
