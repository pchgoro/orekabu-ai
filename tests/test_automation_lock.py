from __future__ import annotations

from datetime import timedelta
from pathlib import Path

from services.automation_lock import AutomationLock


def test_automation_lock_is_exclusive_and_releases(tmp_path: Path) -> None:
    target = tmp_path / "orekabu.db"
    first = AutomationLock(target)
    second = AutomationLock(target)

    assert first.acquire() is True
    assert second.acquire() is False
    first.release()
    assert second.acquire() is True
    second.release()
    assert not second.path.exists()


def test_automation_lock_recovers_stale_marker(tmp_path: Path) -> None:
    target = tmp_path / "orekabu.db"
    lock = AutomationLock(target)
    lock.path.parent.mkdir(parents=True, exist_ok=True)
    lock.path.write_text("stale\n", encoding="utf-8")
    lock.path.touch()
    import os
    import time

    old = time.time() - 3600
    os.utime(lock.path, (old, old))
    recovered = AutomationLock(target, stale_after=timedelta(minutes=5))

    assert recovered.acquire() is True
    recovered.release()
