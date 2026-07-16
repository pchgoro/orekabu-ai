"""Official EDINET API v2 metadata tests without external communication."""

from __future__ import annotations

import json
import sqlite3
from datetime import date
from pathlib import Path

import pytest

import services.edinet as edinet_service
from services.database import init_db
from services.edinet import (
    EdinetApiClient,
    api_key_configured,
    classify_document,
    filter_registered_documents,
    list_documents,
    list_fetch_runs,
    lookback_dates,
    normalize_security_code,
    normalize_stock_ticker_code,
    run_edinet_fetch,
    run_edinet_range,
)


class Response:
    """Context-manager response used by the standard-library client."""

    def __init__(self, payload: dict) -> None:
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self) -> bytes:
        return json.dumps(self.payload, ensure_ascii=False).encode("utf-8")


def payload() -> dict:
    return {
        "metadata": {"status": "200"},
        "results": [
            {
                "docID": "S100TEST",
                "edinetCode": "E00001",
                "secCode": "58010",
                "filerName": "テスト提出者",
                "docDescription": "有価証券報告書",
                "submitDateTime": "2026-07-16 15:00",
            },
            {
                "docID": "OTHER",
                "secCode": "99990",
                "docDescription": "臨時報告書",
                "submitDateTime": "2026-07-16 16:00",
            },
        ],
    }


def client() -> EdinetApiClient:
    return EdinetApiClient("secret", opener=lambda *_args, **_kwargs: Response(payload()))


def test_api_key_is_required() -> None:
    with pytest.raises(ValueError, match="EDINET_API_KEY"):
        EdinetApiClient("")


