"""Dashboard briefing and mobile-priority AppTest coverage."""

from pathlib import Path

from streamlit.testing.v1 import AppTest

from services.database import load_settings, save_settings

ROOT = Path(__file__).resolve().parents[2]


def test_dashboard_shows_briefing_and_tasks(ui_db, monkeypatch) -> None:
    import pandas as pd
    index=pd.date_range("2026-01-01",periods=100,freq="B"); values=pd.Series(range(100),index=index,dtype=float)+1000
    frame=pd.DataFrame({"Open":values,"High":values+10,"Low":values-10,"Close":values,"Volume":1000},index=index)
    monkeypatch.setattr("services.stock_data.fetch_stock_history",lambda *args,**kwargs:frame)
    at=AppTest.from_file(str(ROOT/"app.py"),default_timeout=60).run(timeout=60)
    headings = {item.value for item in at.subheader}
    assert {"今日やること", "重要イベント", "最新材料"}.issubset(headings)
    assert not at.exception


def test_mobile_priority_target_pages_use_cards_without_exceptions(ui_db, monkeypatch) -> None:
    import pandas as pd
    index=pd.date_range("2026-01-01",periods=100,freq="B"); values=pd.Series(range(100),index=index,dtype=float)+1000
    frame=pd.DataFrame({"Open":values,"High":values+10,"Low":values-10,"Close":values,"Volume":1000},index=index)
    monkeypatch.setattr("services.stock_data.fetch_stock_history",lambda *args,**kwargs:frame)
    settings=load_settings(); settings["mobile_priority_display"]=True; save_settings(settings)
    files=[ROOT/"app.py",ROOT/"pages"/"1_保有株.py",ROOT/"pages"/"2_監視銘柄.py",ROOT/"pages"/"5_決算.py",ROOT/"pages"/"7_ニュース.py"]
    for file in files:
        at=AppTest.from_file(str(file),default_timeout=60).run(timeout=60)
        assert not at.exception, file


def test_dashboard_standard_compact_and_zero_visibility_settings(ui_db, monkeypatch) -> None:
    """Dashboard presentation settings must be applied from the temporary DB."""
    import pandas as pd

    index = pd.date_range("2026-01-01", periods=100, freq="B")
    values = pd.Series(range(100), index=index, dtype=float) + 1000
    frame = pd.DataFrame(
        {"Open": values, "High": values + 10, "Low": values - 10, "Close": values, "Volume": 1000},
        index=index,
    )
    monkeypatch.setattr("services.stock_data.fetch_stock_history", lambda *args, **kwargs: frame)

    settings = load_settings()
    settings.update({"dashboard_display_mode": "標準", "hide_zero_sections": False, "display_density": "ゆったり"})
    save_settings(settings)
    standard = AppTest.from_file(str(ROOT / "app.py"), default_timeout=60).run(timeout=60)
    assert any(item.value == "ポートフォリオ概要" for item in standard.subheader)
    assert load_settings()["display_density"] == "ゆったり"
    assert not standard.exception

    settings = load_settings()
    settings.update({"dashboard_display_mode": "コンパクト", "hide_zero_sections": True, "display_density": "コンパクト"})
    save_settings(settings)
    compact = AppTest.from_file(str(ROOT / "app.py"), default_timeout=60).run(timeout=60)
    assert not any(item.value == "ポートフォリオ概要" for item in compact.subheader)
    assert not compact.exception


def test_dashboard_empty_focus_blocks_are_safe(ui_db, monkeypatch) -> None:
    """The three morning blocks must render even when all sources are empty."""
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=60).run(timeout=60)
    headings = {item.value for item in at.subheader}
    assert {"今日やること", "重要イベント", "最新材料"}.issubset(headings)
    assert not at.exception
