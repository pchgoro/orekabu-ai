"""Tests for safe candidate-only CSV import."""

from __future__ import annotations

import io
from pathlib import Path

import pandas as pd

from services.database import init_db, load_settings
from services.earnings import list_earnings
from services.earnings_candidates import import_candidate_csv, list_candidates, parse_candidate_csv, validate_candidate_csv_preview


COLUMNS=["ticker","earnings_date","announcement_time","fiscal_year","fiscal_quarter","source_name","source_reference","confidence","memo"]


def test_bom_parse_and_candidate_only_import(tmp_path: Path) -> None:
    db=tmp_path/"test.db"; init_db(db)
    raw=pd.DataFrame([["5801.T","2099-01-10","15:00","2099","Q1","manual-research","ref","medium",""]],columns=COLUMNS).to_csv(index=False).encode("utf-8-sig")
    frame,errors=parse_candidate_csv(io.BytesIO(raw))
    assert not errors
    result=import_candidate_csv(frame,load_settings(db),db)
    assert result["created"]==1 and len(list_candidates(db))==1
    assert list_earnings(db)==[]


def test_csv_invalid_unknown_duplicate_and_past(tmp_path: Path) -> None:
    db=tmp_path/"test.db"; init_db(db); settings=load_settings(db)
    frame=pd.DataFrame([
        ["9999.T","2099-01-10","","2099","Q1","csv","","low",""],
        ["5801.T","bad","","2099","Q1","csv","","low",""],
        ["5801.T","2020-01-10","","2020","Q1","csv","","low",""],
    ],columns=COLUMNS)
    result=import_candidate_csv(frame,settings,db)
    assert result["failed"]==2 and result["created"]==1 and result["warnings"]==1
    duplicate=import_candidate_csv(frame.iloc[[2]],settings,db)
    assert duplicate["duplicate"]==1


def test_csv_preview_separates_invalid_rows(tmp_path: Path) -> None:
    db=tmp_path/"test.db"; init_db(db)
    frame=pd.DataFrame([
        ["5801.T","2099-01-10","","2099","Q1","csv","","low",""],
        ["9999.T","bad","","2099","Q1","csv","","low",""],
    ],columns=COLUMNS)
    valid,invalid=validate_candidate_csv_preview(frame,db)
    assert len(valid)==1 and len(invalid)==1
    assert invalid.iloc[0]["行番号"]==3
    assert invalid.iloc[0]["エラー理由"]
