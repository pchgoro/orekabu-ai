"""Dependency-free Streamlit process and HTTP smoke test."""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_streamlit_root_and_health_use_isolated_db(tmp_path: Path) -> None:
    db = tmp_path / "e2e.db"
    port = _free_port()
    env = os.environ.copy()
    env["OREKABU_DB_PATH"] = str(db)
    env["STREAMLIT_BROWSER_GATHER_USAGE_STATS"] = "false"
    creationflags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    process = subprocess.Popen(
        [sys.executable, "-m", "streamlit", "run", "app.py", "--server.headless", "true", "--server.port", str(port)],
        cwd=ROOT, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        creationflags=creationflags,
    )
    try:
        health = _wait_for(f"http://127.0.0.1:{port}/_stcore/health", process)
        root = urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=5)
        assert health == 200 and root.status == 200
        assert not (ROOT / "data" / "orekabu.db").samefile(db) if db.exists() else True
    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill(); process.wait(timeout=5)


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _wait_for(url: str, process: subprocess.Popen, timeout: float = 30) -> int:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if process.poll() is not None:
            _, stderr = process.communicate(timeout=1)
            raise AssertionError(f"Streamlit exited early: {stderr[-1000:]}")
        try:
            return urllib.request.urlopen(url, timeout=2).status
        except Exception:
            time.sleep(0.25)
    raise AssertionError("Streamlit health endpoint did not become ready")
