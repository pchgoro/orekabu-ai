"""Strategy tags, reusable rule sets, stock overrides, CSV, and summaries."""

from __future__ import annotations

import csv
import io
import math
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable

from services.database import _now, connect
from utils.constants import DB_PATH
from utils.validators import normalize_ticker

TAG_GROUPS = ("theme", "style", "horizon", "strategy", "custom")
RULE_TYPES = (
    "percent_from_average_price",
    "fixed_price",
    "percent_from_current_price",
    "none",
)
COLOR_KEYS = ("positive", "negative", "warning", "info", "muted")
RULE_ROLES = ("stop_loss", "take_profit", "add_position")


def list_tags(
    db_path: Path | str = DB_PATH, *, include_inactive: bool = True,
) -> list[dict[str, Any]]:
    """Return tags with assignment counts."""
    where = "" if include_inactive else "WHERE t.is_active=1"
    with connect(db_path) as conn:
        rows = conn.execute(
            f"""SELECT t.*,COUNT(st.id) AS stock_count
            FROM strategy_tags t
            LEFT JOIN stock_strategy_tags st ON st.tag_id=t.id
            {where}
            GROUP BY t.id
            ORDER BY t.tag_group,t.display_order,t.name"""
        ).fetchall()
    return [dict(row) for row in rows]


def save_tag(
    payload: dict[str, Any],
    db_path: Path | str = DB_PATH,
    *,
    tag_id: int | None = None,
) -> int:
    """Create or update one strategy tag."""
    name = str(payload.get("name") or "").strip()[:100]
    group = str(payload.get("tag_group") or "").strip()
    if not name:
        raise ValueError("タグ名を入力してください。")
    if group not in TAG_GROUPS:
        raise ValueError("タググループが不正です。")
    description = str(payload.get("description") or "").strip()[:1000]
    color_key = str(payload.get("color_key") or "info")
    if color_key not in COLOR_KEYS:
        color_key = "info"
    display_order = _bounded_int(payload.get("display_order"), 0, 9999)
    active = int(bool(payload.get("is_active", True)))
    now = _now()
    with connect(db_path) as conn:
        if tag_id is None:
            cursor = conn.execute(
                """INSERT INTO strategy_tags
                (name,tag_group,description,color_key,display_order,is_active,created_at,updated_at)
                VALUES(?,?,?,?,?,?,?,?)""",
                (name, group, description, color_key, display_order, active, now, now),
            )
            return int(cursor.lastrowid)
        conn.execute(
            """UPDATE strategy_tags
            SET name=?,tag_group=?,description=?,color_key=?,display_order=?,
                is_active=?,updated_at=?
            WHERE id=?""",
            (name, group, description, color_key, display_order, active, now, int(tag_id)),
        )
        return int(tag_id)


def set_tag_active(
    tag_id: int, active: bool, db_path: Path | str = DB_PATH,
) -> None:
    """Enable or disable a tag without removing assignments."""
    with connect(db_path) as conn:
        conn.execute(
            "UPDATE strategy_tags SET is_active=?,updated_at=? WHERE id=?",
            (int(active), _now(), int(tag_id)),
        )


def delete_tag(
    tag_id: int, db_path: Path | str = DB_PATH, *, force: bool = False,
) -> None:
    """Delete an unused tag or require explicit force when it has relations."""
    with connect(db_path) as conn:
        related = conn.execute(
            """SELECT
                (SELECT COUNT(*) FROM stock_strategy_tags WHERE tag_id=?) +
                (SELECT COUNT(*) FROM strategy_rule_sets WHERE tag_id=?) +
                (SELECT COUNT(*) FROM stock_trade_rules WHERE source_tag_id=?)
            """,
            (int(tag_id), int(tag_id), int(tag_id)),
        ).fetchone()[0]
        if related and not force:
            raise ValueError("関連データがあります。削除せず無効化してください。")
        conn.execute("DELETE FROM strategy_tags WHERE id=?", (int(tag_id),))


def list_stock_tags(
    stock_id: int | None = None, db_path: Path | str = DB_PATH,
) -> list[dict[str, Any]]:
    """Return active tag assignments, optionally for one stock."""
    where = "WHERE st.stock_id=?" if stock_id is not None else ""
    params: tuple[Any, ...] = (int(stock_id),) if stock_id is not None else ()
    with connect(db_path) as conn:
        rows = conn.execute(
            f"""SELECT st.id AS assignment_id,st.stock_id,t.*
            FROM stock_strategy_tags st
            JOIN strategy_tags t ON t.id=st.tag_id
            {where}
            ORDER BY t.tag_group,t.display_order,t.name""",
            params,
        ).fetchall()
    return [dict(row) for row in rows]


