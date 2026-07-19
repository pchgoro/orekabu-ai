"""Shared UI vocabulary, market colors, and priority mapping tests."""

from components.ui import density_padding, market_direction, priority_level, status_tone


def test_priority_levels_follow_shared_order() -> None:
    assert priority_level(1) == "urgent"
    assert priority_level(3) == "urgent"
    assert priority_level(4) == "today"
    assert priority_level(7) == "today"
    assert priority_level(8) == "later"
    assert priority_level(None) == "later"


def test_display_density_has_stable_spacing() -> None:
    assert density_padding("コンパクト") == "0.65rem"
    assert density_padding("標準") == "0.9rem"
    assert density_padding("ゆったり") == "1.2rem"
    assert density_padding("不正") == "0.9rem"


def test_japanese_market_direction_colors() -> None:
    assert market_direction(1) == "positive"
    assert market_direction("+12.5") == "positive"
    assert market_direction(-1) == "negative"
    assert market_direction("-0.01") == "negative"
    assert market_direction(0) == "muted"
    assert market_direction(None) == "muted"
    assert market_direction("データなし") == "muted"


def test_status_colors_do_not_reuse_market_gain_or_loss_colors() -> None:
    assert status_tone("warning") == "warning"
    assert status_tone("danger") == "warning"
    assert status_tone("info") == "info"
    assert status_tone("success") == "info"
    assert status_tone("positive") == "positive"
    assert status_tone("negative") == "negative"
    assert status_tone("unknown") == "info"
