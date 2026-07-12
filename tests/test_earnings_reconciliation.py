"""Tests for candidate comparison and manual confirmed-data protection."""

from __future__ import annotations

from datetime import date

import pytest

from services.earnings_reconciliation import candidate_diff, reconcile_candidate


def event(**overrides):
    base = {"id": 1, "fiscal_year": 2099, "fiscal_quarter": "Q1", "earnings_date": "2099-01-10", "announcement_time": "15:00", "date_status": "予定"}
    return {**base, **overrides}


def test_reconciliation_statuses() -> None:
    assert reconcile_candidate(date(2099,1,10),2099,"Q1","15:00",[]).comparison_status == "new"
    assert reconcile_candidate(date(2099,1,10),2099,"Q1","15:00",[event()]).comparison_status == "same"
    assert reconcile_candidate(date(2099,1,11),2099,"Q1","15:00",[event()]).comparison_status == "date_changed"
    assert reconcile_candidate(date(2099,1,10),2099,"Q1","引け後",[event()]).comparison_status == "time_changed"
    assert reconcile_candidate(date(2099,1,10),2099,"Q2","15:00",[event(fiscal_quarter="未設定")]).comparison_status == "quarter_changed"
    assert reconcile_candidate(date(2020,1,1),2020,"Q1","",[]).comparison_status == "past_date"
    assert reconcile_candidate(None,None,"未設定","",[]).comparison_status == "invalid"


def test_multiple_matches_and_confirmed_difference_are_conflicts() -> None:
    assert reconcile_candidate(date(2099,1,10),2099,"Q1","",[event(id=1),event(id=2)]).comparison_status == "conflict"
    result = reconcile_candidate(date(2099,1,11),2099,"Q1","15:00",[event(date_status="確定")])
    assert result.comparison_status == "conflict"
    assert "確定" in result.warning


def test_candidate_diff_has_text_states() -> None:
    rows = candidate_diff({"existing_date":"2099-01-10","candidate_date":"2099-01-11","provider_name":"yfinance"})
    assert any(row["差分"] == "変更あり" for row in rows)
    assert all("None" not in str(row) for row in rows)