def replace_stock_tags(
    stock_id: int, tag_ids: Iterable[int], db_path: Path | str = DB_PATH,
) -> None:
    """Replace one stock's tag assignments in one transaction."""
    unique_ids = sorted({int(value) for value in tag_ids})
    with connect(db_path) as conn:
        if not conn.execute("SELECT 1 FROM stocks WHERE id=?", (int(stock_id),)).fetchone():
            raise ValueError("対象銘柄が見つかりません。")
        if unique_ids:
            placeholders = ",".join("?" for _ in unique_ids)
            count = conn.execute(
                f"SELECT COUNT(*) FROM strategy_tags WHERE id IN ({placeholders}) AND is_active=1",
                tuple(unique_ids),
            ).fetchone()[0]
            if int(count) != len(unique_ids):
                raise ValueError("無効または存在しないタグが含まれています。")
        conn.execute("DELETE FROM stock_strategy_tags WHERE stock_id=?", (int(stock_id),))
        now = _now()
        conn.executemany(
            "INSERT INTO stock_strategy_tags(stock_id,tag_id,created_at) VALUES(?,?,?)",
            [(int(stock_id), tag_id, now) for tag_id in unique_ids],
        )


def bulk_assign_tags(
    stock_ids: Iterable[int],
    tag_ids: Iterable[int],
    db_path: Path | str = DB_PATH,
    *,
    remove: bool = False,
) -> int:
    """Assign or remove multiple tags without disturbing other assignments."""
    stocks = sorted({int(value) for value in stock_ids})
    tags = sorted({int(value) for value in tag_ids})
    changed = 0
    with connect(db_path) as conn:
        now = _now()
        for stock_id in stocks:
            for tag_id in tags:
                if remove:
                    changed += conn.execute(
                        "DELETE FROM stock_strategy_tags WHERE stock_id=? AND tag_id=?",
                        (stock_id, tag_id),
                    ).rowcount
                else:
                    changed += conn.execute(
                        """INSERT OR IGNORE INTO stock_strategy_tags
                        (stock_id,tag_id,created_at) VALUES(?,?,?)""",
                        (stock_id, tag_id, now),
                    ).rowcount
    return changed


def get_rule_set(
    tag_id: int, db_path: Path | str = DB_PATH,
) -> dict[str, Any] | None:
    """Return one tag rule set."""
    with connect(db_path) as conn:
        row = conn.execute(
            """SELECT r.*,t.name AS tag_name,t.tag_group
            FROM strategy_rule_sets r
            JOIN strategy_tags t ON t.id=r.tag_id
            WHERE r.tag_id=?""",
            (int(tag_id),),
        ).fetchone()
    return dict(row) if row else None


def list_rule_sets(db_path: Path | str = DB_PATH) -> list[dict[str, Any]]:
    """Return all tag rule sets."""
    with connect(db_path) as conn:
        rows = conn.execute(
            """SELECT r.*,t.name AS tag_name,t.tag_group,t.is_active
            FROM strategy_rule_sets r
            JOIN strategy_tags t ON t.id=r.tag_id
            ORDER BY r.priority DESC,t.tag_group,t.display_order,t.name"""
        ).fetchall()
    return [dict(row) for row in rows]


def save_rule_set(
    tag_id: int, payload: dict[str, Any], db_path: Path | str = DB_PATH,
) -> None:
    """Validate and upsert one reusable tag rule."""
    rule = normalize_rule(payload)
    now = _now()
    with connect(db_path) as conn:
        if not conn.execute(
            "SELECT 1 FROM strategy_tags WHERE id=?", (int(tag_id),)
        ).fetchone():
            raise ValueError("対象タグが見つかりません。")
        conn.execute(
            """INSERT INTO strategy_rule_sets
            (tag_id,stop_loss_type,stop_loss_value,take_profit_type,
             take_profit_value,add_position_type,add_position_value,
             earnings_policy,priority,memo,created_at,updated_at)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(tag_id) DO UPDATE SET
                stop_loss_type=excluded.stop_loss_type,
                stop_loss_value=excluded.stop_loss_value,
                take_profit_type=excluded.take_profit_type,
                take_profit_value=excluded.take_profit_value,
                add_position_type=excluded.add_position_type,
                add_position_value=excluded.add_position_value,
                earnings_policy=excluded.earnings_policy,
                priority=excluded.priority,
                memo=excluded.memo,
                updated_at=excluded.updated_at""",
            (
                int(tag_id),
                rule["stop_loss_type"],
                rule["stop_loss_value"],
                rule["take_profit_type"],
                rule["take_profit_value"],
                rule["add_position_type"],
                rule["add_position_value"],
                rule["earnings_policy"],
                rule["priority"],
                rule["memo"],
                now,
                now,
            ),
        )


