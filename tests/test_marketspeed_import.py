"""MarketSpeed portfolio CSV parsing and protected import tests."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from services.company_profile import update_company_metadata
from services.database import add_stock, connect, get_stock, init_db
from services.marketspeed_import import (
    build_marketspeed_preview,
    detect_csv_encoding,
    import_marketspeed_preview,
    parse_market_number,
    parse_marketspeed_csv,
)

HEADER = (
    '"売り","コード","銘柄名","口座区分","保有数量(株/口)",'
    '"評価損益額(円)","評価損益率(％)","配当利回り(％)","PER","PBR",'
    '"前日比(円)","前日比率(％)","決算日","平均取得価額(円)",'
    '"JAX時価(円)","時価(円)","時価評価額(円)","発注数量(株/口)",'
    '"銘柄情報等","JNX時価(円)"'
)


def row(
    code: str,
    name: str,
    account: str,
    shares: str,
    average_price: str,
    *,
    profit: str = "+1,234",
) -> str:
    return (
        f'"売り","{code}","{name}","{account}","{shares}","{profit}",'
        f'"+1.23","2.50","12.3","1.2","+10","+0.5","03/31",'
        f'"{average_price}","-","2,000","200,000","0","決算","-"'
    )


def csv_bytes(*rows: str, encoding: str = "utf-8-sig") -> bytes:
    return ("\n".join((HEADER, *rows)) + "\n").encode(encoding)


def test_encoding_detection_utf8_bom_and_cp932() -> None:
    assert detect_csv_encoding(csv_bytes(row("3687", "フィックスターズ", "特定", "100", "1,500")))[1] == "UTF-8 BOM"
    cp932 = csv_bytes(
        row("3687", "フィックスターズ", "特定", "100", "1,500"),
        encoding="cp932",
    )
    assert detect_csv_encoding(cp932)[1] == "CP932"


def test_numeric_parser_handles_commas_plus_percent_and_missing() -> None:
    assert parse_market_number("+1,234.50") == 1234.5
    assert parse_market_number("+12.3％") == 12.3
    assert parse_market_number("-") is None
    assert parse_market_number("") is None


def test_numeric_and_alpha_tickers_and_weighted_account_merge() -> None:
    parsed = parse_marketspeed_csv(
        csv_bytes(
            row("3687", "フィックスターズ", "特定", "100", "1,500"),
            row("3687", "フィックスターズ", "NISA", "100", "1,700"),
            row("285A", "英字コードETF", "特定", "10", "2,000"),
        )
    )
    assert len(parsed["records"]) == 2
    assert parsed["duplicate_groups"] == 1
    numeric = next(item for item in parsed["records"] if item["ticker"] == "3687.T")
    assert numeric["shares"] == 200
    assert numeric["average_price"] == 1600
    assert numeric["account_memo"] == (
        "口座内訳: 特定 100株 @1,500円 / NISA 100株 @1,700円"
    )
    assert {item["ticker"] for item in parsed["records"]} == {"3687.T", "285A.T"}


def test_invalid_row_does_not_stop_other_rows() -> None:
    parsed = parse_marketspeed_csv(
        csv_bytes(
            row("3687", "正常", "特定", "100", "1,500"),
            row("BAD", "不正", "特定", "100", "1,500"),
        )
    )
    assert [item["ticker"] for item in parsed["records"]] == ["3687.T"]
    assert len(parsed["errors"]) == 1


def seed_existing(db: Path) -> None:
    with connect(db) as conn:
        conn.execute(
            """UPDATE stocks SET company_name='既存会社',category='保有株',is_holding=1,
               shares=50,average_price=1000,buy_watch_price=900,memo='ユーザーメモ',
               company_alias='既存略称',market='東証',industry='電機'
               WHERE ticker='5801.T'"""
        )
        stock_id = conn.execute(
            "SELECT id FROM stocks WHERE ticker='5801.T'"
        ).fetchone()[0]
        conn.execute(
            """INSERT INTO stock_news_keywords
            (stock_id,keyword,is_enabled,created_at,updated_at)
            VALUES (?,?,1,'2026-01-01','2026-01-01')""",
            (stock_id, "維持キーワード"),
        )
    add_stock(
        {
            "ticker": "7203",
            "company_name": "CSVにない保有株",
            "category": "保有株",
            "is_holding": True,
            "shares": 10,
            "average_price": 2000,
            "memo": "維持",
        },
        db,
    )


def test_update_preserves_watch_memo_metadata_keywords_and_missing_holdings(
    tmp_path: Path,
) -> None:
    db = tmp_path / "test.db"
    init_db(db)
    seed_existing(db)
    parsed = parse_marketspeed_csv(
        csv_bytes(
            row("5801", "更新会社", "特定", "100", "1,500"),
            row("5801", "更新会社", "NISA", "100", "1,700"),
        ),
        "portfolio.csv",
    )
    preview = build_marketspeed_preview(parsed, "update", db)
    assert preview["summary"]["updated"] == 1
    assert [row["ticker"] for row in preview["missing_holdings"]] == ["7203.T"]
    result = import_marketspeed_preview(preview, db)
    assert result["updated"] == 1
    stock = get_stock("5801.T", db)
    assert stock["company_name"] == "更新会社"
    assert stock["shares"] == 200
    assert stock["average_price"] == 1600
    assert stock["buy_watch_price"] == 900
    assert stock["memo"].startswith("ユーザーメモ\n口座内訳:")
    assert stock["company_alias"] == "既存略称"
    assert stock["market"] == "東証"
    assert stock["industry"] == "電機"
    assert get_stock("7203.T", db)["is_holding"] == 1
    with sqlite3.connect(db) as conn:
        assert conn.execute(
            "SELECT keyword FROM stock_news_keywords"
        ).fetchone()[0] == "維持キーワード"


@pytest.mark.parametrize("policy", ["skip", "new_only"])
def test_existing_skip_policies_and_new_insert(tmp_path: Path, policy: str) -> None:
    db = tmp_path / "test.db"
    init_db(db)
    parsed = parse_marketspeed_csv(
        csv_bytes(
            row("5801", "更新しない", "特定", "100", "1,500"),
            row("285A", "新規ETF", "NISA", "10", "2,000"),
        )
    )
    preview = build_marketspeed_preview(parsed, policy, db)
    result = import_marketspeed_preview(preview, db)
    assert result["inserted"] == 1
    assert result["skipped"] == 1
    assert get_stock("5801.T", db)["company_name"] != "更新しない"
    assert get_stock("285A.T", db)["is_holding"] == 1


def test_preview_and_parse_never_change_database(tmp_path: Path) -> None:
    db = tmp_path / "test.db"
    init_db(db)
    with sqlite3.connect(db) as conn:
        before = conn.execute("SELECT * FROM stocks ORDER BY id").fetchall()
    parsed = parse_marketspeed_csv(
        csv_bytes(row("3687", "フィックスターズ", "特定", "100", "1,500"))
    )
    build_marketspeed_preview(parsed, "update", db)
    with sqlite3.connect(db) as conn:
        after = conn.execute("SELECT * FROM stocks ORDER BY id").fetchall()
    assert after == before
