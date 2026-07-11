"""Tests for database layer."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from services.database import add_stock, delete_stock, get_stock, get_stocks, init_db, load_settings, save_settings, update_stock
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
