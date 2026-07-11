"""Directed related-stock management and earnings impact candidates."""

from __future__ import annotations

import csv
import io
import logging
from pathlib import Path
from typing import Any

import pandas as pd

from services.database import _now, connect, get_stock
from services.earnings import earnings_date_info, japan_today
from utils.constants import DB_PATH, IMPACT_LEVELS, RELATION_TYPES
from utils.validators import normalize_ticker

logger = logging.getLogger(__name__)
RELATIONS_CSV_COLUMNS = ["source_ticker", "related_ticker", "relation_type", "impact_level", "memo"]


def validate_relation_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Validate relation direction, type, and impact."""
    source_id, related_id = int(payload.get("source_stock_id")), int(payload.get("related_stock_id"))
    if source_id == related_id:
        raise ValueError("自分自身を関連銘柄には登録できません。")
    relation_type = str(payload.get("relation_type") or "その他")
    impact_level = str(payload.get("impact_level") or "中")
    if relation_type not in RELATION_TYPES:
        raise ValueError("関係タイプが不正です。")
    if impact_level not in IMPACT_LEVELS:
        raise ValueError("影響度が不正です。")
    return {"source_stock_id": source_id, "related_stock_id": related_id, "relation_type": relation_type, "impact_level": impact_level, "memo": str(payload.get("memo") or "").strip()}


def list_relations(db_path: Path | str = DB_PATH) -> list[dict[str, Any]]:
    """List directed relations with both stock names."""
    with connect(db_path) as conn:
        rows = conn.execute(
            """SELECT r.*, s.ticker source_ticker, s.company_name source_company_name,
               s.is_holding source_is_holding, t.ticker related_ticker, t.company_name related_company_name
               FROM stock_relations r JOIN stocks s ON s.id=r.source_stock_id
               JOIN stocks t ON t.id=r.related_stock_id
               ORDER BY s.ticker, t.ticker"""
        ).fetchall()
    return [dict(row) for row in rows]


def get_stock_relations(stock_id: int, db_path: Path | str = DB_PATH) -> list[dict[str, Any]]:
    """Return outgoing relations for a source stock."""
    return [row for row in list_relations(db_path) if int(row["source_stock_id"]) == int(stock_id)]


def add_relation(payload: dict[str, Any], db_path: Path | str = DB_PATH) -> int:
    """Insert a directed stock relation."""
    item = validate_relation_payload(payload)
    now = _now()
    with connect(db_path) as conn:
        cursor = conn.execute(
            """INSERT INTO stock_relations
               (source_stock_id,related_stock_id,relation_type,impact_level,memo,created_at,updated_at)
               VALUES (?,?,?,?,?,?,?)""", (*item.values(), now, now)
        )
        return int(cursor.lastrowid)


def update_relation(relation_id: int, payload: dict[str, Any], db_path: Path | str = DB_PATH) -> None:
    """Update a directed stock relation."""
    item = validate_relation_payload(payload)
    with connect(db_path) as conn:
        cursor = conn.execute(
            """UPDATE stock_relations SET source_stock_id=?,related_stock_id=?,relation_type=?,
               impact_level=?,memo=?,updated_at=? WHERE id=?""", (*item.values(), _now(), relation_id)
        )
        if cursor.rowcount == 0:
            raise ValueError("更新対象の関連銘柄が見つかりません。")


def delete_relation(relation_id: int, db_path: Path | str = DB_PATH) -> None:
    """Delete a relation and report missing ids."""
    with connect(db_path) as conn:
        cursor = conn.execute("DELETE FROM stock_relations WHERE id=?", (relation_id,))
        if cursor.rowcount == 0:
            raise ValueError("削除対象の関連銘柄が見つかりません。")


def upsert_relation(payload: dict[str, Any], update_existing: bool, db_path: Path | str = DB_PATH) -> str:
    """Insert, update, or skip a directed relation."""
    item = validate_relation_payload(payload)
    with connect(db_path) as conn:
        row = conn.execute("SELECT id FROM stock_relations WHERE source_stock_id=? AND related_stock_id=?", (item["source_stock_id"], item["related_stock_id"])).fetchone()
    if row:
        if not update_existing:
            return "skipped"
        update_relation(int(row["id"]), item, db_path)
        return "updated"
    add_relation(item, db_path)
    return "inserted"


def impact_candidates(db_path: Path | str = DB_PATH) -> list[dict[str, Any]]:
    """Return each relation with the related stock's next future earnings event."""
    with connect(db_path) as conn:
        rows = conn.execute(
            """SELECT r.*, s.ticker source_ticker, s.company_name source_company_name,
               s.is_holding source_is_holding, t.ticker related_ticker, t.company_name related_company_name,
               e.earnings_date, e.fiscal_quarter, e.date_status, e.announcement_time,
               e.memo earnings_memo
               FROM stock_relations r JOIN stocks s ON s.id=r.source_stock_id
               JOIN stocks t ON t.id=r.related_stock_id
               LEFT JOIN earnings_events e ON e.id=(
                 SELECT e2.id FROM earnings_events e2 WHERE e2.stock_id=r.related_stock_id
                 AND (e2.earnings_date >= ? OR e2.earnings_date IS NULL)
                 ORDER BY e2.earnings_date IS NULL, e2.earnings_date LIMIT 1)
               ORDER BY e.earnings_date IS NULL, e.earnings_date"""
            , (japan_today().isoformat(),)
        ).fetchall()
    result = []
    for raw in rows:
        row = dict(raw)
        row.update(earnings_date_info(row.get("earnings_date")))
        result.append(row)
    impact_order = {"高": 0, "中": 1, "低": 2}
    return sorted(result, key=lambda r: (r.get("days_until") is None, r.get("days_until") if r.get("days_until") is not None else 999999, impact_order.get(r.get("impact_level"), 9), not bool(r.get("source_is_holding"))))


