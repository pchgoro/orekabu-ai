"""Explainable user score and category rule tests."""

from __future__ import annotations

from services.categories import list_categories, replace_stock_categories
from services.database import get_stock, init_db
from services.stock_scores import (
    calculate_ore_score,
    enrich_rows_with_ore_scores,
    list_score_history,
    record_scores,
    save_trade_rule,
)


def test_ore_score_is_clamped_and_explained(tmp_path) -> None:
    db = tmp_path / "scores.db"; init_db(db)
    stock = get_stock("5801.T", db); assert stock
    categories = {row["name"]: row for row in list_categories(db)}
    replace_stock_categories(int(stock["id"]), [int(categories["AI"]["id"]), int(categories["国策"]["id"])], db)
    result = calculate_ore_score({**stock, "current_price": 900, "average_price": 1000, "profit_loss": -100, "volume_ratio": 2.0}, db)
    assert 0 <= result["score"] <= 100
    assert {part["reason"] for part in result["breakdown"]} >= {"基本点", "AIテーマ", "国策テーマ", "出来高増加", "含み損"}


def test_trade_rule_marks_stop_and_history_is_explicit(tmp_path) -> None:
    db = tmp_path / "history.db"; init_db(db)
    stock = get_stock("5801.T", db); assert stock
    ai = next(row for row in list_categories(db) if row["name"] == "AI")
    replace_stock_categories(int(stock["id"]), [int(ai["id"])], db)
    save_trade_rule(int(ai["id"]), {"stop_loss_percent": 8, "take_profit_percent": 30}, db)
    row = {**stock, "current_price": 900, "average_price": 1000, "profit_loss": -100}
    scored = enrich_rows_with_ore_scores([row], db)
    assert scored[0]["ore_score"]["stop_loss_reached"] is True
    assert record_scores(scored, db) == 1
    assert len(list_score_history(int(stock["id"]), db_path=db)) == 1


def test_ore_score_improvements_and_sudden_changes(tmp_path) -> None:
    from services.stock_scores import score_rankings
    from services.daily_briefing import build_daily_tasks

    db = tmp_path / "impr.db"; init_db(db)
    stock = get_stock("5801.T", db); assert stock
    
    res = calculate_ore_score(stock, db)
    assert any("カテゴリ" in imp for imp in res["improvements"])
    
    ai = next(row for row in list_categories(db) if row["name"] == "AI")
    replace_stock_categories(int(stock["id"]), [int(ai["id"])], db)
    
    res = calculate_ore_score(stock, db)
    assert any("投資ルール" in imp for imp in res["improvements"])
    
    save_trade_rule(int(ai["id"]), {"max_holding_ratio_percent": 10}, db)
    
    row = {**stock, "is_holding": 1, "shares": 100, "current_price": 1000, "average_price": 1000}
    scored = enrich_rows_with_ore_scores([row], db)
    assert record_scores(scored, db) == 1
    
    kokusaku = next(row for row in list_categories(db) if row["name"] == "国策")
    replace_stock_categories(int(stock["id"]), [int(ai["id"]), int(kokusaku["id"])], db)

    row_new = {**stock, "is_holding": 1, "shares": 100, "current_price": 1000, "average_price": 1000, "volume_ratio": 2.0}
    scored_new = enrich_rows_with_ore_scores([row_new], db)
    
    rankings = score_rankings(scored_new)
    assert len(rankings["sudden_changes"]) == 1
    assert rankings["sudden_changes"][0]["score_diff"] == 15
    
    tasks = build_daily_tasks(
        stock_rows=scored_new,
        earnings_rows=[],
        candidates=[],
        news_rows=[],
        buy_watch_rows=[]
    )
    ratio_tasks = [t for t in tasks if t["label"] == "カテゴリ比率超過"]
    assert len(ratio_tasks) == 1
    assert "AI" in ratio_tasks[0]["detail"]

