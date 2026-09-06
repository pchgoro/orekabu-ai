from __future__ import annotations

from datetime import datetime
from pathlib import Path
from threading import Event

from services import startup_automation
from services.database import init_db


def test_startup_update_starts_once_while_in_flight(tmp_path: Path) -> None:
    calls: list[tuple[list[str], Path | str]] = []
    started = Event()
    release = Event()

    def runner(args: list[str], *, db_path: Path | str) -> int:
        calls.append((args, db_path))
        started.set()
        release.wait(timeout=2)
        return 0

    db = tmp_path / "startup.db"
    init_db(db)
    assert startup_automation.start_daily_update_if_needed(db, runner=runner) is True
    assert started.wait(timeout=2)
    assert startup_automation.start_daily_update_if_needed(db, runner=runner) is False
    assert calls == [(["--limit", "20"], db)]
    release.set()


def test_startup_update_does_not_repeat_after_today_started(tmp_path: Path, monkeypatch) -> None:
    db = tmp_path / "already-run.db"
    monkeypatch.setattr(
        startup_automation,
        "list_runs",
        lambda limit, db_path: [{"started_at": datetime.now().astimezone().isoformat()}],
    )
    assert startup_automation.start_daily_update_if_needed(db, runner=lambda *args, **kwargs: 0) is False
