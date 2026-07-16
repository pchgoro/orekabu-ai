"""Disclosure page smoke coverage with an isolated SQLite database."""

from pathlib import Path

from streamlit.testing.v1 import AppTest

from services.disclosures import save_disclosure

ROOT = Path(__file__).resolve().parents[2]


def test_disclosure_page_loads_and_shows_registered_item(ui_db) -> None:
    save_disclosure({
        "ticker": "5801.T", "disclosure_type": "業績予想修正", "title": "通期予想の修正",
        "disclosed_at": "2026-07-13T15:00", "importance": "高",
    })
    at = AppTest.from_file(str(ROOT / "pages" / "8_適時開示.py"), default_timeout=60).run(timeout=60)
    assert any(item.value == "適時開示" for item in at.title)
    assert not at.exception


def test_dashboard_shows_disclosure_metrics(ui_db, monkeypatch) -> None:
    import pandas as pd

    index = pd.date_range("2026-01-01", periods=100, freq="B")
    values = pd.Series(range(100), index=index, dtype=float) + 1000
    frame = pd.DataFrame({"Open": values, "High": values + 10, "Low": values - 10, "Close": values, "Volume": 1000}, index=index)
    monkeypatch.setattr("services.stock_data.fetch_stock_history", lambda *args, **kwargs: frame)
    save_disclosure({
        "ticker": "5801.T", "disclosure_type": "決算短信", "title": "決算短信",
        "disclosed_at": "2026-07-13T15:00", "importance": "高",
    })
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=60).run(timeout=60)
    labels = {item.label for item in at.metric}
    assert {"今日の開示", "未読開示", "重要度高", "保有株開示"}.issubset(labels)
    assert not at.exception
