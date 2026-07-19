"""Strategy tag, reusable rule, override, CSV, and aggregate tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from services.database import connect, get_stock, init_db
from services.strategy_rules import (
    aggregate_by_tag,
    apply_bulk_preview,
    calculate_rule_lines,
    delete_tag,
    enrich_rows_with_strategy,
    export_rule_csv,
    export_tag_csv,
    import_rule_csv,
    import_tag_csv,
    list_stock_tags,
    list_tags,
    parse_rule_csv,
    parse_tag_csv,
    preview_bulk_apply,
    replace_stock_tags,
    resolve_strategy_rule,
    save_rule_set,
    save_stock_rule,
    save_tag,
)


def _stock(db: Path, ticker: str = "5801.T") -> dict:
    stock = get_stock(ticker, db)
    assert stock
    return stock


def _tag_id(db: Path, name: str, group: str) -> int:
    tag = next(
        row for row in list_tags(db)
        if row["name"] == name and row["tag_group"] == group
    )
    return int(tag["id"])


def _rule(stop: float = 8, take: float = 30, add: float = 12, priority: int = 10) -> dict:
    return {
        "stop_loss_type": "percent_from_average_price",
        "stop_loss_value": stop,
        "take_profit_type": "percent_from_average_price",
        "take_profit_value": take,
        "add_position_type": "percent_from_average_price",
        "add_position_value": add,
        "priority": priority,
        "memo": "test",
    }


def test_tag_crud_multiple_assignment_and_duplicate_prevention(tmp_path: Path) -> None:
    db = tmp_path / "tags.db"
    init_db(db)
    stock = _stock(db)
    ai = _tag_id(db, "AI", "theme")
    medium = _tag_id(db, "中期", "horizon")
    replace_stock_tags(int(stock["id"]), [ai, medium, ai], db)
    assigned = list_stock_tags(int(stock["id"]), db)
    assert {row["name"] for row in assigned} == {"AI", "中期"}
    with connect(db) as conn:
        assert conn.execute(
            "SELECT COUNT(*) FROM stock_strategy_tags WHERE stock_id=?",
            (int(stock["id"]),),
        ).fetchone()[0] == 2

    custom = save_tag(
        {
            "name": "独自テーマ",
            "tag_group": "custom",
            "description": "確認用",
            "color_key": "warning",
        },
        db,
    )
    with pytest.raises(Exception):
        save_tag({"name": "独自テーマ", "tag_group": "custom"}, db)
    delete_tag(custom, db)


def test_priority_conflict_and_individual_override(tmp_path: Path) -> None:
    db = tmp_path / "priority.db"
    init_db(db)
    stock = _stock(db)
    ai = _tag_id(db, "AI", "theme")
    medium = _tag_id(db, "中期", "horizon")
    replace_stock_tags(int(stock["id"]), [ai, medium], db)
    save_rule_set(ai, _rule(stop=8, priority=10), db)
    save_rule_set(medium, _rule(stop=10, priority=20), db)
    resolved = resolve_strategy_rule(int(stock["id"]), db)
    assert resolved["source_tag_id"] == medium
    assert not resolved["conflict"]

    save_rule_set(ai, _rule(stop=8, priority=20), db)
    resolved = resolve_strategy_rule(int(stock["id"]), db)
    assert resolved["conflict"]
    assert len(resolved["candidates"]) == 2

    save_stock_rule(
        int(stock["id"]),
        {
            "stop_loss_type": "fixed_price",
            "stop_loss_value": 1000,
            "take_profit_type": "fixed_price",
            "take_profit_value": 2000,
            "add_position_type": "none",
        },
        db,
    )
    resolved = resolve_strategy_rule(int(stock["id"]), db)
    assert resolved["source_type"] == "individual"
    assert resolved["rule"]["stop_loss_value"] == 1000


def test_line_calculation_and_near_states() -> None:
    rule = _rule()
    lines = calculate_rule_lines(rule, 1000, 920, near_percent=3)
    assert lines["stop_loss_price"] == 920
    assert lines["take_profit_price"] == 1300
    assert lines["add_position_price"] == 880
    assert lines["stop_loss_reached"]

    assert calculate_rule_lines(rule, 1000, 940, near_percent=3)["stop_loss_near"]
    assert calculate_rule_lines(rule, 1000, 1270, near_percent=3)["take_profit_near"]
    assert calculate_rule_lines(rule, 1000, 900, near_percent=3)["add_position_near"]
    assert calculate_rule_lines(rule, 1000, 1300)["take_profit_reached"]


def test_bulk_apply_preview_preserves_override_and_prevents_duplicates(tmp_path: Path) -> None:
    db = tmp_path / "bulk.db"
    init_db(db)
    stock = _stock(db)
    ai = _tag_id(db, "AI", "theme")
    replace_stock_tags(int(stock["id"]), [ai], db)
    save_rule_set(ai, _rule(), db)
    preview = preview_bulk_apply([int(stock["id"])], db)
    assert preview[0]["action"] == "新規"
    result = apply_bulk_preview(preview, [int(stock["id"])], db)
    assert result["applied"] == 1
    assert resolve_strategy_rule(int(stock["id"]), db)["status"] == "applied"
    second = preview_bulk_apply([int(stock["id"])], db)
    assert second[0]["action"] == "同一"
    apply_bulk_preview(second, [int(stock["id"])], db)
    with connect(db) as conn:
        assert conn.execute(
            "SELECT COUNT(*) FROM stock_trade_rules WHERE stock_id=?",
            (int(stock["id"]),),
        ).fetchone()[0] == 1

    save_stock_rule(int(stock["id"]), _rule(stop=5), db)
    assert preview_bulk_apply([int(stock["id"])], db)[0]["action"] == "個別上書きを維持"


def test_tag_and_rule_csv_utf8_bom_and_row_level_failure(tmp_path: Path) -> None:
    db = tmp_path / "csv.db"
    init_db(db)
    parsed = parse_tag_csv(
        "\ufeffticker,tags\n5801,AI|中期\nBAD,AI\n".encode("utf-8")
    )
    result = import_tag_csv(parsed, db)
    assert result == {"updated": 1, "skipped": 0, "failed": 1}
    exported = export_tag_csv(db).decode("utf-8-sig")
    assert "5801.T" in exported
    assert "AI" in exported and "中期" in exported

    rule_csv = (
        "\ufefftag_name,tag_group,stop_loss_type,stop_loss_value,"
        "take_profit_type,take_profit_value,add_position_type,"
        "add_position_value,priority,memo\n"
        "AI,theme,percent_from_average_price,8,"
        "percent_from_average_price,30,none,,10,標準\n"
    ).encode("utf-8")
    rules = parse_rule_csv(rule_csv)
    assert import_rule_csv(rules, db)["inserted"] == 1
    exported_rules = export_rule_csv(db).decode("utf-8-sig")
    assert "AI,theme" in exported_rules


def test_tag_aggregate_counts_overlap_and_portfolio_ratio(tmp_path: Path) -> None:
    db = tmp_path / "aggregate.db"
    init_db(db)
    stock = _stock(db)
    ai = _tag_id(db, "AI", "theme")
    power = _tag_id(db, "電力", "theme")
    replace_stock_tags(int(stock["id"]), [ai, power], db)
    rows = enrich_rows_with_strategy(
        [
            {
                **stock,
                "is_holding": 1,
                "market_value": 100000,
                "profit": 10000,
                "profit_pct": 10,
                "current_price": 1000,
                "earnings_days_until": 3,
            }
        ],
        db,
    )
    aggregates = aggregate_by_tag(rows)
    selected = [row for row in aggregates if row["tag"] in {"AI", "電力"}]
    assert len(selected) == 2
    assert all(row["portfolio_ratio"] == 100 for row in selected)
    assert sum(row["market_value"] for row in selected) == 200000
