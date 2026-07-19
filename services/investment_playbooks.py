"""User-authored investment rules and explainable price-state evaluation."""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

from services.database import _now, connect
from utils.constants import DB_PATH

THEME_OPTIONS = (
    "AI",
    "半導体",
    "データセンター",
    "電力",
    "防衛",
    "宇宙",
    "高配当",
    "国策",
    "生成AI",
    "ロボット",
    "フィジカルAI",
    "医療",
    "自動車",
    "インフラ",
    "その他",
)

EXIT_CONDITION_OPTIONS = (
    "テーマ崩壊",
    "下方修正",
    "業績悪化",
    "配当減額",
    "買った理由消滅",
    "財務悪化",
    "チャート悪化",
    "自分で判断",
)

HOLDING_PERIOD_OPTIONS = ("短期", "中期", "長期", "自由入力")
RULE_NEAR_PERCENT = 5.0


def get_playbook(
    stock_id: int, db_path: Path | str = DB_PATH,
) -> dict[str, Any] | None:
    """Return one decoded playbook or None when no rule is configured."""
    with connect(db_path) as conn:
        row = conn.execute(
            "SELECT * FROM investment_playbooks WHERE stock_id=?",
            (int(stock_id),),
        ).fetchone()
    return _decode_row(dict(row)) if row else None


def list_playbooks(
    db_path: Path | str = DB_PATH, *, holdings_only: bool = False,
) -> list[dict[str, Any]]:
    """Return decoded playbooks joined to their registered stocks."""
    where = "WHERE s.is_holding=1" if holdings_only else ""
    with connect(db_path) as conn:
        rows = conn.execute(
            f"""SELECT p.*,s.ticker,s.company_name,s.is_holding
            FROM investment_playbooks p
            JOIN stocks s ON s.id=p.stock_id
            {where}
            ORDER BY s.ticker"""
        ).fetchall()
    return [_decode_row(dict(row)) for row in rows]


def save_playbook(
    stock_id: int, payload: dict[str, Any], db_path: Path | str = DB_PATH,
) -> None:
    """Validate and upsert one playbook without changing stock data."""
    normalized = normalize_playbook(payload)
    now = _now()
    with connect(db_path) as conn:
        if not conn.execute(
            "SELECT 1 FROM stocks WHERE id=?", (int(stock_id),)
        ).fetchone():
            raise ValueError("対象銘柄が見つかりません。")
        conn.execute(
            """INSERT INTO investment_playbooks
            (stock_id,buy_reason,investment_theme,target_price_1,
             target_price_1_sell_percent,target_price_2,
             target_price_2_sell_percent,final_target_price,stop_loss_price,
             trailing_stop_percent,holding_period,exit_conditions,risk_notes,
             created_at,updated_at)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(stock_id) DO UPDATE SET
                buy_reason=excluded.buy_reason,
                investment_theme=excluded.investment_theme,
                target_price_1=excluded.target_price_1,
                target_price_1_sell_percent=excluded.target_price_1_sell_percent,
                target_price_2=excluded.target_price_2,
                target_price_2_sell_percent=excluded.target_price_2_sell_percent,
                final_target_price=excluded.final_target_price,
                stop_loss_price=excluded.stop_loss_price,
                trailing_stop_percent=excluded.trailing_stop_percent,
                holding_period=excluded.holding_period,
                exit_conditions=excluded.exit_conditions,
                risk_notes=excluded.risk_notes,
                updated_at=excluded.updated_at""",
            (
                int(stock_id),
                normalized["buy_reason"],
                json.dumps(normalized["investment_themes"], ensure_ascii=False),
                normalized["target_price_1"],
                normalized["target_price_1_sell_percent"],
                normalized["target_price_2"],
                normalized["target_price_2_sell_percent"],
                normalized["final_target_price"],
                normalized["stop_loss_price"],
                normalized["trailing_stop_percent"],
                normalized["holding_period"],
                json.dumps(normalized["exit_conditions"], ensure_ascii=False),
                normalized["risk_notes"],
                now,
                now,
            ),
        )


def delete_playbook(stock_id: int, db_path: Path | str = DB_PATH) -> None:
    """Delete one playbook without touching the registered stock."""
    with connect(db_path) as conn:
        cursor = conn.execute(
            "DELETE FROM investment_playbooks WHERE stock_id=?",
            (int(stock_id),),
        )
        if cursor.rowcount == 0:
            raise ValueError("削除する投資ルールがありません。")


