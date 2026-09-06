"""Run all free collectors in a fixed, independently audited order."""

from __future__ import annotations

import sys
from collections.abc import Callable
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
from services.automation import JobResult, run_steps
from services.automation_jobs import run_candidate_cleanup, run_earnings_job, run_news_job
from services.database import load_settings
from services.edinet import EdinetApiClient, lookback_dates, run_edinet_range
from services.earnings import japan_today
from services.earnings_providers.fallback_provider import build_default_earnings_provider
from services.news_providers.rss_provider import RssNewsProvider
from services.stock_profiles import YFinanceStockProfileProvider, run_profile_refresh
from utils.constants import DB_PATH


def resolve_daily_edinet_options(
    args: object,
    raw_argv: Sequence[str],
    settings: dict,
) -> tuple[int, int, str]:
    """Resolve daily EDINET days and limit with explicit CLI precedence."""
    requested_days = getattr(args, "edinet_lookback_days", None)
    days = (
        int(requested_days)
        if requested_days is not None
        else int(settings["edinet_daily_lookback_days"])
    )
    limit = (
        int(getattr(args, "limit"))
        if option_provided(raw_argv, "--limit")
        else int(settings["edinet_fetch_limit"])
    )
    source = (
        "CLI --edinet-lookback-days"
        if requested_days is not None
        else "設定 daily"
    )
    return days, limit, source


def build_daily_update_steps(
    *,
    ticker: str | None,
    limit: int,
    force: bool,
    dry_run: bool,
    settings: dict,
    edinet_dates: Sequence,
    edinet_limit: int,
    verbose: bool,
    db_path: Path | str = DB_PATH,
) -> list[tuple[str, Callable[[], JobResult]]]:
    """Build the shared daily-update steps for CLI and future startup callers."""

    def show_edinet_progress(row: dict) -> None:
        if verbose:
            print(
                f"{row['date']} API取得={row['api_documents']} "
                f"ticker一致={row['security_matches']} "
                f"対象書類={row['target_documents']} 保存候補={row['inserted']} "
                f"重複={row['duplicates']} 失敗={row['failed']}"
            )

    def edinet_step() -> JobResult:
        key = api_key()
        if not key:
            return JobResult(processed=1, failed=1, message="EDINET_API_KEYが未設定です。")
        return run_edinet_range(
            EdinetApiClient(key),
            target_dates=edinet_dates,
            ticker=ticker,
            limit=edinet_limit,
            dry_run=dry_run,
            db_path=db_path,
            progress=show_edinet_progress,
        )

    return [
        (
            "rss",
            lambda: run_news_job(
                lambda source: RssNewsProvider(source["url"], max_items=limit),
                limit=limit,
                dry_run=dry_run,
                db_path=db_path,
            ),
        ),
        (
            "earnings",
            lambda: run_earnings_job(
                build_default_earnings_provider(
                    db_path=db_path,
                    dry_run=dry_run,
                    force_ir=force,
                ),
                ticker=ticker,
                limit=limit,
                force=force,
                dry_run=dry_run,
                include_all_holdings=True,
                db_path=db_path,
            ),
        ),
        ("edinet", edinet_step),
        (
            "stock_profiles",
            lambda: run_profile_refresh(
                YFinanceStockProfileProvider(),
                ticker=ticker,
                limit=limit,
                dry_run=dry_run,
                db_path=db_path,
            ),
        ),
        (
            "candidate_cleanup",
            lambda: run_candidate_cleanup(
                int(settings["earnings_auto_fetch"]["candidate_retention_days"]),
                dry_run=dry_run,
                db_path=db_path,
            ),
        ),
    ]


def main(argv: Sequence[str] | None = None, db_path: Path | str = DB_PATH) -> int:
    """Run RSS, earnings, EDINET, profiles, then reviewed-candidate cleanup."""
    raw_argv = list(argv) if argv is not None else sys.argv[1:]
    parser = build_parser("無料データ取得を順番に一括実行します。")
    parser.add_argument(
        "--edinet-lookback-days",
        "--lookback-days",
        dest="edinet_lookback_days",
        type=int,
        help="EDINETの日次確認日数（1から365）",
    )
    args = parser.parse_args(raw_argv)
    ticker = prepare(args, db_path)
    settings = load_settings(db_path)
    edinet_days, edinet_limit, edinet_source = resolve_daily_edinet_options(
        args, raw_argv, settings
    )
    edinet_dates = lookback_dates(japan_today(), edinet_days)

    steps = build_daily_update_steps(
        ticker=ticker,
        limit=args.limit,
        force=args.force,
        dry_run=args.dry_run,
        settings=settings,
        edinet_dates=edinet_dates,
        edinet_limit=edinet_limit,
        verbose=args.verbose,
        db_path=db_path,
    )
    result = run_steps(
        "run_daily_update",
        steps,
        dry_run=args.dry_run,
        target_count=args.limit,
        db_path=db_path,
    )
    if args.verbose:
        print_edinet_summary(
            result,
            lookback_days=edinet_days,
            limit=edinet_limit,
            source=edinet_source,
        )
    print_result(result)
    return exit_code(result)


if __name__ == "__main__":
    raise SystemExit(run_main(main))
