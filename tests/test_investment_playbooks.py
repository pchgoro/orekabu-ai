"""Investment playbook CRUD, validation, and price-state tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from services.database import get_stock, init_db
from services.investment_playbooks import (
    delete_playbook,
    enrich_rows_with_playbooks,
    evaluate_playbook,
    format_playbook_for_prompt,
    get_playbook,
    save_playbook,
)


def payload() -> dict:
    return {
        "buy_reason": "データセンター投資の拡大",
        "investment_themes": ["AI", "データセンター", "AI"],
        "target_price_1": 3500,
        "target_price_1_sell_percent": 30,
        "target_price_2": 4000,
        "target_price_2_sell_percent": 30,
        "final_target_price": 4500,
        "stop_loss_price": 2900,
        "trailing_stop_percent": 8,
        "holding_period": "中期",
        "exit_conditions": {
            "selected": ["テーマ崩壊", "下方修正"],
            "custom": "受注成長が止まった場合",
        },
        "risk_notes": "決算前後の変動に注意",
    }


def test_playbook_crud_preserves_stock_data(tmp_path: Path) -> None:
    db = tmp_path / "playbook.db"
    init_db(db)
    stock = get_stock("5801.T", db)
    assert stock
    save_playbook(int(stock["id"]), payload(), db)
    saved = get_playbook(int(stock["id"]), db)
    assert saved
    assert saved["investment_themes"] == ["AI", "データセンター"]
    assert saved["target_price_1_sell_percent"] == 30
    assert saved["exit_conditions"]["selected"] == ["テーマ崩壊", "下方修正"]
    assert get_stock("5801.T", db) == stock

    updated = payload()
    updated["buy_reason"] = "更新理由"
    save_playbook(int(stock["id"]), updated, db)
    assert get_playbook(int(stock["id"]), db)["buy_reason"] == "更新理由"

    delete_playbook(int(stock["id"]), db)
    assert get_playbook(int(stock["id"]), db) is None
    assert get_stock("5801.T", db) == stock


@pytest.mark.parametrize(
    ("price", "code"),
    [
        (2800, "stop_loss_reached"),
        (2900, "stop_loss_reached"),
        (3000, "stop_loss_near"),
        (3400, "target_price_1_near"),
        (3500, "target_price_1_reached"),
        (4100, "target_price_2_reached"),
        (4600, "final_target_price_reached"),
    ],
)
def test_playbook_price_states(price: float, code: str) -> None:
    result = evaluate_playbook(payload(), price)
    assert result["status_code"] == code


def test_unset_and_missing_price_states() -> None:
    unset = evaluate_playbook(None, 3000)
    assert unset["status_code"] == "unset"
    assert unset["current_price"] == 3000
    assert evaluate_playbook(payload(), None)["status_code"] == "no_price"


def test_invalid_percent_and_target_order_are_rejected(tmp_path: Path) -> None:
    db = tmp_path / "invalid.db"
    init_db(db)
    stock = get_stock("5801.T", db)
    assert stock
    invalid = payload()
    invalid["trailing_stop_percent"] = 101
    with pytest.raises(ValueError, match="100以下"):
        save_playbook(int(stock["id"]), invalid, db)
    invalid = payload()
    invalid["target_price_1"] = 5000
    with pytest.raises(ValueError, match="順に設定"):
        save_playbook(int(stock["id"]), invalid, db)


def test_rows_are_enriched_and_prompt_contains_rules(tmp_path: Path) -> None:
    db = tmp_path / "enrich.db"
    init_db(db)
    stock = get_stock("5801.T", db)
    assert stock
    save_playbook(int(stock["id"]), payload(), db)
    rows = enrich_rows_with_playbooks(
        [{**stock, "current_price": 3400}], db
    )
    assert rows[0]["playbook_status"] == "利確①まで5%以内"
    assert rows[0]["playbook_target_distance"] == 100
    prompt = format_playbook_for_prompt(rows[0]["investment_playbook"])
    for text in ("買った理由", "投資テーマ", "利確①", "損切り価格", "売却条件"):
        assert text in prompt
    assert "None" not in prompt
