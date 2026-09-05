"""UI smoke tests for theme categories and the user score ranking."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parents[2]


def _frame() -> pd.DataFrame:
    index = pd.date_range("2026-01-01", periods=100, freq="B")
    values = pd.Series(range(100), index=index, dtype=float) + 1000
    return pd.DataFrame({"Open": values, "High": values + 10, "Low": values - 10, "Close": values, "Volume": 1000}, index=index)


def test_category_and_score_pages_load(ui_db, monkeypatch) -> None:
    monkeypatch.setattr("services.stock_data.fetch_stock_history", lambda *args, **kwargs: _frame())
    categories = AppTest.from_file(str(ROOT / "pages" / "11_テーマ管理.py"), default_timeout=60).run(timeout=60)
    assert not categories.exception
    scores = AppTest.from_file(str(ROOT / "pages" / "12_オレ株スコア.py"), default_timeout=60).run(timeout=60)
    assert not scores.exception
