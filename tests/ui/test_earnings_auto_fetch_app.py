"""AppTest coverage for Phase 2B fetch, review, history, and CSV UI."""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

import pandas as pd
from streamlit.testing.v1 import AppTest

from services.database import get_stock
from services.earnings import add_earnings, list_earnings
from services.earnings_candidates import (
    add_fetch_result, finish_fetch_run, list_candidates, review_candidate,
    save_candidate, start_fetch_run,
)
from services.earnings_providers.base import EarningsFetchResult

ROOT = Path(__file__).resolve().parents[2]
EARNINGS_PAGE = next((ROOT / "pages").glob("5_*.py"))


def fetched(day: date = date(2099, 1, 10)) -> EarningsFetchResult:
    return EarningsFetchResult(
        ticker="5801.T", earnings_date=day, candidate_dates=(day,), source_name="mock",
        source_reference="unit", retrieved_at=datetime.now().astimezone().isoformat(timespec="seconds"),
        confidence="low", fiscal_year=2099, fiscal_quarter="Q1",
    )


def app() -> AppTest:
    return AppTest.from_file(str(EARNINGS_PAGE), default_timeout=60).run(timeout=60)


def button(at: AppTest, label: str):
    return next(item for item in at.button if item.label == label)


def test_individual_fetch_candidate_detail_and_approval(ui_db, monkeypatch) -> None:
    from services.earnings_providers.yfinance_provider import YFinanceEarningsProvider
    monkeypatch.setattr(YFinanceEarningsProvider, "fetch_next_earnings", lambda self, ticker: fetched())
    at = app()
    assert any(item.label == "決算日自動取得" for item in at.tabs)
    button(at, "決算候補を取得").click().run(timeout=60)
    assert len(at.exception) == 0
    assert len(list_candidates()) == 1
    assert list_earnings() == []
    rendered = " ".join(frame.value.to_string() for frame in at.dataframe)
    assert "新規" in rendered and "2099-01-10" in rendered
    assert "現在" in rendered and "候補" in rendered
    button(at, "承認").click().run(timeout=60)
    assert list_earnings()[0]["earnings_date"] == "2099-01-10"
    assert list_candidates()[0]["review_status"] == "approved"


def test_hold_and_reject_do_not_create_formal_events(ui_db) -> None:
    stock = get_stock("5801.T")
    _, first, _ = save_candidate(stock, fetched(), date(2099, 1, 10))
    at = app()
    button(at, "保留").click().run(timeout=60)
    assert list_candidates()[0]["review_status"] == "held"
    assert list_earnings() == []
    _, second, _ = save_candidate(stock, fetched(date(2099, 1, 11)), date(2099, 1, 11))
    at = app()
    button(at, "却下").click().run(timeout=60)
    statuses = {row["id"]: row["review_status"] for row in list_candidates()}
    assert statuses[first] == "held" and statuses[second] == "rejected"
    assert list_earnings() == []


def test_confirmed_event_requires_checkbox_before_update(ui_db) -> None:
    stock = get_stock("5801.T")
    add_earnings({"stock_id":stock["id"],"fiscal_year":2099,"fiscal_quarter":"Q1","earnings_date":"2099-01-10","date_status":"確定"})
    save_candidate(stock, fetched(date(2099, 1, 11)), date(2099, 1, 11))
    at = app()
    button(at, "承認").click().run(timeout=60)
    assert any("追加確認" in item.value for item in at.error)
    assert list_earnings()[0]["earnings_date"] == "2099-01-10"
    confirmation = next(item for item in at.checkbox if item.label.startswith("既存の確定データ"))
    confirmation.check().run(timeout=60)
    button(confirmation.root, "承認").click().run(timeout=60)
    assert list_earnings()[0]["earnings_date"] == "2099-01-11"


def test_fetch_history_and_failed_ticker_are_visible(ui_db) -> None:
    stock = get_stock("5801.T")
    run_id = start_fetch_run("mock", 1)
    add_fetch_result(run_id, stock, "failed", error_code="timeout", error_message="タイムアウト")
    finish_fetch_run(run_id, {"success":0,"candidates":0,"unchanged":0,"failed":1}, ["5801.T: タイムアウト"])
    at = app()
    text = " ".join(frame.value.fillna("").to_string() for frame in at.dataframe)
    assert "failed" in text and "timeout" in text and "5801.T" in text
    assert any("失敗銘柄" in item.value for item in at.info)


def test_candidate_csv_preview_and_import_never_updates_formal_events(ui_db) -> None:
    content = pd.DataFrame([{
        "ticker":"5801.T","earnings_date":"2099-02-01","announcement_time":"15:00",
        "fiscal_year":"2099","fiscal_quarter":"Q1","source_name":"調査CSV",
        "source_reference":"公式確認前","confidence":"medium","memo":"日本語メモ",
    }]).to_csv(index=False).encode("utf-8-sig")
    at = app()
    uploader = next(item for item in at.file_uploader if item.label == "決算候補CSV")
    at = uploader.upload("candidates.csv", content, "text/csv").run(timeout=60)
    assert any("有効行: 1件" in item.value for item in at.markdown)
    button(at, "候補CSVをインポート").click().run(timeout=60)
    assert len(list_candidates()) == 1
    assert list_earnings() == []


def test_planned_form_without_date_shows_japanese_error(ui_db) -> None:
    at = app()
    at = button(at, "決算イベントを登録").click().run(timeout=60)
    assert any("決算日を入力" in item.value for item in at.error)


def test_phase2a_earnings_form_create_edit_delete(ui_db) -> None:
    at = app()
    create_status = next(item for item in at.selectbox if item.label == "日付状態")
    at = create_status.select(create_status.options[-1]).run(timeout=60)
    at = button(at, "決算イベントを登録").click().run(timeout=60)
    assert not at.error, [item.value for item in at.error]
    assert len(list_earnings()) == 1
    at = app()
    years = [item for item in at.number_input if item.label == "対象年度"]
    years[-1].set_value(int(years[-1].value) + 1)
    at = button(at, "更新").click().run(timeout=60)
    assert not at.error, [item.value for item in at.error]
    assert list_earnings()[0]["fiscal_year"] == date.today().year + 1
    at = app()
    confirmation = next(item for item in at.checkbox if item.label == "削除することを確認しました")
    at = confirmation.check().run(timeout=60)
    button(at, "決算イベントを削除").click().run(timeout=60)
    assert list_earnings() == []
