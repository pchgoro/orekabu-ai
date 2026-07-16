"""Settings loading, validation, and merging."""

from __future__ import annotations

import copy
import math
from typing import Any

from utils.constants import DEFAULT_SETTINGS


def default_settings() -> dict[str, Any]:
    """Return a deep copy of default settings."""
    return copy.deepcopy(DEFAULT_SETTINGS)


def merge_settings(saved: dict[str, Any] | None) -> dict[str, Any]:
    """Merge saved settings onto defaults so new keys are always present."""
    merged = default_settings()
    if not isinstance(saved, dict) or not saved:
        return merged
    for key, value in saved.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key].update(value)
        else:
            merged[key] = value
    return validate_settings(merged)


def validate_settings(settings: dict[str, Any]) -> dict[str, Any]:
    """Clamp settings to values that keep the app operational."""
    settings["dashboard_display_mode"] = settings.get("dashboard_display_mode") if settings.get("dashboard_display_mode") in {"標準", "コンパクト"} else "標準"
    settings["news_display_mode"] = settings.get("news_display_mode") if settings.get("news_display_mode") in {"カード", "表"} else "カード"
    settings["mobile_priority_display"] = _as_bool(settings.get("mobile_priority_display"), False)
    settings["briefing_limit"] = _clamp_int(settings.get("briefing_limit"), 10, 1, 20)
    settings["daily_tasks_limit"] = _clamp_int(settings.get("daily_tasks_limit"), 10, 1, 10)
    settings["hide_zero_sections"] = _as_bool(settings.get("hide_zero_sections"), True)
    settings["ranking_limit"] = _clamp_int(settings.get("ranking_limit"), 10, 1, 100)
    settings["stock_cache_minutes"] = _clamp_int(settings.get("stock_cache_minutes"), 15, 1, 1440)
    settings["buy_watch_near_percent"] = _clamp_float(settings.get("buy_watch_near_percent"), 3.0, 0.0, 100.0)
    settings["earnings_dashboard_limit"] = _clamp_int(settings.get("earnings_dashboard_limit"), 5, 1, 100)
    settings["earnings_near_days"] = _clamp_int(settings.get("earnings_near_days"), 7, 1, 365)
    settings["related_earnings_limit"] = _clamp_int(settings.get("related_earnings_limit"), 5, 1, 100)
    settings["past_earnings_days"] = _clamp_int(settings.get("past_earnings_days"), 30, 0, 3650)
    settings["show_unconfirmed_earnings"] = _as_bool(settings.get("show_unconfirmed_earnings"), True)
    auto = settings.get("earnings_auto_fetch", {})
    defaults = DEFAULT_SETTINGS["earnings_auto_fetch"]
    if not isinstance(auto, dict):
        auto = {}
    auto["enabled"] = _as_bool(auto.get("enabled"), defaults["enabled"])
    auto["provider"] = "yfinance" if auto.get("provider") != "csv" else "csv"
    auto["max_tickers_per_run"] = _clamp_int(auto.get("max_tickers_per_run"), defaults["max_tickers_per_run"], 1, 100)
    auto["request_interval_seconds"] = _clamp_float(auto.get("request_interval_seconds"), defaults["request_interval_seconds"], 1.0, 60.0)
    auto["cache_hours"] = _clamp_int(auto.get("cache_hours"), defaults["cache_hours"], 1, 168)
    auto["candidate_retention_days"] = _clamp_int(auto.get("candidate_retention_days"), defaults["candidate_retention_days"], 1, 3650)
    auto["show_past_candidates"] = _as_bool(auto.get("show_past_candidates"), defaults["show_past_candidates"])
    auto["save_same_candidates"] = _as_bool(auto.get("save_same_candidates"), defaults["save_same_candidates"])
    auto["date_change_min_days"] = _clamp_int(auto.get("date_change_min_days"), defaults["date_change_min_days"], 1, 365)
    auto["include_confirmed_events"] = _as_bool(auto.get("include_confirmed_events"), defaults["include_confirmed_events"])
    settings["earnings_auto_fetch"] = auto
    score = settings.get("score", {})
    if not isinstance(score, dict):
        score = {}
    for key, default in DEFAULT_SETTINGS["score"].items():
        try:
            value = float(score.get(key, default))
            score[key] = value if math.isfinite(value) else float(default)
        except (TypeError, ValueError, OverflowError):
            score[key] = float(default)
    settings["score"] = score
    return settings


def _clamp_int(value: Any, default: int, minimum: int, maximum: int) -> int:
    """Convert a setting to a bounded integer or use its known-safe default."""
    try:
        converted = int(value)
    except (TypeError, ValueError, OverflowError):
        converted = default
    return max(minimum, min(converted, maximum))


def _clamp_float(value: Any, default: float, minimum: float, maximum: float) -> float:
    """Convert a setting to a finite bounded float or use its default."""
    try:
        converted = float(value)
        if not math.isfinite(converted):
            raise ValueError
    except (TypeError, ValueError, OverflowError):
        converted = default
    return max(minimum, min(converted, maximum))


def _as_bool(value: Any, default: bool) -> bool:
    """Parse persisted booleans without treating the string 'false' as true."""
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and value in {0, 1}:
        return bool(value)
    if isinstance(value, str):
        normalized = value.strip().casefold()
        if normalized in {"true", "1", "yes", "on"}:
            return True
        if normalized in {"false", "0", "no", "off"}:
            return False
    return default
