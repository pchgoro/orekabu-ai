"""Free automation orchestration and dry-run safety tests."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from services.automation import JobResult, list_run_steps, list_runs, run_steps
from services.database import init_db


def table_counts(db: Path) -> dict[str, int]:
    """Return counts for all application tables."""
    with sqlite3.connect(db) as conn:
        tables = [
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            )
        ]
        return {table: int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]) for table in tables}


def test_dry_run_keeps_every_table_unchanged(tmp_path: Path) -> None:
    db = tmp_path / "test.db"
    init_db(db)
    before = table_counts(db)
    result = run_steps(
        "dry",
        [("preview", lambda: JobResult(processed=2, inserted=2))],
        dry_run=True,
        db_path=db,
    )
    assert result["run_id"] is None
    assert table_counts(db) == before


def test_daily_steps_keep_order_and_continue_after_failure(tmp_path: Path) -> None:
    db = tmp_path / "test.db"
    init_db(db)
    called: list[str] = []

    def step(name: str, fail: bool = False):
        def execute() -> JobResult:
            called.append(name)
            if fail:
                raise RuntimeError("temporary failure")
            return JobResult(processed=1, inserted=1)

        return execute

    result = run_steps(
        "daily",
        [
            ("rss", step("rss")),
            ("earnings", step("earnings", True)),
            ("edinet", step("edinet")),
            ("stock_profiles", step("stock_profiles")),
            ("candidate_cleanup", step("candidate_cleanup")),
        ],
        db_path=db,
    )
    assert called == ["rss", "earnings", "edinet", "stock_profiles", "candidate_cleanup"]
    assert result["failed"] == 1
    assert [row["step_name"] for row in list_run_steps(result["run_id"], db)] == called
    assert list_runs(db_path=db)[0]["status"] == "partial"


def test_repeated_run_creates_independent_history(tmp_path: Path) -> None:
    db = tmp_path / "test.db"
    init_db(db)
    for _ in range(2):
        run_steps("repeat", [("rss", lambda: JobResult(processed=1))], db_path=db)
    assert len(list_runs(db_path=db)) == 2
