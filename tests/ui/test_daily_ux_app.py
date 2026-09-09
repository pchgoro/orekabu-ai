"""Dashboard briefing and mobile-priority AppTest coverage."""

from pathlib import Path

from streamlit.testing.v1 import AppTest

from services.automation import JobResult, finish_run, start_run
from services.database import add_stock, get_stock, load_settings, save_settings
from services.earnings import add_earnings, japan_today
from services.news import save_article
from services.news_providers.base import NewsItem

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


def test_dashboard_renders_grouped_focus_reasons_and_profile_cta(ui_db, monkeypatch) -> None:
    """The real dashboard path must keep grouped reasons and profile navigation."""
    import pandas as pd

    index = pd.date_range("2026-01-01", periods=100, freq="B")
    values = pd.Series(range(100), index=index, dtype=float) + 1000
    frame = pd.DataFrame(
        {"Open": values, "High": values + 10, "Low": values - 10, "Close": values, "Volume": 1000},
        index=index,
    )
    monkeypatch.setattr("services.stock_data.fetch_stock_history", lambda *args, **kwargs: frame)

    from services.database import get_stock

    stock = get_stock("5801.T", ui_db)
    assert stock is not None
    add_earnings(
        {
            "stock_id": stock["id"],
            "fiscal_year": 2026,
            "fiscal_quarter": "Q1",
            "earnings_date": japan_today().isoformat(),
            "date_status": "予定",
        },
        ui_db,
    )
    save_article(
        NewsItem(title="5801.T 古河電気工業の重要ニュース", published_at=japan_today().isoformat()),
        metadata={"importance": "高", "category": "業績"},
        db_path=ui_db,
    )

    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=60).run(timeout=60)

    assert not at.exception
    assert any("本日決算" in item.value for item in at.markdown)
    captions = [item.value for item in at.caption]
    assert any("確認理由:" in value and "重要ニュースを確認" in value for value in captions)
    assert any(button.label == "確認する" for button in at.button)


def test_dashboard_focus_shows_only_top_three_of_four_runtime_candidates(ui_db, monkeypatch) -> None:
    """The dashboard's morning block must keep its three-item display boundary."""
    import pandas as pd

    index = pd.date_range("2026-01-01", periods=100, freq="B")
    values = pd.Series(range(100), index=index, dtype=float) + 1000
    frame = pd.DataFrame(
        {"Open": values, "High": values + 10, "Low": values - 10, "Close": values, "Volume": 1000},
        index=index,
    )
    monkeypatch.setattr("services.stock_data.fetch_stock_history", lambda *args, **kwargs: frame)

    for ticker, company_name in (("5801.T", "古河電気工業"), ("6976.T", "太陽誘電"), ("4062.T", "イビデン")):
        stock = get_stock(ticker, ui_db)
        assert stock is not None
        add_earnings(
            {
                "stock_id": stock["id"],
                "fiscal_year": 2026,
                "fiscal_quarter": "Q1",
                "earnings_date": japan_today().isoformat(),
                "date_status": "予定",
            },
            ui_db,
        )
    extra_id = add_stock(
        {"ticker": "9999.T", "company_name": "追加テスト社", "category": "監視銘柄"},
        ui_db,
    )
    add_earnings(
        {
            "stock_id": extra_id,
            "fiscal_year": 2026,
            "fiscal_quarter": "Q1",
            "earnings_date": japan_today().isoformat(),
            "date_status": "予定",
        },
        ui_db,
    )

    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=60).run(timeout=60)

    assert not at.exception
    assert sum(button.label == "確認する" for button in at.button) == 3


def test_dashboard_missing_ticker_task_keeps_normal_page_link(ui_db, monkeypatch) -> None:
    """A global task must not be misrouted to the company-profile button."""
    import streamlit as st

    page_links: list[tuple[str, str]] = []
    monkeypatch.setattr(st, "page_link", lambda page, label, **kwargs: page_links.append((page, label)))
    profile_calls: list[tuple[str, str]] = []
    monkeypatch.setattr(
        "components.daily.company_profile_button",
        lambda ticker, label, key: profile_calls.append((str(ticker), label)),
    )
    run_id = start_run("test-failed-run", False, 1, ui_db)
    finish_run(run_id, [JobResult(processed=1, failed=1, message="fixture failure")], ui_db)

    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=60).run(timeout=60)
    assert not at.exception
    assert ("pages/6_設定.py", "確認する") in page_links
    assert all(ticker for ticker, _label in profile_calls)
