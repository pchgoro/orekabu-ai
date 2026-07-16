"""Shared CLI setup for local automation scripts."""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path
from typing import Sequence

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parents[1]
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from services.database import get_stock, init_db  # noqa: E402
from utils.constants import DB_PATH  # noqa: E402
from utils.logging_config import setup_logging  # noqa: E402
from utils.validators import normalize_ticker  # noqa: E402


def build_parser(description: str) -> argparse.ArgumentParser:
    """Create the common argument surface required by all automation CLIs."""
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument("--dry-run", action="store_true", help="取得内容だけ確認しDBを変更しません")
    parser.add_argument("--ticker", help="対象を1銘柄に限定します（例: 5801 または 5801.T）")
    parser.add_argument("--limit", type=int, default=20, help="処理上限（既定: 20）")
    parser.add_argument("--force", action="store_true", help="キャッシュ等を無視して再取得します")
    parser.add_argument("--verbose", action="store_true", help="詳細ログを表示します")
    return parser


def prepare(args: argparse.Namespace, db_path: Path | str = DB_PATH) -> str | None:
    """Load local environment, initialize the DB, logging, and ticker validation."""
    load_dotenv(BASE_DIR / ".env")
    setup_logging()
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    if args.limit < 1:
        raise ValueError("--limitは1以上で指定してください。")
    init_db(db_path)
    if not args.ticker:
        return None
    ticker = normalize_ticker(args.ticker)
    if get_stock(ticker, db_path) is None:
        raise ValueError(f"登録されていない銘柄です: {ticker}")
    return ticker


def api_key() -> str:
    """Read the EDINET key without logging it."""
    return os.getenv("EDINET_API_KEY", "").strip()


def option_provided(argv: Sequence[str], option: str) -> bool:
    """Return whether an option was explicitly provided, including --name=value."""
    return any(value == option or value.startswith(f"{option}=") for value in argv)


def print_result(result: dict | object) -> None:
    """Print a concise result suitable for Task Scheduler history."""
    print(result)


def exit_code(result: dict) -> int:
    """Return 0 for success, 1 for partial/failure."""
    return 1 if int(result.get("failed", 0)) else 0


def run_main(main_function: callable, argv: Sequence[str] | None = None) -> int:
    """Execute a CLI main function with a stable configuration error code."""
    try:
        return int(main_function(argv))
    except (ValueError, OSError) as exc:
        print(f"設定エラー: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:
        logging.getLogger(__name__).exception("Automation CLI failed")
        print(f"実行エラー: {exc}", file=sys.stderr)
        return 1
