"""Smoke test all existing pages against an isolated DB and mocked prices."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parents[2]


def fake_history() -> pd.DataFrame:
    index=pd.date_range("2026-01-01",periods=100,freq="B")
    values=pd.Series(range(100),index=index,dtype=float)+1000
    return pd.DataFrame({"Open":values,"High":values+10,"Low":values-10,"Close":values,"Volume":1000},index=index)


def test_all_phase1_phase2a_pages_open_without_exceptions(ui_db, monkeypatch) -> None:
    monkeypatch.setattr("services.stock_data.fetch_stock_history",lambda *args,**kwargs:fake_history())
    files=[ROOT/"app.py",*sorted((ROOT/"pages").glob("*.py"))]
    for file in files:
        at=AppTest.from_file(str(file),default_timeout=60).run(timeout=60)
        assert len(at.exception)==0, f"{file}: {[item.value for item in at.exception]}"
