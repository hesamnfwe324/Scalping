"""Option 4 regression tests: RANGE needs three confirmations."""

from live_trading.signals.decision_engine import _effective_min_confirmations


def test_range_raises_default_two_confirmation_floor_to_three():
    assert _effective_min_confirmations(2, "RANGE", False) == 3


def test_range_floor_does_not_weaken_stricter_operator_setting():
    assert _effective_min_confirmations(4, "RANGE", False) == 4


def test_range_floor_applies_even_when_counter_trend_base_is_lower():
    assert _effective_min_confirmations(1, "RANGE", True) == 3


def test_non_range_regime_keeps_global_confirmation_setting():
    assert _effective_min_confirmations(2, "WEAK_TREND_BULL", False) == 2
