"""Run an EDINET initial backfill using configured free API access."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Sequence

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.common import (
    api_key,
    build_parser,
    exit_code,
    option_provided,
    prepare,
    print_result,
    run_main,
)
from scripts.fetch_edinet import print_edinet_summary
from services.automation import run_steps
from services.database import load_settings
from services.edinet import EdinetApiClient, lookback_dates, run_edinet_range
from services.earnings import japan_today
from utils.constants import DB_PATH


def resolve_backfill_options(
    args: object,
    raw_argv: Sequence[str],
    settings: dict,
) -> tuple[int, int, str]:
    """Resolve initial backfill days and limit with CLI precedence."""
    requested_days = getattr(args, "days", None)
    days = (
        int(requested_days)
        if requested_days is not None
        else int(settings["edinet_initial_backfill_days"])
    )
    limit = (
        int(getattr(args, "limit"))
        if option_provided(raw_argv, "--limit")
        else int(settings["edinet_fetch_limit"])
    )
    return days, limit, "CLI --days" if requested_days is not None else "設定 initial"


def main(argv: Sequence[str] | None = None, db_path: Path | str = DB_PATH) -> int:
    """Backfill EDINET metadata using initial-backfill settings by default."""
    raw_argv = list(argv) if argv is not None else sys.argv[1:]
    parser = build_parser("EDINET書類を初回バックフィルします。")
    parser.add_argument("--days", type=int, help="バックフィル日数（1から365）")
    args = parser.parse_args(raw_argv)
    ticker = prepare(args, db_path)
    settings = load_settings(db_path)
    days, limit, source = resolve_backfill_options(args, raw_argv, settings)
    target_dates = lookback_dates(japan_today(), days)
    client = EdinetApiClient(api_key())

    def progress(row: dict) -> None:
        if args.verbose:
            print(
                f"{row['date']} API取得={row['api_documents']} "
                f"ticker一致={row['security_matches']} "
                f"対象書類={row['target_documents']} 保存候補={row['inserted']} "
                f"重複={row['duplicates']} 失敗={row['failed']}"
            )

    result = run_steps(
        "run_edinet_backfill",
        [
            (
                "edinet",
                lambda: run_edinet_range(
                    client,
                    target_dates=target_dates,
                    ticker=ticker,
                    limit=limit,
                    dry_run=args.dry_run,
                    db_path=db_path,
                    progress=progress,
                ),
            )
        ],
        dry_run=args.dry_run,
        target_count=limit,
        db_path=db_path,
    )
    if args.verbose:
        print_edinet_summary(
            result,
            lookback_days=days,
            limit=limit,
            source=source,
        )
    print_result(result)
    return exit_code(result)


if __name__ == "__main__":
    raise SystemExit(run_main(main))
