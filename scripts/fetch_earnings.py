"""Fetch yfinance earnings dates into review candidates."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Sequence

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.common import build_parser, exit_code, prepare, print_result, run_main
from services.automation import run_steps
from services.automation_jobs import run_earnings_job
from services.earnings_providers.yfinance_provider import YFinanceEarningsProvider
from utils.constants import DB_PATH


def main(argv: Sequence[str] | None = None, db_path: Path | str = DB_PATH) -> int:
    """Run the earnings candidate collector."""
    parser = build_parser("yfinanceから決算日候補を取得します。")
    args = parser.parse_args(argv)
    ticker = prepare(args, db_path)
    result = run_steps(
        "fetch_earnings",
        [
            (
                "earnings",
                lambda: run_earnings_job(
                    YFinanceEarningsProvider(),
                    ticker=ticker,
                    limit=args.limit,
                    force=args.force,
                    dry_run=args.dry_run,
                    db_path=db_path,
                ),
            )
        ],
        dry_run=args.dry_run,
        db_path=db_path,
    )
    print_result(result)
    return exit_code(result)


if __name__ == "__main__":
    raise SystemExit(run_main(main))
