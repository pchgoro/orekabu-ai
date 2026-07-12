"""Tests for isolated batch fetch runs and audit counts."""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

from services.database import get_stocks, init_db, load_settings
from services.earnings_candidates import list_candidates, list_fetch_results, list_fetch_runs, run_candidate_fetch
from services.earnings_providers.base import EarningsFetchResult


class Provider:
    name="mock"
    def fetch_next_earnings(self,ticker):
        if ticker=="6976.T":
            return EarningsFetchResult(ticker=ticker,source_name=self.name,retrieved_at=datetime.now().astimezone().isoformat(),error_code="network_error",error_message="失敗")
        day=date(2099,1,10)
        return EarningsFetchResult(ticker=ticker,earnings_date=day,candidate_dates=(day,),source_name=self.name,retrieved_at=datetime.now().astimezone().isoformat(),confidence="low")


def test_partial_fetch_run_and_counts(tmp_path: Path) -> None:
    db=tmp_path/"test.db"; init_db(db); settings=load_settings(db)
    settings["earnings_auto_fetch"]["request_interval_seconds"]=1
    stocks=[stock for stock in get_stocks(db) if stock["ticker"] in {"5801.T","6976.T"}]
    result=run_candidate_fetch(stocks,Provider(),settings,db_path=db,sleep=lambda value:None)
    run=list_fetch_runs(db)[0]
    assert run["status"]=="partial" and run["failed_count"]==1 and run["candidate_count"]==1
    assert len(list_fetch_results(result["run_id"],db))==2


def test_all_failed_run(tmp_path: Path) -> None:
    db=tmp_path/"test.db"; init_db(db); settings=load_settings(db)
    stocks=[stock for stock in get_stocks(db) if stock["ticker"]=="6976.T"]
    run_candidate_fetch(stocks,Provider(),settings,db_path=db,sleep=lambda value:None)
    assert list_fetch_runs(db)[0]["status"]=="failed"


class CountingProvider:
    name="counting"
    def __init__(self, fail=False, raises=False): self.calls=0; self.fail=fail; self.raises=raises
    def fetch_next_earnings(self,ticker):
        self.calls+=1
        if self.raises: raise RuntimeError("unexpected")
        if self.fail: return EarningsFetchResult(ticker=ticker,source_name=self.name,retrieved_at=datetime.now().astimezone().isoformat(),error_code="timeout",error_message="失敗")
        day=date(2099,2,1)
        return EarningsFetchResult(ticker=ticker,earnings_date=day,candidate_dates=(day,),source_name=self.name,retrieved_at=datetime.now().astimezone().isoformat(),confidence="low")


def test_all_success_and_cache_prevent_duplicate_candidate(tmp_path: Path) -> None:
    db=tmp_path/"test.db"; init_db(db); settings=load_settings(db); stock=get_stocks(db)[:1]
    provider=CountingProvider()
    first=run_candidate_fetch(stock,provider,settings,db_path=db,sleep=lambda value:None)
    second=run_candidate_fetch(stock,provider,settings,db_path=db,sleep=lambda value:None)
    assert first["counts"]["success"]==1 and second["counts"]["cached"]==1
    assert provider.calls==1 and len(list_candidates(db))==1 and len(list_fetch_runs(db))==2
    assert list_fetch_runs(db)[-1]["status"]=="completed"


def test_failed_ticker_can_be_force_retried(tmp_path: Path) -> None:
    db=tmp_path/"test.db"; init_db(db); settings=load_settings(db); stock=get_stocks(db)[:1]
    failed=CountingProvider(fail=True)
    run_candidate_fetch(stock,failed,settings,db_path=db,sleep=lambda value:None)
    success=CountingProvider()
    result=run_candidate_fetch(stock,success,settings,db_path=db,sleep=lambda value:None,force_fetch=True)
    assert result["counts"]["success"]==1 and success.calls==1
    assert len(list_fetch_runs(db))==2 and len(list_candidates(db))==1


def test_provider_exception_isolated_and_lock_released(tmp_path: Path) -> None:
    db=tmp_path/"test.db"; init_db(db); settings=load_settings(db); stock=get_stocks(db)[:1]
    result=run_candidate_fetch(stock,CountingProvider(raises=True),settings,db_path=db,sleep=lambda value:None)
    assert result["counts"]["failed"]==1
    second=run_candidate_fetch(stock,CountingProvider(),settings,db_path=db,sleep=lambda value:None,force_fetch=True)
    assert second["counts"]["success"]==1


def test_running_lock_rejects_second_execution(tmp_path: Path) -> None:
    from services import earnings_candidates as module
    db=tmp_path/"test.db"; init_db(db); settings=load_settings(db)
    assert module._FETCH_LOCK.acquire(blocking=False)
    try:
        import pytest
        with pytest.raises(RuntimeError,match="実行中"):
            run_candidate_fetch(get_stocks(db)[:1],CountingProvider(),settings,db_path=db,sleep=lambda value:None)
    finally:
        module._FETCH_LOCK.release()