def delete_rule_set(tag_id: int, db_path: Path | str = DB_PATH) -> None:
    """Delete one reusable rule while retaining its tag."""
    with connect(db_path) as conn:
        conn.execute("DELETE FROM strategy_rule_sets WHERE tag_id=?", (int(tag_id),))


def get_stock_rule(
    stock_id: int, db_path: Path | str = DB_PATH,
) -> dict[str, Any] | None:
    """Return one explicitly applied stock rule."""
    with connect(db_path) as conn:
        row = conn.execute(
            """SELECT r.*,t.name AS source_tag_name,t.tag_group AS source_tag_group
            FROM stock_trade_rules r
            LEFT JOIN strategy_tags t ON t.id=r.source_tag_id
            WHERE r.stock_id=?""",
            (int(stock_id),),
        ).fetchone()
    return dict(row) if row else None


def save_stock_rule(
    stock_id: int,
    payload: dict[str, Any],
    db_path: Path | str = DB_PATH,
    *,
    source_type: str = "individual",
    source_tag_id: int | None = None,
    is_overridden: bool = True,
) -> None:
    """Upsert one stock rule without changing any investment playbook."""
    rule = normalize_rule(payload)
    now = _now()
    with connect(db_path) as conn:
        if not conn.execute("SELECT 1 FROM stocks WHERE id=?", (int(stock_id),)).fetchone():
            raise ValueError("対象銘柄が見つかりません。")
        conn.execute(
            """INSERT INTO stock_trade_rules
            (stock_id,stop_loss_type,stop_loss_value,take_profit_type,
             take_profit_value,add_position_type,add_position_value,
             source_type,source_tag_id,is_overridden,memo,created_at,updated_at)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(stock_id) DO UPDATE SET
                stop_loss_type=excluded.stop_loss_type,
                stop_loss_value=excluded.stop_loss_value,
                take_profit_type=excluded.take_profit_type,
                take_profit_value=excluded.take_profit_value,
                add_position_type=excluded.add_position_type,
                add_position_value=excluded.add_position_value,
                source_type=excluded.source_type,
                source_tag_id=excluded.source_tag_id,
                is_overridden=excluded.is_overridden,
                memo=excluded.memo,
                updated_at=excluded.updated_at""",
            (
                int(stock_id),
                rule["stop_loss_type"],
                rule["stop_loss_value"],
                rule["take_profit_type"],
                rule["take_profit_value"],
                rule["add_position_type"],
                rule["add_position_value"],
                source_type,
                source_tag_id,
                int(is_overridden),
                rule["memo"],
                now,
                now,
            ),
        )


def delete_stock_rule(stock_id: int, db_path: Path | str = DB_PATH) -> None:
    """Delete only the strategy trade rule for one stock."""
    with connect(db_path) as conn:
        conn.execute("DELETE FROM stock_trade_rules WHERE stock_id=?", (int(stock_id),))


def normalize_rule(payload: dict[str, Any]) -> dict[str, Any]:
    """Validate reusable and individual price rule payloads."""
    result: dict[str, Any] = {}
    for role in RULE_ROLES:
        rule_type = str(payload.get(f"{role}_type") or "none")
        if rule_type not in RULE_TYPES:
            raise ValueError("ルール種類が不正です。")
        result[f"{role}_type"] = rule_type
        result[f"{role}_value"] = _rule_value(
            payload.get(f"{role}_value"), rule_type, _role_label(role)
        )
    result["earnings_policy"] = str(payload.get("earnings_policy") or "").strip()[:500]
    result["priority"] = _bounded_int(payload.get("priority"), -9999, 9999)
    result["memo"] = str(payload.get("memo") or "").strip()[:4000]
    return result


