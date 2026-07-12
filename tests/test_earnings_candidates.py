"""Tests for candidate persistence and transactional review."""

from __future__ import annotations

import sqlite3
from datetime import date, datetime
from pathlib import Path

import pytest

from services.database import get_stock, init_db
from services.earnings import add_earnings, list_earnings
from services.earnings_candidates import add_fetch_result, approve_candidate, finish_fetch_run, list_candidates, list_fetch_runs, purge_reviewed_candidates, review_candidate, save_candidate, start_fetch_run
from services.earnings_providers.base import EarningsFetchResult


def result(day=date(2099,1,10), **kwargs):
    values={"ticker":"5801.T","earnings_date":day,"candidate_dates":(day,),"source_name":"test","source_reference":"unit","retrieved_at":datetime.now().astimezone().isoformat(),"confidence":"low","fiscal_year":2099,"fiscal_quarter":"Q1"}
    values.update(kwargs)
    return EarningsFetchResult(**values)


def test_candidate_registration_and_duplicate(tmp_path: Path) -> None:
    db=tmp_path/"test.db"; init_db(db); stock=get_stock("5801.T",db)
    status,candidate_id,_=save_candidate(stock,result(),date(2099,1,10),db_path=db)
    assert status=="created" and candidate_id
    status,_,_=save_candidate(stock,result(),date(2099,1,10),db_path=db)
    assert status=="duplicate"


def test_approve_new_creates_formal_event_only_after_approval(tmp_path: Path) -> None:
    db=tmp_path/"test.db"; init_db(db); stock=get_stock("5801.T",db)
    _,candidate_id,_=save_candidate(stock,result(),date(2099,1,10),db_path=db)
    assert list_earnings(db)==[]
    event_id=approve_candidate(candidate_id,"new_event",db_path=db)
    assert event_id and list_earnings(db)[0]["earnings_date"]=="2099-01-10"
    assert list_candidates(db)[0]["review_status"]=="approved"


def test_hold_and_reject(tmp_path: Path) -> None:
    db=tmp_path/"test.db"; init_db(db); stock=get_stock("5801.T",db)
    _,held,_=save_candidate(stock,result(),date(2099,1,10),db_path=db)
    review_candidate(held,"held",db_path=db)
    _,rejected,_=save_candidate(stock,result(date(2099,1,11)),date(2099,1,11),db_path=db)
    review_candidate(rejected,"rejected",db_path=db)
    assert {row["review_status"] for row in list_candidates(db)}=={"held","rejected"}


def test_update_planned_and_protect_confirmed(tmp_path: Path) -> None:
    db=tmp_path/"test.db"; init_db(db); stock=get_stock("5801.T",db)
    payload={"stock_id":stock["id"],"fiscal_year":2099,"fiscal_quarter":"Q1","earnings_date":"2099-01-10","date_status":"予定"}
    event_id=add_earnings(payload,db)
    _,candidate_id,_=save_candidate(stock,result(date(2099,1,11)),date(2099,1,11),db_path=db)
    approve_candidate(candidate_id,"date_only",db_path=db)
    assert list_earnings(db)[0]["earnings_date"]=="2099-01-11"
    from services.earnings import update_earnings
    update_earnings(event_id,{**payload,"earnings_date":"2099-01-11","date_status":"確定"},db)
    _,fixed_candidate,_=save_candidate(stock,result(date(2099,1,12)),date(2099,1,12),db_path=db)
    with pytest.raises(ValueError,match="追加確認"):
        approve_candidate(fixed_candidate,"date_only",db_path=db)
    assert list_candidates(db)[0]["review_status"]=="pending"
    assert list_earnings(db)[0]["earnings_date"]=="2099-01-11"


def test_transaction_rolls_back_on_duplicate_formal_event(tmp_path: Path) -> None:
    db=tmp_path/"test.db"; init_db(db); stock=get_stock("5801.T",db)
    add_earnings({"stock_id":stock["id"],"fiscal_year":2099,"fiscal_quarter":"Q1","earnings_date":"2099-01-10","date_status":"予定"},db)
    _,candidate_id,_=save_candidate(stock,result(date(2099,6,1),fiscal_quarter="Q1"),date(2099,6,1),db_path=db)
    with pytest.raises(sqlite3.IntegrityError):
        approve_candidate(candidate_id,"new_event",db_path=db)
    assert get_pending(db,candidate_id)=="pending"


def get_pending(db, candidate_id):
    import sqlite3
    c=sqlite3.connect(db); value=c.execute("select review_status from earnings_candidates where id=?",(candidate_id,)).fetchone()[0]; c.close(); return value


def test_retention_deletes_only_old_reviewed_candidates(tmp_path: Path) -> None:
    db=tmp_path/"test.db"; init_db(db); stock=get_stock("5801.T",db)
    _,reviewed,_=save_candidate(stock,result(),date(2099,1,10),db_path=db)
    review_candidate(reviewed,"rejected",db_path=db)
    _,pending,_=save_candidate(stock,result(date(2099,1,11)),date(2099,1,11),db_path=db)
    c=sqlite3.connect(db); c.execute("update earnings_candidates set reviewed_at='2000-01-01T00:00:00+09:00' where id=?",(reviewed,)); c.commit(); c.close()
    assert purge_reviewed_candidates(90,db)==1
    assert [row["id"] for row in list_candidates(db)]==[pending]


def test_candidate_history_and_formal_event_survive_reinitialization(tmp_path: Path) -> None:
    db=tmp_path/"test.db"; init_db(db); stock=get_stock("5801.T",db)
    _,candidate_id,_=save_candidate(stock,result(),date(2099,1,10),db_path=db)
    run_id=start_fetch_run("mock",1,db)
    add_fetch_result(run_id,stock,"candidate_created",candidate_id,retrieved_at=datetime.now().astimezone().isoformat(),db_path=db)
    finish_fetch_run(run_id,{"success":1,"candidates":1,"unchanged":0,"failed":0},[],db)
    approve_candidate(candidate_id,"new_event",db_path=db)
    init_db(db); init_db(db)
    assert list_candidates(db)[0]["review_status"]=="approved"
    assert list_fetch_runs(db)[0]["candidate_count"]==1
    assert list_earnings(db)[0]["earnings_date"]=="2099-01-10"
