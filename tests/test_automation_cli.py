"""CLI contract tests without external communication."""

from __future__ import annotations

from datetime import date
from argparse import Namespace
from pathlib import Path

import pytest

from scripts.fetch_edinet import (
    build_edinet_parser,
    resolve_fetch_options,
    resolve_target_dates,
)
from scripts.common import build_parser, run_main
from scripts.run_daily_update import resolve_daily_edinet_options
from scripts.run_edinet_backfill import resolve_backfill_options


def test_all_common_cli_flags_are_available() -> None:
    args = build_parser("test").parse_args(
        ["--dry-run", "--ticker", "5801", "--limit", "3", "--force", "--verbose"]
    )
    assert args.dry_run is True
    assert args.ticker == "5801"
    assert args.limit == 3
    assert args.force is True
    assert args.verbose is True


def test_configuration_error_exit_code() -> None:
    def raises(_argv=None):
        raise ValueError("bad config")

    assert run_main(raises, []) == 2


def test_edinet_date_and_lookback_options() -> None:
    parser = build_edinet_parser()
    date_args = parser.parse_args(["--date", "2026-07-16"])
    assert resolve_target_dates(date_args, date(2026, 7, 20)) == [date(2026, 7, 16)]
    lookback_args = parser.parse_args(["--lookback-days", "2"])
    assert resolve_target_dates(lookback_args, date(2026, 7, 20)) == [
        date(2026, 7, 20),
        date(2026, 7, 19),
    ]


def test_edinet_date_and_lookback_are_mutually_exclusive() -> None:
    with pytest.raises(SystemExit):
        build_edinet_parser().parse_args(
            ["--date", "2026-07-16", "--lookback-days", "2"]
        )


def edinet_settings() -> dict[str, int]:
    return {
        "edinet_daily_lookback_days": 3,
        "edinet_monthly_lookback_days": 30,
        "edinet_initial_backfill_days": 90,
        "edinet_fetch_limit": 20,
    }


def test_edinet_daily_monthly_and_initial_setting_defaults() -> None:
    parser = build_edinet_parser()
    daily_dates, daily_limit, daily_source = resolve_fetch_options(
        parser.parse_args([]), [], edinet_settings(), date(2026, 7, 20)
    )
    monthly_dates, _, monthly_source = resolve_fetch_options(
        parser.parse_args(["--preset", "monthly"]),
        ["--preset", "monthly"],
        edinet_settings(),
        date(2026, 7, 20),
    )
    initial_dates, _, initial_source = resolve_fetch_options(
        parser.parse_args(["--preset", "initial"]),
        ["--preset", "initial"],
        edinet_settings(),
        date(2026, 7, 20),
    )
    assert len(daily_dates) == 3 and daily_limit == 20 and daily_source == "設定 daily"
    assert len(monthly_dates) == 30 and monthly_source == "設定 monthly"
    assert len(initial_dates) == 90 and initial_source == "設定 initial"


def test_edinet_cli_values_override_settings() -> None:
    parser = build_edinet_parser()
    args = parser.parse_args(["--lookback-days", "7", "--limit", "45"])
    dates, limit, source = resolve_fetch_options(
        args,
        ["--lookback-days", "7", "--limit", "45"],
        edinet_settings(),
        date(2026, 7, 20),
    )
    assert len(dates) == 7
    assert limit == 45
    assert source == "CLI --lookback-days"

    daily = Namespace(edinet_lookback_days=5, limit=40)
    assert resolve_daily_edinet_options(
        daily,
        ["--edinet-lookback-days", "5", "--limit", "40"],
        edinet_settings(),
    ) == (5, 40, "CLI --edinet-lookback-days")

    backfill = Namespace(days=120, limit=60)
    assert resolve_backfill_options(
        backfill,
        ["--days", "120", "--limit", "60"],
        edinet_settings(),
    ) == (120, 60, "CLI --days")


def test_daily_and_backfill_use_settings_when_not_explicit() -> None:
    daily = Namespace(edinet_lookback_days=None, limit=20)
    backfill = Namespace(days=None, limit=20)
    assert resolve_daily_edinet_options(daily, [], edinet_settings()) == (
        3,
        20,
        "設定 daily",
    )
    assert resolve_backfill_options(backfill, [], edinet_settings()) == (
        90,
        20,
        "設定 initial",
    )
