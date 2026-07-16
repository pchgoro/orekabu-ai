"""Fetch official EDINET API v2 metadata."""

from __future__ import annotations

import sys
from argparse import ArgumentParser, Namespace
from datetime import date
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
from services.automation import run_steps
from services.database import load_settings
from services.edinet import EdinetApiClient, lookback_dates, run_edinet_range
from services.earnings import japan_today
from utils.constants import DB_PATH


def build_edinet_parser() -> ArgumentParser:
    """Build the EDINET CLI parser."""
    parser = build_parser("EDINET公式API v2から登録銘柄の書類メタデータを取得します。")
    dates = parser.add_mutually_exclusive_group()
    dates.add_argument("--date", help="対象日 YYYY-MM-DD（未指定時は今日）")
    dates.add_argument(
        "--lookback-days",
        type=int,
        help="今日を含む直近N日を検索します（1から365）",
    )
    parser.add_argument(
        "--preset",
        choices=("daily", "monthly", "initial"),
        default="daily",
        help="日数未指定時に使う設定（既定: daily）",
    )
    return parser


def resolve_target_dates(
    args: Namespace,
    today: date,
    settings: dict | None = None,
) -> list[date]:
    """Resolve one date or a descending Japanese-calendar lookback range."""
    if args.lookback_days is not None:
        return lookback_dates(today, args.lookback_days)
    if args.date:
        return [date.fromisoformat(args.date)]
    values = settings or {}
    setting_key = {
        "daily": "edinet_daily_lookback_days",
        "monthly": "edinet_monthly_lookback_days",
        "initial": "edinet_initial_backfill_days",
    }[args.preset]
    return lookback_dates(today, int(values.get(setting_key, {"daily": 3, "monthly": 30, "initial": 90}[args.preset])))


def resolve_fetch_options(
    args: Namespace,
    raw_argv: Sequence[str],
    settings: dict,
    today: date,
) -> tuple[list[date], int, str]:
    """Resolve date range, limit, and provenance for direct EDINET fetches."""
    target_dates = resolve_target_dates(args, today, settings)
    limit = (
        args.limit
        if option_provided(raw_argv, "--limit")
        else int(settings["edinet_fetch_limit"])
    )
    if args.date:
        source = "CLI --date"
    elif args.lookback_days is not None:
        source = "CLI --lookback-days"
    else:
        source = f"設定 {args.preset}"
    return target_dates, limit, source


def print_edinet_summary(result: dict, *, lookback_days: int, limit: int, source: str) -> None:
    """Print concise EDINET configuration and aggregate counters."""
    step = next((row for row in result.get("steps", []) if row.get("name") == "edinet"), {})
    details = step.get("details") or {}
    print(
        f"EDINET設定 lookback={lookback_days}日 limit={limit} source={source} "
        f"API取得={details.get('api_documents', 0)} "
        f"ticker一致={details.get('security_matches', 0)} "
        f"保存={step.get('inserted', 0)} 重複={step.get('duplicates', 0)} "
        f"失敗={step.get('failed', 0)}"
    )


def main(argv: Sequence[str] | None = None, db_path: Path | str = DB_PATH) -> int:
    """Run the EDINET metadata collector."""
    raw_argv = list(argv) if argv is not None else sys.argv[1:]
    parser = build_edinet_parser()
    args = parser.parse_args(raw_argv)
    ticker = prepare(args, db_path)
    settings = load_settings(db_path)
    target_dates, limit, source = resolve_fetch_options(
        args, raw_argv, settings, japan_today()
    )
    client = EdinetApiClient(api_key())

    def show_progress(row: dict) -> None:
        if not args.verbose:
            return
        print(
            f"{row['date']} API取得={row['api_documents']} "
            f"ticker一致={row['security_matches']} "
            f"対象書類={row['target_documents']} "
            f"保存候補={row['inserted']} 重複={row['duplicates']} "
            f"失敗={row['failed']}"
        )

    result = run_steps(
        "fetch_edinet",
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
                    progress=show_progress,
                ),
            )
        ],
        dry_run=args.dry_run,
        db_path=db_path,
    )
    if args.verbose:
        print_edinet_summary(
            result,
            lookback_days=len(target_dates),
            limit=limit,
            source=source,
        )
    print_result(result)
    return exit_code(result)


if __name__ == "__main__":
    raise SystemExit(run_main(main))