def resolve_strategy_rule(
    stock_id: int, db_path: Path | str = DB_PATH,
) -> dict[str, Any]:
    """Resolve individual override first, otherwise the highest-priority tag rule."""
    stock_rule = get_stock_rule(stock_id, db_path)
    if stock_rule and bool(stock_rule.get("is_overridden")):
        return {
            "status": "applied",
            "source_type": "individual",
            "source_label": "個別上書き",
            "source_tag_id": None,
            "conflict": False,
            "rule": stock_rule,
            "candidates": [],
        }
    candidates = _tag_rule_candidates(stock_id, db_path)
    if not candidates:
        if stock_rule:
            return {
                "status": "applied",
                "source_type": stock_rule.get("source_type") or "tag",
                "source_label": stock_rule.get("source_tag_name") or "適用済みタグ",
                "source_tag_id": stock_rule.get("source_tag_id"),
                "conflict": False,
                "rule": stock_rule,
                "candidates": [],
            }
        return _empty_resolution()
    highest = max(int(row.get("priority") or 0) for row in candidates)
    top = [row for row in candidates if int(row.get("priority") or 0) == highest]
    signatures = {_rule_signature(row) for row in top}
    if len(signatures) > 1:
        return {
            "status": "conflict",
            "source_type": "tag_candidate",
            "source_label": "同順位競合",
            "source_tag_id": None,
            "conflict": True,
            "rule": None,
            "candidates": top,
        }
    selected = top[0]
    if (
        stock_rule
        and stock_rule.get("source_type") == "tag"
        and int(stock_rule.get("source_tag_id") or 0) == int(selected["tag_id"])
        and _rule_signature(stock_rule) == _rule_signature(selected)
    ):
        return {
            "status": "applied",
            "source_type": "tag",
            "source_label": f"適用済みタグ: {selected['tag_name']}",
            "source_tag_id": selected["tag_id"],
            "conflict": False,
            "rule": stock_rule,
            "candidates": top,
        }
    return {
        "status": "candidate",
        "source_type": "tag_candidate",
        "source_label": f"タグ候補: {selected['tag_name']}",
        "source_tag_id": selected["tag_id"],
        "conflict": False,
        "rule": selected,
        "candidates": top,
    }


def calculate_rule_lines(
    rule: dict[str, Any] | None,
    average_price: Any,
    current_price: Any,
    *,
    near_percent: float = 3.0,
) -> dict[str, Any]:
    """Calculate three price lines and explain their current state."""
    average = _finite_positive(average_price)
    current = _finite_positive(current_price)
    if not rule:
        return _empty_lines(current)
    stop = calculate_line_price(
        "stop_loss", rule.get("stop_loss_type"), rule.get("stop_loss_value"),
        average, current,
    )
    take = calculate_line_price(
        "take_profit", rule.get("take_profit_type"), rule.get("take_profit_value"),
        average, current,
    )
    add = calculate_line_price(
        "add_position", rule.get("add_position_type"), rule.get("add_position_value"),
        average, current,
    )
    states: list[tuple[int, str, str]] = []
    flags = {
        "stop_loss_reached": False,
        "stop_loss_near": False,
        "take_profit_reached": False,
        "take_profit_near": False,
        "add_position_reached": False,
        "add_position_near": False,
    }
    if current is not None:
        if stop is not None:
            distance = (current - stop) / current * 100
            if current <= stop:
                flags["stop_loss_reached"] = True
                states.append((1, "損切到達", "negative"))
            elif distance <= near_percent:
                flags["stop_loss_near"] = True
                states.append((4, "損切接近", "warning"))
        if take is not None:
            distance = (take - current) / current * 100
            if current >= take:
                flags["take_profit_reached"] = True
                states.append((2, "利確到達", "positive"))
            elif distance <= near_percent:
                flags["take_profit_near"] = True
                states.append((5, "利確接近", "warning"))
        if add is not None:
            distance = (current - add) / current * 100
            if current <= add:
                flags["add_position_reached"] = True
                states.append((3, "買い増し到達", "info"))
            elif distance <= near_percent:
                flags["add_position_near"] = True
                states.append((6, "買い増し接近", "warning"))
    state = min(states, default=(99, "通常", "info"), key=lambda item: item[0])
    return {
        "configured": any(value is not None for value in (stop, take, add)),
        "current_price": current,
        "stop_loss_price": stop,
        "take_profit_price": take,
        "add_position_price": add,
        "status_label": state[1],
        "tone": state[2],
        **flags,
    }


def calculate_line_price(
    role: str,
    rule_type: Any,
    value: Any,
    average_price: Any,
    current_price: Any,
) -> float | None:
    """Calculate one absolute price from a typed rule."""
    if role not in RULE_ROLES or rule_type not in RULE_TYPES or rule_type == "none":
        return None
    number = _finite_positive(value)
    if number is None:
        return None
    if rule_type == "fixed_price":
        return number
    base = (
        _finite_positive(average_price)
        if rule_type == "percent_from_average_price"
        else _finite_positive(current_price)
    )
    if base is None:
        return None
    direction = 1 if role == "take_profit" else -1
    return max(0.0, base * (1 + direction * number / 100))


