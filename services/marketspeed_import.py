"""Rakuten MarketSpeed portfolio CSV parsing, preview, and safe import."""

from __future__ import annotations

import csv
import io
import logging
import math
from collections import defaultdict
from pathlib import Path
from typing import Any

from services.database import _now, add_stock, connect, get_stocks
from utils.constants import DB_PATH
from utils.validators import normalize_ticker

logger = logging.getLogger(__name__)

REQUIRED_COLUMNS = (
    "コード",
    "銘柄名",
    "口座区分",
    "保有数量(株/口)",
    "平均取得価額(円)",
)
POLICIES = ("update", "skip", "new_only")
ACCOUNT_MEMO_PREFIX = "口座内訳:"


def detect_csv_encoding(content: bytes) -> tuple[str, str]:
    """Decode UTF-8 BOM, UTF-8, or CP932 CSV bytes."""
    if content.startswith(b"\xef\xbb\xbf"):
        return content.decode("utf-8-sig"), "UTF-8 BOM"
    try:
        return content.decode("utf-8"), "UTF-8"
    except UnicodeDecodeError:
        try:
            return content.decode("cp932"), "CP932"
        except UnicodeDecodeError as exc:
            raise ValueError("文字コードを判定できませんでした。") from exc


def parse_market_number(value: Any) -> float | None:
    """Parse MarketSpeed numeric text while treating dashes and blanks as missing."""
    text = str(value or "").strip()
    if text in {"", "-", "－", "―"}:
        return None
    normalized = (
        text.replace(",", "")
        .replace("+", "")
        .replace("%", "")
        .replace("％", "")
        .strip()
    )
    try:
        number = float(normalized)
    except ValueError as exc:
        raise ValueError(f"数値として読み込めません: {text}") from exc
    if not math.isfinite(number):
        raise ValueError(f"有限の数値ではありません: {text}")
    return number


def _parse_shares(value: Any) -> int:
    number = parse_market_number(value)
    if number is None:
        raise ValueError("保有数量が空です。")
    if number < 0 or not number.is_integer():
        raise ValueError("保有数量は0以上の整数である必要があります。")
    return int(number)


def _format_number(value: float) -> str:
    return f"{value:,.0f}" if float(value).is_integer() else f"{value:,.2f}".rstrip("0").rstrip(".")


def _account_memo(accounts: list[dict[str, Any]]) -> str:
    parts = [
        f"{row['account'] or '区分未設定'} {row['shares']:,}株 @{_format_number(row['average_price'])}円"
        for row in accounts
    ]
    return f"{ACCOUNT_MEMO_PREFIX} {' / '.join(parts)}"


def merge_account_memo(existing_memo: str, account_memo: str) -> str:
    """Replace only the generated account breakdown and retain user-authored memo lines."""
    user_lines = [
        line
        for line in str(existing_memo or "").splitlines()
        if not line.strip().startswith(ACCOUNT_MEMO_PREFIX)
    ]
    return "\n".join([*user_lines, account_memo]).strip()


def parse_marketspeed_csv(content: bytes, filename: str = "") -> dict[str, Any]:
    """Parse and aggregate MarketSpeed rows without touching the database."""
    text, encoding = detect_csv_encoding(content)
    reader = csv.DictReader(io.StringIO(text))
    columns = tuple(reader.fieldnames or ())
    missing = [column for column in REQUIRED_COLUMNS if column not in columns]
    if missing:
        raise ValueError(f"必要なCSV列が不足しています: {', '.join(missing)}")

    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    errors: list[str] = []
    raw_count = 0
    for line_number, row in enumerate(reader, start=2):
        raw_count += 1
        try:
            ticker = normalize_ticker(row.get("コード"))
            shares = _parse_shares(row.get("保有数量(株/口)"))
            average_price = parse_market_number(row.get("平均取得価額(円)"))
            if shares > 0 and average_price is None:
                raise ValueError("平均取得価額が空です。")
            if average_price is not None and average_price < 0:
                raise ValueError("平均取得価額は0以上である必要があります。")
            groups[ticker].append(
                {
                    "line_number": line_number,
                    "ticker": ticker,
                    "company_name": str(row.get("銘柄名") or "").strip() or ticker,
                    "account": str(row.get("口座区分") or "").strip(),
                    "shares": shares,
                    "average_price": float(average_price or 0),
                    "supplementary": {
                        "評価損益額": parse_market_number(row.get("評価損益額(円)")),
                        "評価損益率": parse_market_number(row.get("評価損益率(％)")),
                        "配当利回り": parse_market_number(row.get("配当利回り(％)")),
                        "PER": parse_market_number(row.get("PER")),
                        "PBR": parse_market_number(row.get("PBR")),
                        "前日比": parse_market_number(row.get("前日比(円)")),
                        "前日比率": parse_market_number(row.get("前日比率(％)")),
                        "決算日": str(row.get("決算日") or "").strip(),
                        "時価": parse_market_number(row.get("時価(円)")),
                        "時価評価額": parse_market_number(row.get("時価評価額(円)")),
                    },
                }
            )
        except Exception as exc:
            errors.append(f"{line_number}行目: {exc}")

    records: list[dict[str, Any]] = []
    duplicate_groups = 0
    for ticker, rows in groups.items():
        if len(rows) > 1:
            duplicate_groups += 1
        total_shares = sum(row["shares"] for row in rows)
        weighted_total = sum(row["shares"] * row["average_price"] for row in rows)
        average_price = weighted_total / total_shares if total_shares else 0.0
        accounts = [
            {
                "account": row["account"],
                "shares": row["shares"],
                "average_price": row["average_price"],
            }
            for row in rows
        ]
        records.append(
            {
                "ticker": ticker,
                "company_name": rows[0]["company_name"],
                "accounts": accounts,
                "account_summary": " / ".join(
                    f"{row['account'] or '区分未設定'} {row['shares']:,}株"
                    for row in accounts
                ),
                "shares": total_shares,
                "average_price": average_price,
                "account_memo": _account_memo(accounts),
                "source_rows": len(rows),
                "supplementary": [row["supplementary"] for row in rows],
            }
        )
    records.sort(key=lambda row: row["ticker"])
    return {
        "filename": filename,
        "encoding": encoding,
        "row_count": raw_count,
        "records": records,
        "errors": errors,
        "duplicate_groups": duplicate_groups,
    }


