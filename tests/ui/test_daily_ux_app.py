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
    assert any(item.value == "今日のブリーフィング" for item in at.subheader)
    assert any(item.value == "今日やること" for item in at.subheader)
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
    settings.update({"dashboard_display_mode": "標準", "hide_zero_sections": False})
    save_settings(settings)
    standard = AppTest.from_file(str(ROOT / "app.py"), default_timeout=60).run(timeout=60)
    assert any(item.value == "ポートフォリオ概要" for item in standard.subheader)
    assert any(item.label == "本日決算" and item.value == "0" for item in standard.metric)
    assert not standard.exception

    settings = load_settings()
    settings.update({"dashboard_display_mode": "コンパクト", "hide_zero_sections": True})
    save_settings(settings)
    compact = AppTest.from_file(str(ROOT / "app.py"), default_timeout=60).run(timeout=60)
    assert not any(item.value == "ポートフォリオ概要" for item in compact.subheader)
    assert not any(item.label == "本日決算" for item in compact.metric)
    assert not compact.exception
