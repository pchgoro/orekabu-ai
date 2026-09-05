"""Theme categories, category price lines, and stock trade notes."""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

from services.database import _now, connect
from utils.constants import DB_PATH


def list_categories(
    db_path: Path | str = DB_PATH, *, include_inactive: bool = False,
) -> list[dict[str, Any]]:
    """Return category masters with stock and information counts."""
    where = "" if include_inactive else "WHERE c.is_active=1"
    with connect(db_path) as conn:
        rows = conn.execute(
            f"""SELECT c.*, r.stop_loss_price, r.take_profit_price, r.add_position_price,
                   r.memo AS rule_memo,
                   COUNT(DISTINCT sc.stock_id) AS stock_count,
                   COUNT(DISTINCT na.article_id) AS news_count,
                   COUNT(DISTINCT ee.id) AS earnings_count,
                   COUNT(DISTINCT d.id) AS disclosure_count
            FROM categories c
            LEFT JOIN category_rules r ON r.category_id=c.id
            LEFT JOIN stock_categories sc ON sc.category_id=c.id
            LEFT JOIN news_article_stocks na ON na.stock_id=sc.stock_id
            LEFT JOIN earnings_events ee ON ee.stock_id=sc.stock_id
            LEFT JOIN disclosures d ON d.stock_id=sc.stock_id
            {where}
            GROUP BY c.id
            ORDER BY c.is_active DESC, c.name COLLATE NOCASE"""
        ).fetchall()
    return [dict(row) for row in rows]


def save_category(
    name: str, description: str = "", color_key: str = "info", *,
    category_id: int | None = None, db_path: Path | str = DB_PATH,
) -> int:
    """Create or edit one category without modifying stock assignments."""
    normalized_name = str(name or "").strip()[:80]
    if not normalized_name:
        raise ValueError("カテゴリ名を入力してください。")
    now = _now()
    with connect(db_path) as conn:
        if category_id is None:
            cursor = conn.execute(
                """INSERT INTO categories(name,description,color_key,is_active,created_at,updated_at)
                VALUES(?,?,?,1,?,?)""",
                (normalized_name, str(description or "").strip()[:1000], str(color_key or "info")[:30], now, now),
            )
            return int(cursor.lastrowid)
        cursor = conn.execute(
            """UPDATE categories SET name=?,description=?,color_key=?,updated_at=? WHERE id=?""",
            (normalized_name, str(description or "").strip()[:1000], str(color_key or "info")[:30], now, int(category_id)),
        )
        if not cursor.rowcount:
            raise ValueError("カテゴリが見つかりません。")
        return int(category_id)


def set_category_active(category_id: int, is_active: bool, db_path: Path | str = DB_PATH) -> None:
    """Safely deactivate a category while preserving existing assignments."""
    with connect(db_path) as conn:
        if not conn.execute(
            "UPDATE categories SET is_active=?,updated_at=? WHERE id=?",
            (int(bool(is_active)), _now(), int(category_id)),
        ).rowcount:
            raise ValueError("カテゴリが見つかりません。")


def delete_category(category_id: int, db_path: Path | str = DB_PATH) -> None:
    """Delete an unused category; assigned categories must be deactivated first."""
    with connect(db_path) as conn:
        assigned = conn.execute(
            "SELECT COUNT(*) FROM stock_categories WHERE category_id=?", (int(category_id),)
        ).fetchone()[0]
        if assigned:
            raise ValueError("割り当て済みのカテゴリは削除せず、無効化してください。")
        if not conn.execute("DELETE FROM categories WHERE id=?", (int(category_id),)).rowcount:
            raise ValueError("カテゴリが見つかりません。")


def list_stock_categories(stock_id: int, db_path: Path | str = DB_PATH) -> list[dict[str, Any]]:
    """Return all categories assigned to one stock."""
    with connect(db_path) as conn:
        rows = conn.execute(
            """SELECT c.* FROM stock_categories sc JOIN categories c ON c.id=sc.category_id
            WHERE sc.stock_id=? ORDER BY c.name COLLATE NOCASE""",
            (int(stock_id),),
        ).fetchall()
    return [dict(row) for row in rows]


def replace_stock_categories(stock_id: int, category_ids: list[int], db_path: Path | str = DB_PATH) -> None:
    """Replace category assignments atomically, keeping only active categories."""
    desired = sorted({int(item) for item in category_ids})
    now = _now()
    with connect(db_path) as conn:
        if not conn.execute("SELECT 1 FROM stocks WHERE id=?", (int(stock_id),)).fetchone():
            raise ValueError("銘柄が見つかりません。")
        if desired:
            placeholders = ",".join("?" for _ in desired)
            count = conn.execute(
                f"SELECT COUNT(*) FROM categories WHERE id IN ({placeholders}) AND is_active=1", desired
            ).fetchone()[0]
            if count != len(desired):
                raise ValueError("無効または存在しないカテゴリが含まれます。")
        conn.execute("DELETE FROM stock_categories WHERE stock_id=?", (int(stock_id),))
        conn.executemany(
            "INSERT INTO stock_categories(stock_id,category_id,created_at) VALUES(?,?,?)",
            [(int(stock_id), category_id, now) for category_id in desired],
        )