def normalize_playbook(payload: dict[str, Any]) -> dict[str, Any]:
    """Normalize form values and reject invalid prices or percentages."""
    themes = _unique_strings(payload.get("investment_themes"), limit=30)
    selected = [
        value
        for value in _unique_strings(
            (payload.get("exit_conditions") or {}).get("selected"), limit=20
        )
        if value in EXIT_CONDITION_OPTIONS
    ]
    custom = str(
        (payload.get("exit_conditions") or {}).get("custom") or ""
    ).strip()[:4000]
    normalized = {
        "buy_reason": str(payload.get("buy_reason") or "").strip()[:10000],
        "investment_themes": themes,
        "target_price_1": _optional_positive(
            payload.get("target_price_1"), "利確①価格"
        ),
        "target_price_1_sell_percent": _optional_percent(
            payload.get("target_price_1_sell_percent"), "利確①売却割合"
        ),
        "target_price_2": _optional_positive(
            payload.get("target_price_2"), "利確②価格"
        ),
        "target_price_2_sell_percent": _optional_percent(
            payload.get("target_price_2_sell_percent"), "利確②売却割合"
        ),
        "final_target_price": _optional_positive(
            payload.get("final_target_price"), "最終目標価格"
        ),
        "stop_loss_price": _optional_positive(
            payload.get("stop_loss_price"), "損切り価格"
        ),
        "trailing_stop_percent": _optional_percent(
            payload.get("trailing_stop_percent"), "トレーリングストップ"
        ),
        "holding_period": str(payload.get("holding_period") or "").strip()[:200],
        "exit_conditions": {"selected": selected, "custom": custom},
        "risk_notes": str(payload.get("risk_notes") or "").strip()[:10000],
    }
    _validate_target_order(normalized)
    return normalized


def evaluate_playbook(
    playbook: dict[str, Any] | None,
    current_price: Any,
    near_percent: float = RULE_NEAR_PERCENT,
) -> dict[str, Any]:
    """Evaluate only the state of configured rules, never a trade recommendation."""
    if not playbook:
        evaluation = _empty_evaluation("unset", "未設定", "muted")
        evaluation["current_price"] = _finite_positive(current_price)
        return evaluation
    price = _finite_positive(current_price)
    if price is None:
        return _empty_evaluation("no_price", "価格未取得", "muted", configured=True)

    targets = _targets(playbook)
    stop = _finite_positive(playbook.get("stop_loss_price"))
    next_target = next(
        ((label, value) for label, value in targets if price < value),
        None,
    )
    reached = [item for item in targets if price >= item[1]]
    target_distance = (next_target[1] - price) if next_target else None
    target_distance_pct = (
        target_distance / price * 100 if target_distance is not None else None
    )
    stop_distance = price - stop if stop is not None else None
    stop_distance_pct = (
        stop_distance / price * 100 if stop_distance is not None else None
    )
    stop_reached = stop is not None and price <= stop
    stop_near = (
        stop is not None
        and price > stop
        and stop_distance_pct is not None
        and stop_distance_pct <= near_percent
    )
    target_near = (
        next_target is not None
        and target_distance_pct is not None
        and target_distance_pct <= near_percent
    )

    if stop_reached:
        code, label, tone = "stop_loss_reached", "損切りライン到達", "negative"
    elif reached:
        reached_label = reached[-1][0]
        code, label, tone = (
            f"{reached_label}_reached",
            f"{_target_display_name(reached_label)}到達",
            "positive",
        )
    elif stop_near:
        code, label, tone = "stop_loss_near", "損切りまで5%以内", "warning"
    elif target_near and next_target:
        code, label, tone = (
            f"{next_target[0]}_near",
            f"{_target_display_name(next_target[0])}まで5%以内",
            "warning",
        )
    else:
        code, label, tone = "holding", "ルール内", "info"

    return {
        "configured": True,
        "status_code": code,
        "status_label": label,
        "tone": tone,
        "current_price": price,
        "next_target_label": next_target[0] if next_target else None,
        "next_target_price": next_target[1] if next_target else None,
        "target_distance": target_distance,
        "target_distance_pct": target_distance_pct,
        "stop_loss_price": stop,
        "stop_distance": stop_distance,
        "stop_distance_pct": stop_distance_pct,
        "take_profit_reached": bool(reached),
        "take_profit_near": target_near,
        "stop_loss_reached": stop_reached,
        "stop_loss_near": stop_near,
    }


def enrich_rows_with_playbooks(
    rows: list[dict[str, Any]], db_path: Path | str = DB_PATH,
) -> list[dict[str, Any]]:
    """Attach compact playbook state to stock analysis rows."""
    playbooks = {
        int(row["stock_id"]): row for row in list_playbooks(db_path)
    }
    enriched: list[dict[str, Any]] = []
    for row in rows:
        playbook = playbooks.get(int(row.get("id") or 0))
        evaluation = evaluate_playbook(playbook, row.get("current_price"))
        enriched.append(
            {
                **row,
                "investment_playbook": playbook,
                "playbook_evaluation": evaluation,
                "playbook_status": evaluation["status_label"],
                "playbook_tone": evaluation["tone"],
                "playbook_target_distance": evaluation["target_distance"],
                "playbook_target_distance_pct": evaluation["target_distance_pct"],
                "playbook_stop_distance": evaluation["stop_distance"],
                "playbook_stop_distance_pct": evaluation["stop_distance_pct"],
            }
        )
    return enriched


