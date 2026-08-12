"""RANGE regression tests: SMC plus one PA/Wyckoff confirmation is enough."""

from live_trading.signals.decision_engine import (
    _effective_min_confirmations,
    _range_confirmation_gate,
)
from live_trading.signals.entry_filter import EntryFilterResult


def test_range_keeps_default_two_confirmation_floor():
    assert _effective_min_confirmations(2, "RANGE", False) == 2


def test_range_floor_does_not_weaken_stricter_operator_setting():
    assert _effective_min_confirmations(4, "RANGE", False) == 4


def test_range_floor_applies_even_when_counter_trend_base_is_lower():
    assert _effective_min_confirmations(1, "RANGE", True) == 2


def test_range_accepts_smc_plus_price_action():
    result = EntryFilterResult(
        allowed=True, direction="BUY", confirmation_count=2,
        smc=True, trend=False, price_action=True, wyckoff=False,
    )
    assert _range_confirmation_gate(result, 2) == (True, "")


def test_range_accepts_smc_plus_wyckoff():
    result = EntryFilterResult(
        allowed=True, direction="BUY", confirmation_count=2,
        smc=True, trend=False, price_action=False, wyckoff=True,
    )
    assert _range_confirmation_gate(result, 2) == (True, "")


def test_range_rejects_smc_plus_trend_without_pa_or_wyckoff():
    result = EntryFilterResult(
        allowed=True, direction="BUY", confirmation_count=2,
        smc=True, trend=True, price_action=False, wyckoff=False,
    )
    allowed, reason = _range_confirmation_gate(result, 2)
    assert not allowed
    assert "Price Action or Wyckoff" in reason


def test_non_range_regime_keeps_global_confirmation_setting():
    assert _effective_min_confirmations(2, "WEAK_TREND_BULL", False) == 2
