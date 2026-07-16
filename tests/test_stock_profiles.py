"""Company profile candidate tests without live yfinance calls."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from services.database import connect, get_stock, init_db
from services.stock_profiles import (
    list_profile_candidates,
    review_profile_candidate,
    run_profile_refresh,
)


class Provider:
    name = "mock"

    def fetch(self, ticker: str) -> dict[str, str]:
        if ticker == "6976.T":
            raise RuntimeError("temporary")
        return {
            "company_name": "外部会社名",
            "company_alias": "外部略称",
            "market": "Tokyo",
            "industry": "Technology",
            "retrieved_at": "2026-07-16T09:00:00+09:00",
        }


def test_profile_candidates_never_overwrite_stocks(tmp_path: Path) -> None:
    db = tmp_path / "test.db"
    init_db(db)
    before = get_stock("5801.T", db)
    result = run_profile_refresh(Provider(), ticker="5801.T", db_path=db)
    after = get_stock("5801.T", db)
    assert result.inserted == 1
    assert after == before
    assert list_profile_candidates(db_path=db)[0]["company_name"] == "外部会社名"


def test_profile_partial_failure_continues(tmp_path: Path) -> None:
    db = tmp_path / "test.db"
    init_db(db)
    result = run_profile_refresh(Provider(), limit=3, db_path=db, sleep=lambda _seconds: None)
    assert result.processed == 3
    assert result.failed == 1
    assert result.inserted == 2


def test_profile_dry_run_keeps_candidate_table_empty(tmp_path: Path) -> None:
    db = tmp_path / "test.db"
    init_db(db)
    result = run_profile_refresh(Provider(), ticker="5801.T", dry_run=True, db_path=db)
    with sqlite3.connect(db) as conn:
        count = conn.execute("SELECT COUNT(*) FROM stock_profile_candidates").fetchone()[0]
    assert result.inserted == 1
    assert count == 0


def create_candidate(db: Path) -> int:
    run_profile_refresh(Provider(), ticker="5801.T", db_path=db)
    return int(list_profile_candidates(db_path=db)[0]["id"])


def test_profile_candidate_item_approval_is_atomic(tmp_path: Path) -> None:
    db = tmp_path / "test.db"
    init_db(db)
    candidate_id = create_candidate(db)
    before = get_stock("5801.T", db)
    result = review_profile_candidate(
        candidate_id,
        "approve",
        approved_fields=["market", "industry"],
        db_path=db,
    )
    after = get_stock("5801.T", db)
    assert result["status"] == "approved"
    assert after["company_name"] == before["company_name"]
    assert after["market"] == "Tokyo"
    assert after["industry"] == "Technology"


def test_profile_candidate_all_fields_hold_and_reject(tmp_path: Path) -> None:
    db = tmp_path / "test.db"
    init_db(db)
    held_id = create_candidate(db)
    assert review_profile_candidate(held_id, "hold", db_path=db)["status"] == "held"
    result = review_profile_candidate(
        held_id,
        "approve",
        approved_fields=["company_name", "company_alias", "market", "industry"],
        db_path=db,
    )
    assert result["status"] == "approved"
    assert get_stock("5801.T", db)["company_alias"] == "外部略称"

    with connect(db) as conn:
        conn.execute(
            "UPDATE stock_profile_candidates SET fingerprint=fingerprint || '-old' WHERE id=?",
            (held_id,),
        )
    rejected_id = create_candidate(db)
    assert review_profile_candidate(rejected_id, "reject", db_path=db)["status"] == "rejected"
    with pytest.raises(ValueError, match="確認済み"):
        review_profile_candidate(
            rejected_id,
            "approve",
            approved_fields=["market"],
            db_path=db,
        )


def test_profile_approval_rolls_back_stock_update(tmp_path: Path) -> None:
    db = tmp_path / "test.db"
    init_db(db)
    candidate_id = create_candidate(db)
    before = get_stock("5801.T", db)
    with connect(db) as conn:
        conn.execute(
            """CREATE TRIGGER fail_profile_review
            BEFORE UPDATE OF review_status ON stock_profile_candidates
            WHEN NEW.review_status='approved'
            BEGIN
                SELECT RAISE(ABORT, 'forced review failure');
            END"""
        )
    with pytest.raises(sqlite3.IntegrityError):
        review_profile_candidate(
            candidate_id,
            "approve",
            approved_fields=["market"],
            db_path=db,
        )
    assert get_stock("5801.T", db) == before
    assert list_profile_candidates(db_path=db)[0]["review_status"] == "pending"