def enrich_rows_with_strategy(
    rows: list[dict[str, Any]],
    db_path: Path | str = DB_PATH,
    *,
    near_percent: float = 3.0,
) -> list[dict[str, Any]]:
    """Attach tags, effective rule, line prices, and conflict state."""
    assignments: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for tag in list_stock_tags(db_path=db_path):
        assignments[int(tag["stock_id"])].append(tag)
    result: list[dict[str, Any]] = []
    for row in rows:
        stock_id = int(row.get("id") or 0)
        resolution = resolve_strategy_rule(stock_id, db_path)
        lines = calculate_rule_lines(
            resolution.get("rule"),
            row.get("average_price"),
            row.get("current_price"),
            near_percent=near_percent,
        )
        result.append(
            {
                **row,
                "strategy_tags": assignments.get(stock_id, []),
                "strategy_rule_resolution": resolution,
                "strategy_rule": resolution.get("rule"),
                "strategy_lines": lines,
                "strategy_status": (
                    "競合" if resolution["conflict"]
                    else lines["status_label"] if lines["configured"]
                    else "未設定"
                ),
                "strategy_source": resolution["source_label"],
            }
        )
    return result


def attach_strategy_context(
    rows: list[dict[str, Any]], db_path: Path | str = DB_PATH,
) -> list[dict[str, Any]]:
    """Attach per-stock unread news and important disclosure counts."""
    with connect(db_path) as conn:
        news_rows = conn.execute(
            """SELECT x.stock_id,COUNT(DISTINCT a.id) AS count
            FROM news_article_stocks x
            JOIN news_articles a ON a.id=x.article_id
            WHERE x.confirmed=1 AND a.is_read=0
            GROUP BY x.stock_id"""
        ).fetchall()
        disclosure_rows = conn.execute(
            """SELECT stock_id,COUNT(*) AS count
            FROM disclosures
            WHERE importance='高'
            GROUP BY stock_id"""
        ).fetchall()
    news = {int(row["stock_id"]): int(row["count"]) for row in news_rows}
    disclosures = {
        int(row["stock_id"]): int(row["count"]) for row in disclosure_rows
    }
    return [
        {
            **row,
            "unread_news": news.get(int(row.get("id") or 0), 0),
            "important_disclosures": disclosures.get(int(row.get("id") or 0), 0),
        }
        for row in rows
    ]


def preview_bulk_apply(
    stock_ids: Iterable[int], db_path: Path | str = DB_PATH,
) -> list[dict[str, Any]]:
    """Preview applying current tag candidates without updating the DB."""
    stocks = _stocks_by_ids(stock_ids, db_path)
    result: list[dict[str, Any]] = []
    for stock_id, stock in stocks.items():
        current = get_stock_rule(stock_id, db_path)
        resolution = resolve_strategy_rule(stock_id, db_path)
        if current and bool(current.get("is_overridden")):
            action = "個別上書きを維持"
        elif resolution["conflict"]:
            action = "競合"
        elif not resolution.get("rule"):
            action = "ルールなし"
        elif current and _rule_signature(current) == _rule_signature(resolution["rule"]):
            action = "同一"
        else:
            action = "更新" if current else "新規"
        result.append(
            {
                "stock_id": stock_id,
                "ticker": stock["ticker"],
                "company_name": stock["company_name"],
                "action": action,
                "source": resolution["source_label"],
                "source_tag_id": resolution.get("source_tag_id"),
                "rule": resolution.get("rule"),
            }
        )
    return result


