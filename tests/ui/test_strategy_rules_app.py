"""Strategy tags and rule UI coverage using an isolated database."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
from streamlit.testing.v1 import AppTest

from services.database import connect, get_stock
from services.strategy_rules import (
    list_tags,
    replace_stock_tags,
    save_rule_set,
)

ROOT = Path(__file__).resolve().parents[2]


def _price_frame() -> pd.DataFrame:
    index = pd.date_range("2026-01-01", periods=100, freq="B")
    values = pd.Series(range(100), index=index, dtype=float) + 1000
    return pd.DataFrame(
        {
            "Open": values,
            "High": values + 10,
            "Low": values - 10,
            "Close": values,
            "Volume": 1000,
        },
        index=index,
    )


def test_strategy_page_loads_all_sections(ui_db, monkeypatch) -> None:
    monkeypatch.setattr(
        "services.stock_data.fetch_stock_history",
        lambda *args, **kwargs: _price_frame(),
    )
    at = AppTest.from_file(
        str(ROOT / "pages" / "10_戦略・カテゴリ.py"),
        default_timeout=60,
    ).run(timeout=60)
    assert any(item.value == "戦略・カテゴリ" for item in at.title)
    assert [item.label for item in at.tabs] == [
        "タグ一覧",
        "タグ別銘柄",
        "ルール設定",
        "一括適用",
        "競合確認",
        "集計",
    ]
    assert any(item.label == "タグを保存" for item in at.button)
    assert not at.exception


def test_holdings_and_company_profile_show_strategy_state(
    ui_db, monkeypatch,
) -> None:
    stock = get_stock("5801.T")
    assert stock
    with connect() as conn:
        conn.execute(
            """UPDATE stocks SET is_holding=1,category='保有株',
            shares=100,average_price=1000 WHERE id=?""",
            (int(stock["id"]),),
        )
    ai = next(
        row for row in list_tags()
        if row["name"] == "AI" and row["tag_group"] == "theme"
    )
    replace_stock_tags(int(stock["id"]), [int(ai["id"])])
    save_rule_set(
        int(ai["id"]),
        {
            "stop_loss_type": "percent_from_average_price",
            "stop_loss_value": 8,
            "take_profit_type": "percent_from_average_price",
            "take_profit_value": 30,
            "add_position_type": "percent_from_average_price",
            "add_position_value": 12,
            "priority": 10,
        },
    )
    monkeypatch.setattr(
        "services.stock_data.fetch_stock_history",
        lambda *args, **kwargs: _price_frame(),
    )
    holdings = AppTest.from_file(
        str(ROOT / "pages" / "1_保有株.py"), default_timeout=60
    ).run(timeout=60)
    rendered = " ".join(item.value for item in holdings.markdown)
    assert "戦略タグ" in rendered
    assert "AI" in rendered
    assert not holdings.exception

    profile = AppTest.from_file(
        str(ROOT / "pages" / "9_企業カルテ.py"), default_timeout=60
    ).run(timeout=60)
    assert any(
        item.value == "戦略タグ・共通ルール"
        for item in profile.subheader
    )
    assert any(item.label == "タグを保存" for item in profile.button)
    assert not profile.exception


def test_strategy_page_handles_no_active_tags(ui_db, monkeypatch) -> None:
    with connect() as conn:
        conn.execute("UPDATE strategy_tags SET is_active=0")
    monkeypatch.setattr(
        "services.stock_data.fetch_stock_history",
        lambda *args, **kwargs: _price_frame(),
    )
    at = AppTest.from_file(
        str(ROOT / "pages" / "10_戦略・カテゴリ.py"),
        default_timeout=60,
    ).run(timeout=60)
    assert not at.exception