def export_relations_csv(rows: list[dict[str, Any]]) -> bytes:
    """Export relations as UTF-8 BOM CSV."""
    data = [{col: row.get(col, "") or "" for col in RELATIONS_CSV_COLUMNS} for row in rows]
    return pd.DataFrame(data, columns=RELATIONS_CSV_COLUMNS).to_csv(index=False).encode("utf-8-sig")


def parse_relations_csv(uploaded_file: Any) -> tuple[pd.DataFrame, list[str]]:
    """Parse a relations CSV for preview."""
    try:
        rows = list(csv.DictReader(io.StringIO(uploaded_file.getvalue().decode("utf-8-sig"))))
        frame = pd.DataFrame(rows)
        missing = [col for col in RELATIONS_CSV_COLUMNS if col not in frame.columns]
        return (frame, [f"CSV列が不足しています: {', '.join(missing)}"]) if missing else (frame[RELATIONS_CSV_COLUMNS], [])
    except Exception as exc:
        logger.exception("関連銘柄CSV読み込みエラー")
        return pd.DataFrame(), [f"関連銘柄CSVを読み込めませんでした: {exc}"]


def import_relations_csv(frame: pd.DataFrame, update_existing: bool, db_path: Path | str = DB_PATH) -> dict[str, Any]:
    """Import directed relations independently."""
    result: dict[str, Any] = {"inserted": 0, "updated": 0, "skipped": 0, "failed": 0, "errors": []}
    for index, row in frame.iterrows():
        try:
            source = get_stock(normalize_ticker(row.get("source_ticker")), db_path)
            related = get_stock(normalize_ticker(row.get("related_ticker")), db_path)
            if source is None or related is None:
                raise ValueError("登録銘柄に存在しないtickerです。")
            status = upsert_relation({**row.to_dict(), "source_stock_id": source["id"], "related_stock_id": related["id"]}, update_existing, db_path)
            result[status] += 1
        except Exception as exc:
            result["failed"] += 1
            result["errors"].append(f"{int(index)+2}行目: {exc}")
            logger.exception("関連銘柄CSV行エラー line=%s", int(index)+2)
    return result