def apply_bulk_preview(
    preview_rows: list[dict[str, Any]],
    selected_stock_ids: Iterable[int],
    db_path: Path | str = DB_PATH,
) -> dict[str, int]:
    """Apply selected, non-conflicting preview rows in one transaction."""
    selected = {int(value) for value in selected_stock_ids}
    counts = {"applied": 0, "skipped": 0, "conflicts": 0}
    now = _now()
    with connect(db_path) as conn:
        for row in preview_rows:
            if int(row["stock_id"]) not in selected:
                counts["skipped"] += 1
                continue
            if row["action"] in {"競合", "ルールなし", "個別上書きを維持"}:
                counts["conflicts" if row["action"] == "競合" else "skipped"] += 1
                continue
            rule = row.get("rule")
            if not rule:
                counts["skipped"] += 1
                continue
            conn.execute(
                """INSERT INTO stock_trade_rules
                (stock_id,stop_loss_type,stop_loss_value,take_profit_type,
                 take_profit_value,add_position_type,add_position_value,
                 source_type,source_tag_id,is_overridden,memo,created_at,updated_at)
                VALUES(?,?,?,?,?,?,?,?,?,0,?,?,?)
                ON CONFLICT(stock_id) DO UPDATE SET
                    stop_loss_type=excluded.stop_loss_type,
                    stop_loss_value=excluded.stop_loss_value,
                    take_profit_type=excluded.take_profit_type,
                    take_profit_value=excluded.take_profit_value,
                    add_position_type=excluded.add_position_type,
                    add_position_value=excluded.add_position_value,
                    source_type=excluded.source_type,
                    source_tag_id=excluded.source_tag_id,
                    is_overridden=0,memo=excluded.memo,updated_at=excluded.updated_at
                WHERE stock_trade_rules.is_overridden=0""",
                (
                    int(row["stock_id"]),
                    rule["stop_loss_type"], rule["stop_loss_value"],
                    rule["take_profit_type"], rule["take_profit_value"],
                    rule["add_position_type"], rule["add_position_value"],
                    "tag", row.get("source_tag_id"),
                    str(rule.get("memo") or ""), now, now,
                ),
            )
            counts["applied"] += 1
    return counts


def strategy_dashboard_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Summarize line states and holding value by strategy tags."""
    holdings = [row for row in rows if row.get("is_holding")]
    tag_values: dict[str, float] = defaultdict(float)
    total_value = 0.0
    counts = defaultdict(int)
    for row in holdings:
        value = float(row.get("market_value") or 0)
        total_value += value
        for tag in row.get("strategy_tags") or []:
            tag_values[str(tag["name"])] += value
        lines = row.get("strategy_lines") or {}
        for key in (
            "stop_loss_reached", "stop_loss_near", "take_profit_reached",
            "take_profit_near", "add_position_reached", "add_position_near",
        ):
            counts[key] += int(bool(lines.get(key)))
        resolution = row.get("strategy_rule_resolution") or {}
        counts["conflicts"] += int(bool(resolution.get("conflict")))
        counts["unset"] += int(
            not bool(resolution.get("conflict"))
            and not bool(lines.get("configured"))
        )
    ratios = [
        {
            "tag": tag,
            "market_value": value,
            "portfolio_ratio": (value / total_value * 100) if total_value else 0.0,
        }
        for tag, value in tag_values.items()
    ]
    ratios.sort(key=lambda item: item["market_value"], reverse=True)
    return {**counts, "top_tag_ratios": ratios[:5], "portfolio_value": total_value}


def aggregate_by_tag(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Aggregate portfolio metrics for each tag; overlaps are intentional."""
    groups: dict[int, dict[str, Any]] = {}
    portfolio_value = sum(
        float(row.get("market_value") or 0) for row in rows if row.get("is_holding")
    )
    for row in rows:
        for tag in row.get("strategy_tags") or []:
            tag_id = int(tag["id"])
            group = groups.setdefault(
                tag_id,
                {
                    "tag_id": tag_id,
                    "tag_group": tag["tag_group"],
                    "tag": tag["name"],
                    "stock_count": 0,
                    "market_value": 0.0,
                    "profit_loss": 0.0,
                    "profit_rates": [],
                    "earnings_7d": 0,
                    "unread_news": 0,
                    "important_disclosures": 0,
                    "stop_near": 0,
                    "take_near": 0,
                },
            )
            group["stock_count"] += 1
            if row.get("is_holding"):
                group["market_value"] += float(row.get("market_value") or 0)
                group["profit_loss"] += float(row.get("profit") or 0)
                rate = row.get("profit_pct")
                if isinstance(rate, (int, float)) and math.isfinite(float(rate)):
                    group["profit_rates"].append(float(rate))
            days = row.get("earnings_days_until")
            group["earnings_7d"] += int(isinstance(days, int) and 0 <= days <= 7)
            group["unread_news"] += int(row.get("unread_news") or 0)
            group["important_disclosures"] += int(row.get("important_disclosures") or 0)
            lines = row.get("strategy_lines") or {}
            group["stop_near"] += int(
                bool(lines.get("stop_loss_near") or lines.get("stop_loss_reached"))
            )
            group["take_near"] += int(
                bool(lines.get("take_profit_near") or lines.get("take_profit_reached"))
            )
    output = []
    for group in groups.values():
        rates = group.pop("profit_rates")
        group["average_profit_rate"] = sum(rates) / len(rates) if rates else None
        group["portfolio_ratio"] = (
            group["market_value"] / portfolio_value * 100 if portfolio_value else 0.0
        )
        output.append(group)
    return sorted(output, key=lambda item: (-item["market_value"], item["tag_group"], item["tag"]))


