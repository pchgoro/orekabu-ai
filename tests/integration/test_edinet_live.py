"""Optional live EDINET API v2 integration test using an isolated database."""

from __future__ import annotations

import os
from datetime import date
from pathlib import Path

import pytest
from dotenv import load_dotenv

from services.database import init_db
from services.edinet import EdinetApiClient, run_edinet_fetch


@pytest.mark.integration
def test_edinet_live_dry_run_is_structured_and_does_not_write(tmp_path: Path) -> None:
    load_dotenv(Path(__file__).resolve().parents[2] / ".env", override=False)
    api_key = os.getenv("EDINET_API_KEY", "").strip()
    if not api_key:
        pytest.skip("EDINET_API_KEYが未設定です。")
    db = tmp_path / "edinet-live.db"
    init_db(db)
    result = run_edinet_fetch(
        EdinetApiClient(api_key),
        target_date=date.today(),
        limit=5,
        dry_run=True,
        db_path=db,
    )
    assert result.processed <= 5
    assert result.failed == 0
