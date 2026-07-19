"""Company profile Streamlit AppTest coverage."""

from pathlib import Path

import pandas as pd
from streamlit.testing.v1 import AppTest

from components.navigation import COMPANY_PROFILE_REQUESTED_TICKER

ROOT = Path(__file__).resolve().parents[2]


def test_company_profile_page_loads_all_sections(ui_db, monkeypatch) -> None:
    index = pd.date_range("2026-01-01", periods=100, freq="B")
    values = pd.Series(range(100), index=index, dtype=float) + 1000
    frame = pd.DataFrame({"Open": values, "High": values + 10, "Low": values - 10, "Close": values, "Volume": 1000}, index=index)
    monkeypatch.setattr("services.stock_data.fetch_stock_history", lambda *args, **kwargs: frame)
    at = AppTest.from_file(str(ROOT / "pages" / "9_企業カルテ.py"), default_timeout=60).run(timeout=60)
    assert any(item.value == "企業カルテ" for item in at.title)
    headings = [item.value for item in at.subheader]
    for label in ("今日の注意点", "投資ルール", "戦略タグ・共通ルール", "決算", "ニュース", "適時開示", "EDINET", "関連銘柄", "テーマ・投資ストーリー", "メモ", "タイムライン", "ChatGPT分析用プロンプト"):
        assert label in headings
    assert any(item.label == "投資ルールを保存" for item in at.button)
    assert any(item.label == "企業カルテ情報を保存" for item in at.button)
    assert any(item.label == "メモを追加" for item in at.button)
    assert not at.exception


def test_company_metadata_edit_uses_temporary_db(ui_db, monkeypatch) -> None:
    import services.company_profile as company_profile

    monkeypatch.setattr(company_profile, "build_analysis_rows", lambda stocks, settings: [{**stocks[0], "data_status": "データなし", "current_price": None, "change": None, "score": 0}])
    at = AppTest.from_file(str(ROOT / "pages" / "9_企業カルテ.py"), default_timeout=60).run(timeout=60)
    alias = next(item for item in at.text_input if item.label == "略称")
    alias.set_value("古河電工")
    next(item for item in at.button if item.label == "企業情報を保存").click(); at.run(timeout=60)
    assert company_profile.search_companies("古河電工")[0]["company_alias"] == "古河電工"
    assert not at.exception


def test_company_profile_mobile_priority_layout_loads(ui_db, monkeypatch) -> None:
    """The vertical mobile-priority layout must render without an exception."""
    from services.database import load_settings, save_settings

    settings = load_settings()
    settings["mobile_priority_display"] = True
    save_settings(settings)
    monkeypatch.setattr(
        "services.company_profile.build_analysis_rows",
        lambda stocks, app_settings: [
            {
                **stocks[0],
                "data_status": "データなし",
                "current_price": None,
                "change": None,
                "score": 0,
            }
        ],
    )
    at = AppTest.from_file(
        str(ROOT / "pages" / "9_企業カルテ.py"), default_timeout=60
    ).run(timeout=60)
    assert any(item.value == "企業カルテ" for item in at.title)
    assert not at.exception


def test_company_profile_uses_ticker_requested_by_navigation(
    ui_db, monkeypatch,
) -> None:
    monkeypatch.setattr(
        "services.company_profile.build_analysis_rows",
        lambda stocks, app_settings: [
            {
                **stock,
                "data_status": "データなし",
                "current_price": None,
                "change": None,
                "score": 0,
            }
            for stock in stocks
        ],
    )
    at = AppTest.from_file(
        str(ROOT / "pages" / "9_企業カルテ.py"), default_timeout=60
    )
    at.session_state[COMPANY_PROFILE_REQUESTED_TICKER] = "6976.T"
    at.run(timeout=60)
    selected = next(
        item for item in at.selectbox if item.label == "企業を選択"
    )
    assert str(selected.value).startswith("6976.T ")
    assert any(
        item.value.startswith("6976.T ")
        for item in at.subheader
    )
    assert not at.exception