def parse_tag_csv(content: bytes) -> list[dict[str, Any]]:
    """Parse ticker,tags CSV using UTF-8 BOM, UTF-8, or CP932."""
    rows = _dict_rows(content)
    result = []
    for line, row in enumerate(rows, start=2):
        try:
            ticker = normalize_ticker(str(row.get("ticker") or ""))
            tags = [item.strip() for item in str(row.get("tags") or "").split("|") if item.strip()]
            if not tags:
                raise ValueError("tagsが空です。")
            result.append({"line": line, "ticker": ticker, "tags": tags, "error": ""})
        except Exception as exc:
            result.append({"line": line, "ticker": str(row.get("ticker") or ""), "tags": [], "error": str(exc)})
    return result


def export_tag_csv(
    db_path: Path | str = DB_PATH,
) -> bytes:
    """Export current stock-tag assignments as a UTF-8 BOM CSV."""
    with connect(db_path) as conn:
        rows = conn.execute(
            """SELECT s.ticker,t.name
            FROM stocks s
            JOIN stock_strategy_tags st ON st.stock_id=s.id
            JOIN strategy_tags t ON t.id=st.tag_id
            ORDER BY s.ticker,t.tag_group,t.display_order,t.name"""
        ).fetchall()
    grouped: dict[str, list[str]] = defaultdict(list)
    for row in rows:
        grouped[str(row["ticker"])].append(str(row["name"]))
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=["ticker", "tags"])
    writer.writeheader()
    for ticker, names in grouped.items():
        writer.writerow({"ticker": ticker, "tags": "|".join(names)})
    return ("\ufeff" + output.getvalue()).encode("utf-8")


def import_tag_csv(
    parsed_rows: list[dict[str, Any]],
    db_path: Path | str = DB_PATH,
    *,
    update_existing: bool = True,
) -> dict[str, int]:
    """Assign known active tags by name while continuing past invalid rows."""
    counts = {"updated": 0, "skipped": 0, "failed": 0}
    with connect(db_path) as conn:
        tags = conn.execute(
            "SELECT id,name FROM strategy_tags WHERE is_active=1"
        ).fetchall()
        by_name: dict[str, list[int]] = defaultdict(list)
        for tag in tags:
            by_name[str(tag["name"])].append(int(tag["id"]))
        for row in parsed_rows:
            if row.get("error"):
                counts["failed"] += 1
                continue
            stock = conn.execute("SELECT id FROM stocks WHERE ticker=?", (row["ticker"],)).fetchone()
            missing = [name for name in row["tags"] if name not in by_name]
            ambiguous = [name for name in row["tags"] if len(by_name.get(name, [])) > 1]
            if not stock or missing or ambiguous:
                counts["failed"] += 1
                continue
            stock_id = int(stock["id"])
            ids = [by_name[name][0] for name in row["tags"]]
            if update_existing:
                conn.execute("DELETE FROM stock_strategy_tags WHERE stock_id=?", (stock_id,))
            now = _now()
            before = conn.total_changes
            conn.executemany(
                "INSERT OR IGNORE INTO stock_strategy_tags(stock_id,tag_id,created_at) VALUES(?,?,?)",
                [(stock_id, tag_id, now) for tag_id in ids],
            )
            changed = conn.total_changes - before
            counts["updated" if changed else "skipped"] += 1
    return counts


def parse_rule_csv(content: bytes) -> list[dict[str, Any]]:
    """Parse reusable tag rule CSV with row-level errors."""
    rows = _dict_rows(content)
    result = []
    for line, row in enumerate(rows, start=2):
        try:
            group = str(row.get("tag_group") or "").strip()
            name = str(row.get("tag_name") or "").strip()
            if not name or group not in TAG_GROUPS:
                raise ValueError("タグ名またはグループが不正です。")
            rule = normalize_rule(row)
            result.append({"line": line, "tag_name": name, "tag_group": group, **rule, "error": ""})
        except Exception as exc:
            result.append({"line": line, "tag_name": str(row.get("tag_name") or ""), "tag_group": str(row.get("tag_group") or ""), "error": str(exc)})
    return result


def export_rule_csv(
    db_path: Path | str = DB_PATH,
) -> bytes:
    """Export reusable tag rules as a UTF-8 BOM CSV."""
    fieldnames = [
        "tag_name", "tag_group", "stop_loss_type", "stop_loss_value",
        "take_profit_type", "take_profit_value", "add_position_type",
        "add_position_value", "priority", "memo",
    ]
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()
    for row in list_rule_sets(db_path):
        writer.writerow({key: row.get(key) for key in fieldnames})
    return ("\ufeff" + output.getvalue()).encode("utf-8")


