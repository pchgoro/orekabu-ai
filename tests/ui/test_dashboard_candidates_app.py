"""Dashboard candidate summary AppTest coverage without network access."""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

import pandas as pd
from streamlit.testing.v1 import AppTest

from services.database import get_stock
from services.earnings_candidates import add_fetch_result, finish_fetch_run, save_candidate, start_fetch_run
from services.earnings_providers.base import EarningsFetchResult

ROOT = Path(__file__).resolve().parents[2]


def history() -> pd.DataFrame:
    index = pd.date_range("2026-01-01", periods=100, freq="B")
    values = pd.Series(range(100), index=index, dtype=float) + 1000
    return pd.DataFrame({"Open":values,"High":values+10,"Low":values-10,"Close":values,"Volume":1000}, index=index)


def test_dashboard_candidate_metrics(ui_db, monkeypatch) -> None:
    monkeypatch.setattr("services.stock_data.fetch_stock_history", lambda *args, **kwargs: history())
    stock = get_stock("5801.T")
    day = date(2099,1,10)
    result = EarningsFetchResult(ticker=stock["ticker"],earnings_date=day,candidate_dates=(day,),source_name="mock",retrieved_at=datetime.now().astimezone().isoformat(),confidence="low")
    save_candidate(stock,result,day)
    run_id=start_fetch_run("mock",1)
    add_fetch_result(run_id,stock,"failed",error_code="timeout",error_message="失敗")
    finish_fetch_run(run_id,{"success":0,"candidates":0,"unchanged":0,"failed":1},["失敗"])
    at=AppTest.from_file(str(ROOT/"app.py"),default_timeout=60).run(timeout=60)
    metrics={item.label:item.value for item in at.metric}
    assert metrics["未確認候補"] == "1"
    assert "日付変更" in metrics and "競合" in metrics and "最終取得" in metrics
    assert metrics["直近失敗"] == "1"
    assert len(at.exception)==0
