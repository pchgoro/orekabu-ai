"""Theme category, line rule, and trade note tests."""

from __future__ import annotations

import pytest

from services.categories import (
    delete_category,
    get_category_rule,
    get_trade_notes,
    list_categories,
    list_stock_categories,
    replace_stock_categories,
    save_category,
    save_category_rule,
    save_trade_notes,
)
from services.database import get_stock, init_db


def test_categories_assign_rules_and_notes(tmp_path) -> None:
    db = tmp_path / "categories.db"; init_db(db)
    stock = get_stock("5801.T", db); assert stock
    ai = next(row for row in list_categories(db) if row["name"] == "AI")
    custom_id = save_category("送電網", "電力インフラ", db_path=db)
    replace_stock_categories(int(stock["id"]), [int(ai["id"]), custom_id], db)
    assert {row["name"] for row in list_stock_categories(int(stock["id"]), db)} == {"AI", "送電網"}
    save_category_rule(custom_id, {"stop_loss_price": 1000, "take_profit_price": 2000, "add_position_price": 1200}, db)
    assert get_category_rule(custom_id, db)["take_profit_price"] == 2000
    save_trade_notes(int(stock["id"]), {"holding_reason": "成長性", "sell_conditions": "下方修正", "memo": "確認"}, db)
    assert get_trade_notes(int(stock["id"]), db)["sell_conditions"] == "下方修正"


def test_assigned_category_cannot_be_deleted(tmp_path) -> None:
    db = tmp_path / "category_delete.db"; init_db(db)
    stock = get_stock("5801.T", db); assert stock
    category_id = save_category("テスト", db_path=db)
    replace_stock_categories(int(stock["id"]), [category_id], db)
    with pytest.raises(ValueError, match="無効化"):
        delete_category(category_id, db)
