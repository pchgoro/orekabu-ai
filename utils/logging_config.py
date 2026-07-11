"""Logging setup for file-based diagnostics."""

from __future__ import annotations

import logging

from utils.constants import LOG_DIR, LOG_PATH


def setup_logging() -> None:
    """Configure application logging once."""
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    LOG_PATH.touch(exist_ok=True)
    logging.basicConfig(
        filename=LOG_PATH,
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        encoding="utf-8",
        force=False,
    )
