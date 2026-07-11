"""Tests for rule-based scoring."""

from __future__ import annotations

from services.scoring import calculate_attention_score, judge_score
from services.settings import default_settings


def base_row() -> dict[str, float]:
    return {
        "Close": 100,
        "RSI14": 38.2,
        "DEV_MA25": -1.4,
        "DEV_MA75": 2.0,
        "VOLUME_RATIO": 1.7,
        "DROP_FROM_HIGH_60": -12.0,
        "MA5": 101,
        "MA25": 100,
        "MA75": 99,
    }


def test_rules_and_reasons() -> None:
    result = calculate_attention_score(base_row(), {"MA5": 99, "MA25": 100}, default_settings())
    assert result["score"] == 100
    assert any("RSI 38.2" in reason for reason in result["reasons"])
    assert any("ゴールデンクロス" in reason for reason in result["reasons"])


def test_score_floor() -> None:
    settings = default_settings()
    settings["score"]["base_score"] = -50
    result = calculate_attention_score({"Close": 50, "MA25": 100, "MA75": 100, "RSI14": 80}, None, settings)
    assert result["score"] == 0


def test_score_ceiling() -> None:
    settings = default_settings()
    settings["score"]["base_score"] = 100
    result = calculate_attention_score(base_row(), {"MA5": 99, "MA25": 100}, settings)
    assert result["score"] == 100


def test_settings_reflected() -> None:
    settings = default_settings()
    settings["score"]["rsi_30_40"] = 1
    result = calculate_attention_score(base_row(), None, settings)
    assert any("RSI 38.2：+1点" in reason for reason in result["reasons"])


def test_judge_score() -> None:
    assert judge_score(80) == "最優先で確認"
    assert judge_score(65) == "注目"
    assert judge_score(50) == "通常監視"
    assert judge_score(49) == "優先度低め"
