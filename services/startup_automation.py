"""Non-blocking, once-per-day startup trigger for local daily updates."""

from __future__ import annotations

import logging
import threading
from datetime import datetime
from pathlib import Path
from typing import Callable

from services.automation import list_runs
from utils.constants import DB_PATH

logger = logging.getLogger(__name__)
_STATE_LOCK = threading.Lock()
_IN_FLIGHT: set[str] = set()


def is_daily_update_running(db_path: Path | str = DB_PATH) -> bool:
    """Return whether this process currently owns the daily-update worker."""
    key = str(Path(db_path).resolve())
    with _STATE_LOCK:
        return key in _IN_FLIGHT


def _run_in_background(key: str, runner: Callable[..., int], db_path: Path | str, limit: int) -> None:
    try:
        runner(["--limit", str(limit)], db_path=db_path)
    except Exception:
        logger.exception("起動時自動更新に失敗しました")
    finally:
        with _STATE_LOCK:
            _IN_FLIGHT.discard(key)


def start_daily_update_if_needed(
    db_path: Path | str = DB_PATH,
    *,
    limit: int = 20,
    runner: Callable[..., int] | None = None,
) -> bool:
    """Start today's update in a daemon thread when no run has started today."""
    if limit < 1:
        raise ValueError("limitは1以上で指定してください。")
    key = str(Path(db_path).resolve())
    today = datetime.now().astimezone().date().isoformat()
    with _STATE_LOCK:
        if key in _IN_FLIGHT:
            return False
        latest = list_runs(1, db_path=db_path)
        if latest and str(latest[0].get("started_at") or "").startswith(today):
            return False
        _IN_FLIGHT.add(key)

    if runner is None:
        from scripts.run_daily_update import main as runner

    threading.Thread(
        target=_run_in_background,
        args=(key, runner, db_path, limit),
        name="orekabu-daily-update",
        daemon=True,
    ).start()
    return True
