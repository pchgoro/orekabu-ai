"""Rule-based attention scoring for stocks."""

from __future__ import annotations

import math
from typing import Any

import pandas as pd

from services.settings import default_settings


def _valid(value: Any) -> bool:
    try:
        return value is not None and not math.isnan(float(value)) and not math.isinf(float(value))
    except (TypeError, ValueError):
        return False


def judge_score(score: float) -> str:
    """Return a Japanese label for the score threshold."""
    if score >= 80:
        return "最優先で確認"
    if score >= 65:
        return "注目"
    if score >= 50:
        return "通常監視"
    return "優先度低め"


def calculate_attention_score(row: dict[str, Any] | pd.Series, prev_row: dict[str, Any] | pd.Series | None = None, settings: dict[str, Any] | None = None) -> dict[str, Any]:
    """Calculate the explainable attention score and reasons."""
    score_settings = (settings or default_settings()).get("score", default_settings()["score"])
    data = dict(row)
    prev = dict(prev_row) if prev_row is not None else {}
    score = float(score_settings["base_score"])
    reasons: list[str] = [f"初期点：+{score_settings['base_score']:.0f}点"]

    def add(condition: bool, points_key: str, text: str) -> None:
        nonlocal score
        if condition:
            points = float(score_settings[points_key])
            score += points
            reasons.append(f"{text}：{points:+.0f}点")

    rsi_value = data.get("RSI14")
    if _valid(rsi_value):
        rsi_float = float(rsi_value)
        add(rsi_float <= score_settings["rsi_low"], "rsi_30_or_less", f"RSI {rsi_float:.1f}")
        add(score_settings["rsi_low"] < rsi_float <= score_settings["rsi_mid_low"], "rsi_30_40", f"RSI {rsi_float:.1f}")
        add(score_settings["rsi_mid_low"] < rsi_float <= score_settings["rsi_mid"], "rsi_40_50", f"RSI {rsi_float:.1f}")
        add(rsi_float >= score_settings["rsi_high"], "rsi_70_or_more", f"RSI {rsi_float:.1f}")

    dev25 = data.get("DEV_MA25")
    if _valid(dev25):
        threshold = abs(float(score_settings["ma_deviation_threshold"]))
        add(abs(float(dev25)) <= threshold, "ma25_deviation_near", f"25日線との乖離率 {float(dev25):.2f}%")

    dev75 = data.get("DEV_MA75")
    if _valid(dev75):
        threshold = abs(float(score_settings["ma_deviation_threshold"]))
        add(abs(float(dev75)) <= threshold, "ma75_deviation_near", f"75日線との乖離率 {float(dev75):.2f}%")

    volume_ratio = data.get("VOLUME_RATIO")
    if _valid(volume_ratio):
        vr = float(volume_ratio)
        add(vr >= score_settings["volume_ratio_threshold"], "volume_ratio_15", f"出来高倍率 {vr:.2f}倍")
        add(vr >= score_settings["volume_ratio_extra_threshold"], "volume_ratio_20_extra", f"出来高倍率 {vr:.2f}倍 追加")

    drop = data.get("DROP_FROM_HIGH_60")
    if _valid(drop):
        drop_abs = abs(min(float(drop), 0.0))
        add(score_settings["drop_threshold_low"] <= drop_abs < score_settings["drop_threshold_high"], "drop_10_20", f"直近高値からの下落率 -{drop_abs:.2f}%")
        add(drop_abs >= score_settings["drop_threshold_high"], "drop_20_or_more", f"直近高値からの下落率 -{drop_abs:.2f}%")

    close, ma5, ma25, ma75 = data.get("Close"), data.get("MA5"), data.get("MA25"), data.get("MA75")
    if all(_valid(v) for v in [ma5, ma25]):
        add(float(ma5) > float(ma25), "ma5_above_ma25", "5日移動平均が25日移動平均を上回っている")
        prev_ma5, prev_ma25 = prev.get("MA5"), prev.get("MA25")
        add(
            all(_valid(v) for v in [prev_ma5, prev_ma25]) and float(prev_ma5) <= float(prev_ma25) and float(ma5) > float(ma25),
            "golden_cross_extra",
            "5日線と25日線のゴールデンクロス",
        )

    if all(_valid(v) for v in [close, ma25, ma75]):
        add(float(close) < float(ma25) and float(close) < float(ma75), "price_below_ma25_ma75", "株価が25日線と75日線の両方より下")
        add(float(close) > float(ma25) and float(close) > float(ma75), "price_above_ma25_ma75", "株価が25日線と75日線の両方より上")

    score = max(0, min(100, round(score, 1)))
    return {"score": score, "judge": judge_score(score), "reasons": reasons}
