"""Tests for earnings CRUD, date rules, and CSV."""

from __future__ import annotations

import io
import sqlite3
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from services.database import get_stock, init_db
from services.earnings import add_earnings, delete_earnings, earnings_date_info, earnings_form_date_value, export_earnings_csv, import_earnings_csv, list_earnings, update_earnings


@pytest.mark.parametrize("offset,status,label", [(0,"本日決算","今日"),(1,"明日決算","明日"),(3,"直前","あと3日"),(7,"今週","あと7日"),(14,"2週間以内","あと14日"),(30,"1か月以内","あと30日"),(31,"先予定","30日超"),(-1,"発表済み","発表済み")])
def test_earnings_date_status(offset: int, status: str, label: str) -> None:
    today = date(2026, 12, 31)
    target = date.fromordinal(today.toordinal() + offset)
    info = earnings_date_info(target, today)
    assert info["days_until"] == offset
    assert info["earnings_status"] == status
    assert info["days_label"] == label


def test_earnings_date_missing_and_year_boundary() -> None:
    assert earnings_date_info(None, date(2026, 12, 31))["days_label"] == "日付未確認"
    assert earnings_date_info("2027-01-02", date(2026, 12, 31))["days_until"] == 2


def test_earnings_crud_and_duplicate(tmp_path: Path) -> None:
    db = tmp_path / "test.db"; init_db(db)
    stock = get_stock("5801.T", db)
    payload = {"stock_id": stock["id"], "fiscal_year": 2027, "fiscal_quarter": "Q1", "earnings_date": "2026-07-20", "announcement_time": "15:00", "date_status": "予定", "memo": "確認"}
    event_id = add_earnings(payload, db)
    with pytest.raises(sqlite3.IntegrityError): add_earnings(payload, db)
    update_earnings(event_id, {**payload, "date_status": "確定"}, db)
    assert list_earnings(db)[0]["date_status"] == "確定"
    init_db(db)
    assert list_earnings(db)[0]["date_status"] == "確定"
    delete_earnings(event_id, db)
    assert list_earnings(db) == []
    with pytest.raises(ValueError): delete_earnings(event_id, db)


def test_earnings_csv_bom_import_and_errors(tmp_path: Path) -> None:
    db = tmp_path / "test.db"; init_db(db)
    frame = pd.DataFrame([
        {"ticker":"5801.T","fiscal_year":"2027","fiscal_quarter":"Q1","earnings_date":"2026-07-20","announcement_time":"15:00","date_status":"予定","memo":""},
        {"ticker":"9999.T","fiscal_year":"2027","fiscal_quarter":"Q1","earnings_date":"bad","announcement_time":"","date_status":"予定","memo":""},
    ])
    result = import_earnings_csv(frame, True, db)
    assert (result["inserted"], result["failed"]) == (1, 1)
    exported = export_earnings_csv(list_earnings(db))
    assert exported.startswith(b"\xef\xbb\xbf")
    assert "5801.T" in exported.decode("utf-8-sig")


def test_invalid_date_is_rejected(tmp_path: Path) -> None:
    db = tmp_path / "test.db"; init_db(db)
    stock = get_stock("5801.T", db)
    with pytest.raises(ValueError):
        add_earnings({"stock_id":stock["id"],"fiscal_year":2027,"fiscal_quarter":"Q1","earnings_date":"2026-02-30","date_status":"予定"}, db)


def test_unconfirmed_earnings_can_be_saved_without_date(tmp_path: Path) -> None:
    db = tmp_path / "test.db"; init_db(db)
    stock = get_stock("5801.T", db)
    add_earnings({"stock_id":stock["id"],"fiscal_year":2027,"fiscal_quarter":"Q1","earnings_date":None,"date_status":"未確認"}, db)
    event = list_earnings(db)[0]
    assert event["date_status"] == "未確認"
    assert event["earnings_date"] is None


@pytest.mark.parametrize("status", ["予定", "確定"])
def test_confirmed_or_planned_earnings_require_date(tmp_path: Path, status: str) -> None:
    db = tmp_path / "test.db"; init_db(db)
    stock = get_stock("5801.T", db)
    with pytest.raises(ValueError, match="決算日を入力"):
        add_earnings({"stock_id":stock["id"],"fiscal_year":2027,"fiscal_quarter":"Q1","earnings_date":None,"date_status":status}, db)


def test_earnings_status_transitions_control_date(tmp_path: Path) -> None:
    db = tmp_path / "test.db"; init_db(db)
    stock = get_stock("5801.T", db)
    payload = {"stock_id":stock["id"],"fiscal_year":2027,"fiscal_quarter":"Q1","earnings_date":None,"date_status":"未確認"}
    event_id = add_earnings(payload, db)
    with pytest.raises(ValueError, match="決算日を入力"):
        update_earnings(event_id, {**payload, "date_status":"予定"}, db)
    update_earnings(event_id, {**payload, "date_status":"予定", "earnings_date":"2026-08-01"}, db)
    update_earnings(event_id, {**payload, "date_status":"未確認", "earnings_date":"2026-08-01"}, db)
    assert list_earnings(db)[0]["earnings_date"] is None


def test_unconfirmed_edit_form_value_does_not_default_to_today() -> None:
    assert earnings_form_date_value("未確認", None) is None
    assert earnings_form_date_value("未確認", "2026-08-01") is None


def test_csv_allows_unconfirmed_empty_date(tmp_path: Path) -> None:
    db = tmp_path / "test.db"; init_db(db)
    frame = pd.DataFrame([{"ticker":"5801.T","fiscal_year":"2027","fiscal_quarter":"Q1","earnings_date":"","announcement_time":"","date_status":"未確認","memo":""}])
    result = import_earnings_csv(frame, True, db)
    assert result["inserted"] == 1 and result["failed"] == 0
    assert list_earnings(db)[0]["earnings_date"] is None