def test_api_key_status_never_exposes_value(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    secret = "do-not-log-this-key"
    monkeypatch.setenv("EDINET_API_KEY", secret)
    assert api_key_configured(tmp_path / ".env") is True
    client_with_key = EdinetApiClient(
        secret, opener=lambda *_args, **_kwargs: Response(payload())
    )
    client_with_key.fetch_documents(date(2026, 7, 16))
    assert secret not in caplog.text


def test_supported_document_classification() -> None:
    assert classify_document("訂正有価証券報告書") == "訂正書類"
    assert classify_document("半期報告書") == "半期報告書"
    assert classify_document("決算短信") is None


def test_numeric_security_code_matching_and_alpha_code_skip() -> None:
    stocks = [
        {"id": 1, "ticker": "5801.T"},
        {"id": 2, "ticker": "285A.T"},
    ]
    documents = [
        {"docID": "NUMERIC", "secCode": "58010", "docDescription": "臨時報告書"},
        {"docID": "ALPHA", "secCode": "285A0", "docDescription": "臨時報告書"},
        {"docID": "MISSING", "secCode": None, "docDescription": "臨時報告書"},
    ]
    matches = filter_registered_documents(documents, stocks)
    assert [row[1]["docID"] for row in matches] == ["NUMERIC"]
    assert normalize_stock_ticker_code("5801.T") == "5801"
    assert normalize_stock_ticker_code("5801") == "5801"
    assert normalize_security_code("58010") == "5801"
    assert normalize_stock_ticker_code("285A.T") == ""
    assert normalize_security_code("285A0") == ""


def test_doc_id_deduplication_and_registered_stock_filter(tmp_path: Path) -> None:
    db = tmp_path / "test.db"
    init_db(db)
    first = run_edinet_fetch(client(), target_date=date(2026, 7, 16), db_path=db)
    second = run_edinet_fetch(client(), target_date=date(2026, 7, 16), db_path=db)
    assert first.inserted == 1
    assert second.duplicates == 1
    documents = list_documents(db_path=db)
    assert [row["doc_id"] for row in documents] == ["S100TEST"]
    assert documents[0]["reference_url"].endswith("?S100TEST")


def test_edinet_dry_run_does_not_write(tmp_path: Path) -> None:
    db = tmp_path / "test.db"
    init_db(db)
    with sqlite3.connect(db) as conn:
        before = {
            table: conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in ("edinet_documents", "edinet_fetch_runs", "edinet_fetch_results")
        }
    result = run_edinet_fetch(
        client(), target_date=date(2026, 7, 16), dry_run=True, db_path=db
    )
    with sqlite3.connect(db) as conn:
        after = {
            table: conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in before
        }
    assert result.inserted == 1
    assert after == before


def test_edinet_partial_failure_is_recorded(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db = tmp_path / "test.db"
    init_db(db)
    stock_documents = payload()
    stock_documents["results"].insert(
        1,
        {
            "docID": "S100FAIL",
            "edinetCode": "E00002",
            "secCode": "69760",
            "filerName": "保存失敗提出者",
            "docDescription": "臨時報告書",
            "submitDateTime": "2026-07-16 15:30",
        },
    )
    partial_client = EdinetApiClient(
        "secret", opener=lambda *_args, **_kwargs: Response(stock_documents)
    )
    original = edinet_service.save_document

    def fail_one(stock, document, document_type, db_path):
        if document["docID"] == "S100FAIL":
            raise RuntimeError("forced save failure")
        return original(stock, document, document_type, db_path)

    monkeypatch.setattr(edinet_service, "save_document", fail_one)
    result = run_edinet_fetch(
        partial_client, target_date=date(2026, 7, 16), db_path=db
    )
    assert result.inserted == 1
    assert result.failed == 1
    assert list_fetch_runs(db_path=db)[0]["status"] == "partial"
    with sqlite3.connect(db) as conn:
        statuses = {
            row[0]
            for row in conn.execute(
                "SELECT status FROM edinet_fetch_results ORDER BY id"
            ).fetchall()
        }
    assert statuses == {"inserted", "failed"}


def test_lookback_dates_cross_date_boundary_and_maximum() -> None:
    assert lookback_dates(date(2026, 1, 2), 3) == [
        date(2026, 1, 2),
        date(2026, 1, 1),
        date(2025, 12, 31),
    ]
    assert len(lookback_dates(date(2026, 7, 16), 365)) == 365
    with pytest.raises(ValueError, match="1から365"):
        lookback_dates(date(2026, 7, 16), 366)


def test_edinet_range_continues_after_date_failure_and_deduplicates(
    tmp_path: Path,
) -> None:
    db = tmp_path / "test.db"
    init_db(db)

    class RangeClient:
        def fetch_documents(self, target_date: date):
            if target_date == date(2026, 7, 15):
                raise RuntimeError("temporary")
            return payload()["results"]

    first = run_edinet_range(
        RangeClient(),
        target_dates=[
            date(2026, 7, 16),
            date(2026, 7, 15),
            date(2026, 7, 14),
        ],
        db_path=db,
        interval_seconds=0,
    )
    second = run_edinet_range(
        RangeClient(),
        target_dates=[date(2026, 7, 16), date(2026, 7, 14)],
        db_path=db,
        interval_seconds=0,
    )
    assert first.inserted == 1
    assert first.duplicates == 1
    assert first.failed == 1
    assert [row["status"] for row in first.details["dates"]] == [
        "completed",
        "failed",
        "completed",
    ]
    assert second.duplicates == 2
    assert len(list_documents(db_path=db)) == 1


def test_edinet_range_dry_run_keeps_db_unchanged(tmp_path: Path) -> None:
    db = tmp_path / "test.db"
    init_db(db)
    with sqlite3.connect(db) as conn:
        before = {
            table: conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in ("edinet_documents", "edinet_fetch_runs", "edinet_fetch_results")
        }
    result = run_edinet_range(
        client(),
        target_dates=[date(2026, 7, 16), date(2026, 7, 15)],
        dry_run=True,
        db_path=db,
        interval_seconds=0,
    )
    with sqlite3.connect(db) as conn:
        after = {
            table: conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in before
        }
    assert result.inserted == 2
    assert after == before
