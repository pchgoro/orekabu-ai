"""Settings loading, validation, and merging."""

from __future__ import annotations

import copy
from typing import Any

from utils.constants import DEFAULT_SETTINGS


def default_settings() -> dict[str, Any]:
    """Return a deep copy of default settings."""
    return copy.deepcopy(DEFAULT_SETTINGS)


def merge_settings(saved: dict[str, Any] | None) -> dict[str, Any]:
    """Merge saved settings onto defaults so new keys are always present."""
    merged = default_settings()
    if not saved:
        return merged
    for key, value in saved.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key].update(value)
        else:
            merged[key] = value
    return validate_settings(merged)


def validate_settings(settings: dict[str, Any]) -> dict[str, Any]:
    """Clamp settings to values that keep the app operational."""
    settings["ranking_limit"] = max(1, min(int(settings.get("ranking_limit", 10)), 100))
    settings["stock_cache_minutes"] = max(1, min(int(settings.get("stock_cache_minutes", 15)), 1440))
    settings["buy_watch_near_percent"] = max(0.0, min(float(settings.get("buy_watch_near_percent", 3.0)), 100.0))
    settings["earnings_dashboard_limit"] = max(1, min(int(settings.get("earnings_dashboard_limit", 5)), 100))
    settings["earnings_near_days"] = max(1, min(int(settings.get("earnings_near_days", 7)), 365))
    settings["related_earnings_limit"] = max(1, min(int(settings.get("related_earnings_limit", 5)), 100))
    settings["past_earnings_days"] = max(0, min(int(settings.get("past_earnings_days", 30)), 3650))
    settings["show_unconfirmed_earnings"] = bool(settings.get("show_unconfirmed_earnings", True))
    auto = settings.get("earnings_auto_fetch", {})
    defaults = DEFAULT_SETTINGS["earnings_auto_fetch"]
    auto["enabled"] = bool(auto.get("enabled", defaults["enabled"]))
    auto["provider"] = "yfinance" if auto.get("provider") != "csv" else "csv"
    auto["max_tickers_per_run"] = max(1, min(int(auto.get("max_tickers_per_run", defaults["max_tickers_per_run"])), 100))
    auto["request_interval_seconds"] = max(1.0, min(float(auto.get("request_interval_seconds", defaults["request_interval_seconds"])), 60.0))
    auto["cache_hours"] = max(1, min(int(auto.get("cache_hours", defaults["cache_hours"])), 168))
    auto["candidate_retention_days"] = max(1, min(int(auto.get("candidate_retention_days", defaults["candidate_retention_days"])), 3650))
    auto["show_past_candidates"] = bool(auto.get("show_past_candidates", defaults["show_past_candidates"]))
    auto["save_same_candidates"] = bool(auto.get("save_same_candidates", defaults["save_same_candidates"]))
    auto["date_change_min_days"] = max(1, min(int(auto.get("date_change_min_days", defaults["date_change_min_days"])), 365))
    auto["include_confirmed_events"] = bool(auto.get("include_confirmed_events", defaults["include_confirmed_events"]))
    settings["earnings_auto_fetch"] = auto
    score = settings.get("score", {})
    for key, default in DEFAULT_SETTINGS["score"].items():
        try:
            score[key] = float(score.get(key, default))
        except (TypeError, ValueError):
            score[key] = float(default)
    settings["score"] = score
    return settings
