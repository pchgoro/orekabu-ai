"""Fetch registered RSS/Atom news sources."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Sequence

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.common import build_parser, exit_code, prepare, print_result, run_main
from services.automation import run_steps
from services.automation_jobs import run_news_job
from services.news_providers.rss_provider import RssNewsProvider
from utils.constants import DB_PATH


def main(argv: Sequence[str] | None = None, db_path: Path | str = DB_PATH) -> int:
    """Run the RSS collector."""
    parser = build_parser("登録済みRSS/Atomソースからニュースを取得します。")
    args = parser.parse_args(argv)
    prepare(args, db_path)
    result = run_steps(
        "fetch_news",
        [
            (
                "rss",
                lambda: run_news_job(
                    lambda source: RssNewsProvider(source["url"], max_items=args.limit),
                    limit=args.limit,
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