def build_marketspeed_preview(
    parsed: dict[str, Any],
    policy: str,
    db_path: Path | str = DB_PATH,
) -> dict[str, Any]:
    """Compare aggregated records with current DB values for a selected policy."""
    if policy not in POLICIES:
        raise ValueError("更新方針が不正です。")
    existing_by_ticker = {row["ticker"]: row for row in get_stocks(db_path)}
    preview: list[dict[str, Any]] = []
    summary = {
        "csv_rows": int(parsed["row_count"]),
        "stocks": len(parsed["records"]),
        "new": 0,
        "updated": 0,
        "same": 0,
        "skipped": 0,
        "duplicates": int(parsed["duplicate_groups"]),
        "errors": len(parsed["errors"]),
    }
    imported_tickers: set[str] = set()
    for record in parsed["records"]:
        ticker = record["ticker"]
        imported_tickers.add(ticker)
        existing = existing_by_ticker.get(ticker)
        target_memo = merge_account_memo(
            str(existing.get("memo") or "") if existing else "",
            record["account_memo"],
        )
        incoming = {
            "company_name": record["company_name"],
            "shares": record["shares"],
            "average_price": record["average_price"],
            "memo": target_memo,
        }
        if existing is None:
            decision = "新規"
            summary["new"] += 1
        else:
            same = (
                str(existing["company_name"]) == incoming["company_name"]
                and bool(existing["is_holding"])
                and str(existing["category"]) == "保有株"
                and int(existing["shares"]) == incoming["shares"]
                and math.isclose(float(existing["average_price"]), incoming["average_price"], abs_tol=0.005)
                and str(existing.get("memo") or "") == target_memo
            )
            if same:
                decision = "同一"
                summary["same"] += 1
            elif policy == "update":
                decision = "更新"
                summary["updated"] += 1
            else:
                decision = "スキップ"
                summary["skipped"] += 1
        preview.append(
            {
                **record,
                "current_company_name": existing.get("company_name") if existing else None,
                "current_shares": existing.get("shares") if existing else None,
                "current_average_price": existing.get("average_price") if existing else None,
                "current_buy_watch_price": existing.get("buy_watch_price") if existing else None,
                "current_memo": existing.get("memo") if existing else None,
                "import_memo": target_memo,
                "decision": decision,
            }
        )
    missing_holdings = [
        row
        for row in existing_by_ticker.values()
        if row.get("is_holding") and row["ticker"] not in imported_tickers
    ]
    return {
        **parsed,
        "policy": policy,
        "preview": preview,
        "summary": summary,
        "missing_holdings": missing_holdings,
    }


def import_marketspeed_preview(
    preview_result: dict[str, Any],
    db_path: Path | str = DB_PATH,
) -> dict[str, Any]:
    """Import previewed rows independently while preserving unrelated stock data."""
    result = {
        "inserted": 0,
        "updated": 0,
        "unchanged": 0,
        "skipped": 0,
        "failed": 0,
        "errors": [],
    }
    for row in preview_result["preview"]:
        try:
            if row["decision"] == "同一":
                result["unchanged"] += 1
                continue
            if row["decision"] == "スキップ":
                result["skipped"] += 1
                continue
            if row["decision"] == "新規":
                add_stock(
                    {
                        "ticker": row["ticker"],
                        "company_name": row["company_name"],
                        "category": "保有株",
                        "is_holding": True,
                        "shares": row["shares"],
                        "average_price": row["average_price"],
                        "buy_watch_price": 0,
                        "memo": row["import_memo"],
                    },
                    db_path,
                )
                result["inserted"] += 1
                continue
            with connect(db_path) as conn:
                cursor = conn.execute(
                    """UPDATE stocks
                    SET company_name=?,category='保有株',is_holding=1,shares=?,
                        average_price=?,memo=?,updated_at=?
                    WHERE ticker=?""",
                    (
                        row["company_name"],
                        row["shares"],
                        row["average_price"],
                        row["import_memo"],
                        _now(),
                        row["ticker"],
                    ),
                )
                if cursor.rowcount != 1:
                    raise ValueError("更新対象の銘柄が見つかりません。")
            result["updated"] += 1
        except Exception as exc:
            result["failed"] += 1
            result["errors"].append(f"{row['ticker']}: {exc}")
            logger.exception("MarketSpeed CSV import failed ticker=%s", row["ticker"])
    logger.info(
        "MarketSpeed CSV imported file=%s rows=%s inserted=%s updated=%s skipped=%s failed=%s",
        preview_result.get("filename") or "",
        preview_result.get("row_count") or 0,
        result["inserted"],
        result["updated"],
        result["skipped"],
        result["failed"],
    )
    return result