def get_category_rule(category_id: int, db_path: Path | str = DB_PATH) -> dict[str, Any] | None:
    """Return optional fixed price lines for a category."""
    with connect(db_path) as conn:
        row = conn.execute("SELECT * FROM category_rules WHERE category_id=?", (int(category_id),)).fetchone()
    return dict(row) if row else None


def save_category_rule(category_id: int, payload: dict[str, Any], db_path: Path | str = DB_PATH) -> None:
    """Upsert optional category price lines without applying them to stocks."""
    values = [_optional_price(payload.get(key), label) for key, label in (
        ("stop_loss_price", "損切りライン"),
        ("take_profit_price", "利確ライン"),
        ("add_position_price", "買い増しライン"),
    )]
    now = _now()
    with connect(db_path) as conn:
        if not conn.execute("SELECT 1 FROM categories WHERE id=?", (int(category_id),)).fetchone():
            raise ValueError("カテゴリが見つかりません。")
        conn.execute(
            """INSERT INTO category_rules(category_id,stop_loss_price,take_profit_price,add_position_price,memo,created_at,updated_at)
            VALUES(?,?,?,?,?,?,?) ON CONFLICT(category_id) DO UPDATE SET
                stop_loss_price=excluded.stop_loss_price,take_profit_price=excluded.take_profit_price,
                add_position_price=excluded.add_position_price,memo=excluded.memo,updated_at=excluded.updated_at""",
            (int(category_id), *values, str(payload.get("memo") or "").strip()[:2000], now, now),
        )


def get_trade_notes(stock_id: int, db_path: Path | str = DB_PATH) -> dict[str, Any]:
    """Return stored trade notes or an empty editable value object."""
    with connect(db_path) as conn:
        row = conn.execute("SELECT * FROM trade_notes WHERE stock_id=?", (int(stock_id),)).fetchone()
    return dict(row) if row else {"stock_id": int(stock_id), "holding_reason": "", "sell_conditions": "", "memo": ""}


def save_trade_notes(stock_id: int, payload: dict[str, Any], db_path: Path | str = DB_PATH) -> None:
    """Upsert user-authored rationale, exit conditions, and free notes."""
    fields = tuple(str(payload.get(key) or "").strip()[:10000] for key in ("holding_reason", "sell_conditions", "memo"))
    now = _now()
    with connect(db_path) as conn:
        if not conn.execute("SELECT 1 FROM stocks WHERE id=?", (int(stock_id),)).fetchone():
            raise ValueError("銘柄が見つかりません。")
        conn.execute(
            """INSERT INTO trade_notes(stock_id,holding_reason,sell_conditions,memo,created_at,updated_at)
            VALUES(?,?,?,?,?,?) ON CONFLICT(stock_id) DO UPDATE SET
                holding_reason=excluded.holding_reason,sell_conditions=excluded.sell_conditions,
                memo=excluded.memo,updated_at=excluded.updated_at""",
            (int(stock_id), *fields, now, now),
        )


def enrich_rows_with_categories(rows: list[dict[str, Any]], db_path: Path | str = DB_PATH) -> list[dict[str, Any]]:
    """Attach compact category names and the first configured category rule to rows."""
    with connect(db_path) as conn:
        category_rows = conn.execute(
            """SELECT sc.stock_id,c.id,c.name,r.stop_loss_price,r.take_profit_price,r.add_position_price
            FROM stock_categories sc JOIN categories c ON c.id=sc.category_id
            LEFT JOIN category_rules r ON r.category_id=c.id WHERE c.is_active=1
            ORDER BY c.name"""
        ).fetchall()
    by_stock: dict[int, list[dict[str, Any]]] = {}
    for row in category_rows:
        by_stock.setdefault(int(row["stock_id"]), []).append(dict(row))
    result: list[dict[str, Any]] = []
    for row in rows:
        categories = by_stock.get(int(row.get("id") or 0), [])
        rule = next((item for item in categories if any(item.get(key) is not None for key in ("stop_loss_price", "take_profit_price", "add_position_price"))), None)
        result.append({**row, "stock_categories": categories, "category_rule": rule})
    return result


def _optional_price(value: Any, label: str) -> float | None:
    if value in (None, ""):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label}は数値で入力してください。") from exc
    if not math.isfinite(number) or number <= 0:
        raise ValueError(f"{label}は0より大きい数値で入力してください。")
    return number
