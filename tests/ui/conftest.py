"""Isolated fixtures for Streamlit AppTest."""

from __future__ import annotations

from pathlib import Path

import pytest
import streamlit as st

from services.database import init_db


@pytest.fixture
def ui_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Route every default DB connection to a per-test temporary database."""
    db = tmp_path / "ui.db"
    monkeypatch.setenv("OREKABU_DB_PATH", str(db))
    st.cache_data.clear()
    init_db()
    yield db
    st.cache_data.clear()
