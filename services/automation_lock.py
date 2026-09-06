"""Cross-process guards for local automation jobs."""

from __future__ import annotations

import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import TextIO

from utils.constants import DB_PATH


class AutomationLock:
    """Create an exclusive, recoverable lock for one local automation target."""

    def __init__(self, target: Path | str = DB_PATH, stale_after: timedelta = timedelta(hours=6)) -> None:
        target_path = Path(target)
        self.path = target_path.with_name(f".{target_path.name}.automation.lock")
        self.stale_after = stale_after
        self._handle: TextIO | None = None

    def _is_stale(self) -> bool:
        try:
            return datetime.now().astimezone() - datetime.fromtimestamp(
                self.path.stat().st_mtime, tz=datetime.now().astimezone().tzinfo
            ) > self.stale_after
        except FileNotFoundError:
            return False

    def acquire(self) -> bool:
        """Acquire without waiting; stale lock markers are safe to recover."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        for attempt in range(2):
            try:
                self._handle = self.path.open("x", encoding="utf-8")
                self._handle.write(f"pid={os.getpid()}\n")
                self._handle.flush()
                return True
            except FileExistsError:
                if attempt == 0 and self._is_stale():
                    try:
                        self.path.unlink()
                    except FileNotFoundError:
                        pass
                    continue
                return False
        return False

    def release(self) -> None:
        if self._handle is not None:
            self._handle.close()
            self._handle = None
        try:
            self.path.unlink()
        except FileNotFoundError:
            pass

    def __enter__(self) -> "AutomationLock":
        if not self.acquire():
            raise RuntimeError(f"自動更新は別プロセスで実行中です: {self.path.name}")
        return self

    def __exit__(self, exc_type: object, exc_value: object, traceback: object) -> None:
        self.release()
