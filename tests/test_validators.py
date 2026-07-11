"""Tests for validators."""

from __future__ import annotations

import pytest

from utils.validators import normalize_ticker, validate_non_negative_float, validate_non_negative_int, validate_stock_payload
import pandas as pd

from components.forms import export_csv, import_csv_rows
from services.database import get_stock, init_db


def test_normalize_ticker() -> None:
    assert normalize_ticker("5801") == "5801.T"
    assert normalize_ticker("5801.T") == "5801.T"
    assert normalize_ticker("285A") == "285A.T"
    assert normalize_ticker("285a.t") == "285A.T"


def test_invalid_ticker() -> None:
    with pytest.raises(ValueError):
        normalize_ticker("abc")
    with pytest.raises(ValueError):
        normalize_ticker("28AA")
    with pytest.raises(ValueError):
        normalize_ticker("285A.T.T")


def test_alphanumeric_ticker_can_be_registered(tmp_path) -> None:
    db = tmp_path / "test.db"
    init_db(db)
    from services.database import add_stock

    add_stock({"ticker": "285A", "company_name": "キオクシアホールディングス", "category": "監視銘柄"}, db)
    assert get_stock("285A.T", db)["company_name"] == "キオクシアホールディングス"


def test_price_validation() -> None:
    assert validate_non_negative_float("", "価格") == 0
    assert validate_non_negative_float("12.5", "価格") == 12.5
    with pytest.raises(ValueError):
        validate_non_negative_float("-1", "価格")


def test_shares_validation() -> None:
    assert validate_non_negative_int("", "株数") == 0
    assert validate_non_negative_int("10", "株数") == 10
    with pytest.raises(ValueError):
        validate_non_negative_int("-1", "株数")


def test_csv_payload_validation() -> None:
    payload = validate_stock_payload({"ticker": "5801", "company_name": "古河", "category": "監視銘柄", "is_holding": False})
    assert payload["ticker"] == "5801.T"
    assert payload["shares"] == 0


def test_csv_export_has_utf8_bom() -> None:
    exported = export_csv([{"ticker": "5801.T", "company_name": "古河電気工業", "category": "監視銘柄"}])
    assert exported.startswith(b"\xef\xbb\xbf")


def test_csv_import_inserts_valid_rows(tmp_path) -> None:
    db = tmp_path / "test.db"
    init_db(db)
    df = pd.DataFrame(
        [
            {
                "ticker": "7203",
                "company_name": "トヨタ",
                "category": "監視銘柄",
                "is_holding": "false",
                "shares": "0",
                "average_price": "0",
                "buy_watch_price": "1000",
                "memo": "csv import",
            }
        ]
    )
    from components import forms

    original_upsert = forms.upsert_stock
    forms.upsert_stock = lambda payload, update_existing: original_upsert(payload, update_existing, db_path=db)
    try:
        result = import_csv_rows(df, update_existing=True)
    finally:
        forms.upsert_stock = original_upsert
    assert result["inserted"] == 1
    assert result["failed"] == 0
    assert get_stock("7203.T", db)["company_name"] == "トヨタ"