def import_rule_csv(
    parsed_rows: list[dict[str, Any]],
    db_path: Path | str = DB_PATH,
    *,
    update_existing: bool = True,
) -> dict[str, int]:
    """Import reusable rules for existing tags."""
    counts = {"inserted": 0, "updated": 0, "skipped": 0, "failed": 0}
    for row in parsed_rows:
        if row.get("error"):
            counts["failed"] += 1
            continue
        with connect(db_path) as conn:
            tag = conn.execute(
                "SELECT id FROM strategy_tags WHERE name=? AND tag_group=?",
                (row["tag_name"], row["tag_group"]),
            ).fetchone()
            if not tag:
                counts["failed"] += 1
                continue
            existing = conn.execute(
                "SELECT 1 FROM strategy_rule_sets WHERE tag_id=?", (int(tag["id"]),)
            ).fetchone()
        if existing and not update_existing:
            counts["skipped"] += 1
            continue
        save_rule_set(int(tag["id"]), row, db_path)
        counts["updated" if existing else "inserted"] += 1
    return counts


def _tag_rule_candidates(
    stock_id: int, db_path: Path | str,
) -> list[dict[str, Any]]:
    with connect(db_path) as conn:
        rows = conn.execute(
            """SELECT r.*,t.name AS tag_name,t.tag_group,t.id AS tag_id
            FROM stock_strategy_tags st
            JOIN strategy_tags t ON t.id=st.tag_id AND t.is_active=1
            JOIN strategy_rule_sets r ON r.tag_id=t.id
            WHERE st.stock_id=?
            ORDER BY r.priority DESC,t.display_order,t.name""",
            (int(stock_id),),
        ).fetchall()
    return [dict(row) for row in rows]


def _stocks_by_ids(
    stock_ids: Iterable[int], db_path: Path | str,
) -> dict[int, dict[str, Any]]:
    ids = sorted({int(value) for value in stock_ids})
    if not ids:
        return {}
    placeholders = ",".join("?" for _ in ids)
    with connect(db_path) as conn:
        rows = conn.execute(
            f"SELECT * FROM stocks WHERE id IN ({placeholders})", tuple(ids)
        ).fetchall()
    return {int(row["id"]): dict(row) for row in rows}


def _rule_signature(rule: dict[str, Any]) -> tuple[Any, ...]:
    values = tuple(rule.get(key) for key in (
        "stop_loss_type", "stop_loss_value", "take_profit_type",
        "take_profit_value", "add_position_type", "add_position_value",
    ))
    return (*values, str(rule.get("earnings_policy") or ""))


def _empty_resolution() -> dict[str, Any]:
    return {
        "status": "unset",
        "source_type": "none",
        "source_label": "未設定",
        "source_tag_id": None,
        "conflict": False,
        "rule": None,
        "candidates": [],
    }


def _empty_lines(current_price: Any) -> dict[str, Any]:
    return {
        "configured": False,
        "current_price": _finite_positive(current_price),
        "stop_loss_price": None,
        "take_profit_price": None,
        "add_position_price": None,
        "status_label": "未設定",
        "tone": "muted",
        "stop_loss_reached": False,
        "stop_loss_near": False,
        "take_profit_reached": False,
        "take_profit_near": False,
        "add_position_reached": False,
        "add_position_near": False,
    }


def _rule_value(value: Any, rule_type: str, label: str) -> float | None:
    if rule_type == "none":
        return None
    number = _finite_positive(value)
    if number is None:
        raise ValueError(f"{label}の値を0より大きい数値で入力してください。")
    if rule_type != "fixed_price" and number > 100:
        raise ValueError(f"{label}の割合は100以下で入力してください。")
    return number


def _finite_positive(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) and number > 0 else None


def _bounded_int(value: Any, minimum: int, maximum: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        number = 0
    return max(minimum, min(number, maximum))


def _role_label(role: str) -> str:
    return {
        "stop_loss": "損切",
        "take_profit": "利確",
        "add_position": "買い増し",
    }[role]


def _dict_rows(content: bytes) -> list[dict[str, str]]:
    for encoding in ("utf-8-sig", "utf-8", "cp932"):
        try:
            text = content.decode(encoding)
            return list(csv.DictReader(io.StringIO(text)))
        except UnicodeDecodeError:
            continue
    raise ValueError("CSVの文字コードを判定できませんでした。")