def format_playbook_for_prompt(playbook: dict[str, Any] | None) -> str:
    """Format one playbook for a copy-only analysis prompt."""
    if not playbook:
        return "投資ルール：未設定"
    exits = playbook.get("exit_conditions") or {}
    selected = "、".join(exits.get("selected") or []) or "なし"
    custom = exits.get("custom") or "なし"
    themes = "、".join(playbook.get("investment_themes") or []) or "未設定"
    return f"""買った理由：{playbook.get('buy_reason') or '未設定'}
投資テーマ：{themes}
利確①：{_price_text(playbook.get('target_price_1'))} / 売却割合 {_percent_text(playbook.get('target_price_1_sell_percent'))}
利確②：{_price_text(playbook.get('target_price_2'))} / 売却割合 {_percent_text(playbook.get('target_price_2_sell_percent'))}
最終目標：{_price_text(playbook.get('final_target_price'))}
損切り価格：{_price_text(playbook.get('stop_loss_price'))}
トレーリングストップ：{_percent_text(playbook.get('trailing_stop_percent'))}
保有予定：{playbook.get('holding_period') or '未設定'}
売却条件：{selected}
売却条件の自由記述：{custom}
保有メモ・リスク：{playbook.get('risk_notes') or 'なし'}"""


def _decode_row(row: dict[str, Any]) -> dict[str, Any]:
    result = dict(row)
    result["investment_themes"] = _json_list(
        result.pop("investment_theme", "[]")
    )
    result["exit_conditions"] = _json_exit_conditions(
        result.get("exit_conditions")
    )
    return result


def _json_list(value: Any) -> list[str]:
    try:
        loaded = json.loads(str(value or "[]"))
    except (json.JSONDecodeError, TypeError):
        loaded = []
    return _unique_strings(loaded, limit=30)


def _json_exit_conditions(value: Any) -> dict[str, Any]:
    try:
        loaded = json.loads(str(value or "{}"))
    except (json.JSONDecodeError, TypeError):
        loaded = {}
    if not isinstance(loaded, dict):
        loaded = {}
    return {
        "selected": _unique_strings(loaded.get("selected"), limit=20),
        "custom": str(loaded.get("custom") or ""),
    }


def _unique_strings(value: Any, limit: int) -> list[str]:
    values = value if isinstance(value, (list, tuple, set)) else []
    result: list[str] = []
    for item in values:
        text = str(item or "").strip()[:100]
        if text and text not in result:
            result.append(text)
    return result[:limit]


def _optional_positive(value: Any, label: str) -> float | None:
    if value in (None, ""):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label}は数値で入力してください。") from exc
    if not math.isfinite(number) or number < 0:
        raise ValueError(f"{label}は0以上で入力してください。")
    return number or None


def _optional_percent(value: Any, label: str) -> float | None:
    number = _optional_positive(value, label)
    if number is not None and number > 100:
        raise ValueError(f"{label}は100以下で入力してください。")
    return number


def _validate_target_order(values: dict[str, Any]) -> None:
    targets = [
        value
        for value in (
            values["target_price_1"],
            values["target_price_2"],
            values["final_target_price"],
        )
        if value is not None
    ]
    if any(left > right for left, right in zip(targets, targets[1:])):
        raise ValueError("利確価格は利確①、利確②、最終目標の順に設定してください。")


def _finite_positive(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) and number > 0 else None


def _targets(playbook: dict[str, Any]) -> list[tuple[str, float]]:
    result: list[tuple[str, float]] = []
    for key in ("target_price_1", "target_price_2", "final_target_price"):
        value = _finite_positive(playbook.get(key))
        if value is not None:
            result.append((key, value))
    return sorted(result, key=lambda item: item[1])


def _target_display_name(key: str) -> str:
    return {
        "target_price_1": "利確①",
        "target_price_2": "利確②",
        "final_target_price": "最終目標",
    }.get(key, "利確ライン")


def _empty_evaluation(
    code: str, label: str, tone: str, *, configured: bool = False,
) -> dict[str, Any]:
    return {
        "configured": configured,
        "status_code": code,
        "status_label": label,
        "tone": tone,
        "current_price": None,
        "next_target_label": None,
        "next_target_price": None,
        "target_distance": None,
        "target_distance_pct": None,
        "stop_loss_price": None,
        "stop_distance": None,
        "stop_distance_pct": None,
        "take_profit_reached": False,
        "take_profit_near": False,
        "stop_loss_reached": False,
        "stop_loss_near": False,
    }


def _price_text(value: Any) -> str:
    number = _finite_positive(value)
    return f"{number:,.0f}円" if number is not None else "未設定"


def _percent_text(value: Any) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "未設定"
    return f"{number:g}%" if math.isfinite(number) else "未設定"
