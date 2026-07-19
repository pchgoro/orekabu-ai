"""Investment playbook display coverage for holdings and company profile."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
from streamlit.testing.v1 import AppTest

from services.database import connect, get_stock
from services.investment_playbooks import save_playbook

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


def test_holdings_show_compact_rule_state_and_distances(
    ui_db, monkeypatch,
) -> None:
    stock = get_stock("5801.T")
    assert stock
    with connect() as conn:
        conn.execute(
            """UPDATE stocks SET is_holding=1,category='保有株',
            shares=100,average_price=900 WHERE id=?""",
            (int(stock["id"]),),
        )
    save_playbook(
        int(stock["id"]),
        {
            "target_price_1": 1150,
            "target_price_1_sell_percent": 50,
            "stop_loss_price": 1000,
            "holding_period": "中期",
        },
    )
    monkeypatch.setattr(
        "services.stock_data.fetch_stock_history",
        lambda *args, **kwargs: _price_frame(),
    )
    at = AppTest.from_file(
        str(ROOT / "pages" / "1_保有株.py"), default_timeout=60
    ).run(timeout=60)
    rendered = " ".join(item.value for item in at.markdown)
    assert "利確①まで5%以内" in rendered
    assert "利確まで残り" in rendered
    assert "損切りまで残り" in rendered
    assert not at.exception
