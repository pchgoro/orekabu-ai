"""Execution history and orchestration for free local automation jobs."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable

from services.database import _now, connect
from utils.constants import DB_PATH

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class JobResult:
    """Normalized result returned by one automation job."""

    processed: int = 0
    inserted: int = 0
    duplicates: int = 0
    failed: int = 0
    message: str = ""
    details: dict[str, Any] = field(default_factory=dict)

    @property
    def status(self) -> str:
        """Return completed, partial, or failed from the counters."""
        if self.failed and not (self.processed - self.failed or self.inserted or self.duplicates):
            return "failed"
        return "partial" if self.failed else "completed"


AutomationStep = tuple[str, Callable[[], JobResult]]


def _aggregate_status(results: Iterable[JobResult]) -> str:
    """Return a run status consistent with the contained step results."""
    rows = list(results)
    failed = sum(row.failed for row in rows)
    if not failed:
        return "completed"
    return "partial" if any(row.status != "failed" for row in rows) else "failed"


def start_run(command: str, dry_run: bool, target_count: int, db_path: Path | str = DB_PATH) -> int:
    """Create a persistent automation run. Dry runs must not call this function."""
    now = _now()
    with connect(db_path) as conn:
        cursor = conn.execute(
            """INSERT INTO automation_runs
            (command,started_at,dry_run,target_count,status,created_at)
            VALUES (?,?,?,?,?,?)""",
            (command, now, int(dry_run), max(0, int(target_count)), "running", now),
        )
        return int(cursor.lastrowid)


def add_step(
    run_id: int,
    sequence_no: int,
    step_name: str,
    started_at: str,
    result: JobResult,
    db_path: Path | str = DB_PATH,
) -> None:
    """Persist one completed step."""
    with connect(db_path) as conn:
        conn.execute(
            """INSERT INTO automation_run_steps
            (automation_run_id,step_name,sequence_no,started_at,finished_at,status,
             processed_count,inserted_count,duplicate_count,failed_count,message,created_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                run_id,
                step_name,
                sequence_no,
                started_at,
                _now(),
                result.status,
                result.processed,
                result.inserted,
                result.duplicates,
                result.failed,
                result.message[:1000],
                _now(),
            ),
        )


def finish_run(run_id: int, results: Iterable[JobResult], db_path: Path | str = DB_PATH) -> None:
    """Finish a run from its independent step results."""
    rows = list(results)
    failed = sum(row.failed for row in rows)
    successful_steps = sum(row.status == "completed" for row in rows)
    status = _aggregate_status(rows)
    errors = [row.message for row in rows if row.failed and row.message]
    with connect(db_path) as conn:
        conn.execute(
            """UPDATE automation_runs
            SET finished_at=?,success_count=?,failed_count=?,status=?,error_summary=?
            WHERE id=?""",
            (_now(), successful_steps, failed, status, " / ".join(errors)[:1000], run_id),
        )


def run_steps(
    command: str,
    steps: Iterable[AutomationStep],
    *,
    dry_run: bool = False,
    target_count: int = 0,
    db_path: Path | str = DB_PATH,
) -> dict[str, Any]:
    """Run steps in order while allowing later steps to continue after failures."""
    ordered = list(steps)
    run_id = None if dry_run else start_run(command, False, target_count, db_path)
    results: list[tuple[str, JobResult]] = []
    for sequence_no, (step_name, function) in enumerate(ordered, start=1):
        started_at = _now()
        try:
            result = function()
        except Exception as exc:
            logger.exception("Automation step failed command=%s step=%s", command, step_name)
            result = JobResult(processed=1, failed=1, message=f"{type(exc).__name__}: {exc}")
        results.append((step_name, result))
        if run_id is not None:
            add_step(run_id, sequence_no, step_name, started_at, result, db_path)
    if run_id is not None:
        finish_run(run_id, (result for _, result in results), db_path)
    failed = sum(result.failed for _, result in results)
    return {
        "run_id": run_id,
        "dry_run": dry_run,
        "status": _aggregate_status(result for _, result in results),
        "failed": failed,
        "steps": [{"name": name, **result.__dict__, "status": result.status} for name, result in results],
    }


def list_runs(limit: int = 20, db_path: Path | str = DB_PATH) -> list[dict[str, Any]]:
    """Return recent automation runs."""
    with connect(db_path) as conn:
        rows = conn.execute(
            "SELECT * FROM automation_runs ORDER BY id DESC LIMIT ?",
            (max(1, min(int(limit), 200)),),
        ).fetchall()
    return [dict(row) for row in rows]


def list_run_steps(run_id: int, db_path: Path | str = DB_PATH) -> list[dict[str, Any]]:
    """Return ordered steps for one automation run."""
    with connect(db_path) as conn:
        rows = conn.execute(
            "SELECT * FROM automation_run_steps WHERE automation_run_id=? ORDER BY sequence_no,id",
            (run_id,),
        ).fetchall()
    return [dict(row) for row in rows]


def automation_summary(db_path: Path | str = DB_PATH) -> dict[str, Any]:
    """Return counts used by the settings page."""
    with connect(db_path) as conn:
        latest = conn.execute(
            "SELECT id,finished_at,status,failed_count FROM automation_runs ORDER BY id DESC LIMIT 1"
        ).fetchone()
        edinet = conn.execute(
            "SELECT COUNT(*) FROM edinet_documents WHERE substr(retrieved_at,1,10)=substr(?,1,10)",
            (_now(),),
        ).fetchone()[0]
        earnings = conn.execute(
            "SELECT COUNT(*) FROM earnings_candidates WHERE review_status='pending'"
        ).fetchone()[0]
        profiles = conn.execute(
            "SELECT COUNT(*) FROM stock_profile_candidates WHERE review_status='pending'"
        ).fetchone()[0]
    return {
        "last_run_id": int(latest["id"]) if latest else None,
        "last_run_at": latest["finished_at"] if latest else None,
        "last_status": latest["status"] if latest else None,
        "last_failed": int(latest["failed_count"]) if latest else 0,
        "new_edinet": int(edinet),
        "pending_earnings": int(earnings),
        "pending_profiles": int(profiles),
    }
