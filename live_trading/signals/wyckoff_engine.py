"""
Wyckoff Analysis Engine
Ported from wyckoffEngine.ts — confirmation only, never triggers alone.

CRITICAL FIX (global-state cross-contamination):
  The previous implementation stored a single module-level _calibrated_m5
  config. The live loop calibrates it from M5 candles, but the MTF filter
  also calls analyze_wyckoff() with H1 candles — which then ran against M5
  parameters. H1 candle bodies are ~12× larger than M5 bodies, so M5
  spring_margin and max_range_pct thresholds were orders-of-magnitude too
  tight, making H1 Wyckoff always return NEUTRAL.

  Fix: replace the single global with a per-timeframe dict. Callers pass
  a timeframe key ("M5", "H1", etc.) to set_calibrated_config() and
  analyze_wyckoff(). Defaults to CFG_M5 / CFG_H1 when no calibration has
  been provided for that timeframe, so existing callers that omit the
  timeframe argument remain backward-compatible.
"""
from dataclasses import dataclass
from typing import Dict, List, Literal, Optional
from live_trading.signals.gold_engine import OHLCV

# ── Config ────────────────────────────────────────────────────────────────────

@dataclass
class WyckoffConfig:
    range_bars: int
    trend_bars: int
    spring_margin: float
    upthrust_margin: float
    min_range_touches: int
    max_range_pct: float
    min_range_pct: float
    recent_bars: int


# M5 base config — small margins, tight range thresholds
CFG_M5 = WyckoffConfig(
    range_bars=20, trend_bars=12,
    spring_margin=0.20, upthrust_margin=0.20,
    min_range_touches=2,
    max_range_pct=0.010, min_range_pct=0.001,
    recent_bars=6,
)

# H1 base config — margins ~12× larger to match H1 candle size.
# A 20-bar H1 range spans ~20 hours; spring_margin of ~2.0 is appropriate
# for XAUUSD which moves $5–$15 in a typical H1 candle.
CFG_H1 = WyckoffConfig(
    range_bars=20, trend_bars=12,
    spring_margin=2.0, upthrust_margin=2.0,
    min_range_touches=2,
    max_range_pct=0.025, min_range_pct=0.005,
    recent_bars=6,
)

# Per-timeframe calibrated configs — keyed by canonical timeframe string.
# Set by set_calibrated_config(); read by _get_cfg().
_calibrated: Dict[str, WyckoffConfig] = {}

# Canonical timeframe normalisers — map any alias to a single storage key.
_TF_ALIASES: Dict[str, str] = {
    "M1": "M1",   "1m": "M1",
    "M5": "M5",   "5m": "M5",
    "M10": "M10", "10m": "M10",
    "M15": "M15", "15m": "M15",
    "M20": "M20", "20m": "M20",
    "M30": "M30", "30m": "M30",
    "H1": "H1",   "1h": "H1",
    "H4": "H4",   "4h": "H4",
    "D1": "D1",   "1d": "D1",
}

# Default fallback configs when no calibration is available for a timeframe.
_TF_DEFAULTS: Dict[str, WyckoffConfig] = {
    "H1": CFG_H1,
    "H4": CFG_H1,  # H4 reuses H1 as a conservative approximation
    "D1": CFG_H1,
}


def _canonical_tf(timeframe: str) -> str:
    """Normalise a timeframe alias to its canonical storage key."""
    return _TF_ALIASES.get(timeframe, timeframe.upper())


def calibrate_wyckoff(candles: List[OHLCV]) -> WyckoffConfig:
    """Derive WyckoffConfig from real OHLCV data (mirrors calibrateM5Config).

    The returned config is data-driven — pass it to set_calibrated_config()
    with the appropriate timeframe key so it is stored correctly.
    """
    n = len(candles)
    if n < 200:
        return CFG_M5

    # Median 14-bar ATR (sampled every 30 bars)
    atrs = []
    for i in range(20, n, 30):
        lo = max(1, i - 13)
        total, cnt = 0.0, 0
        for j in range(lo, i + 1):
            c, p = candles[j], candles[j - 1]
            total += max(c.high - c.low, abs(c.high - p.close), abs(c.low - p.close))
            cnt += 1
        if cnt > 0:
            atrs.append(total / cnt)
    atrs.sort()
    median_atr = atrs[int(len(atrs) * 0.50)] if atrs else 5.0

    # Rolling 20-bar range/price percentiles
    range_pcts = []
    for i in range(32, n, 10):
        sl = candles[i - 20:i]
        hi = max(c.high for c in sl)
        lo_p = min(c.low for c in sl)
        price = sl[-1].close
        if price > 0:
            range_pcts.append((hi - lo_p) / price)
    range_pcts.sort()

    p85 = range_pcts[int(len(range_pcts) * 0.85)] if range_pcts else 0.010
    margin = round(median_atr * 0.80, 2)

    return WyckoffConfig(
        range_bars=20, trend_bars=12,
        spring_margin=margin, upthrust_margin=margin,
        min_range_touches=2,
        max_range_pct=round(p85, 5), min_range_pct=0.0005,
        recent_bars=8,
    )


def set_calibrated_config(cfg: WyckoffConfig, timeframe: str = "M5") -> None:
    """Store a calibrated WyckoffConfig for *timeframe*.

    Callers that do not pass timeframe default to "M5" for backward
    compatibility with the old single-global API.
    """
    key = _canonical_tf(timeframe)
    _calibrated[key] = cfg


def _get_cfg(timeframe: str = "M5") -> WyckoffConfig:
    """Return the best available config for *timeframe*.

    Priority: calibrated > TF-specific default > CFG_M5.
    """
    key = _canonical_tf(timeframe)
    if key in _calibrated:
        return _calibrated[key]
    return _TF_DEFAULTS.get(key, CFG_M5)


# ── Output ────────────────────────────────────────────────────────────────────

@dataclass
class WyckoffResult:
    phase: Literal["ACCUMULATION", "DISTRIBUTION", "NEUTRAL"]
    spring: bool
    upthrust: bool
    volume_confirmed: bool
    wyckoff_signal: Literal["BUY", "SELL", "NEUTRAL"]
    wyckoff_score: float   # 0–1


# ── Helpers ───────────────────────────────────────────────────────────────────

def _avg(values: List[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _detect_phase(candles: List[OHLCV], cfg: WyckoffConfig):
    n = len(candles)
    if n < cfg.range_bars + cfg.trend_bars:
        return "NEUTRAL", 0.0, 0.0, 0

    range_start = n - cfg.range_bars
    range_candles = candles[range_start:]

    support    = min(c.low  for c in range_candles)
    resistance = max(c.high for c in range_candles)
    range_size = resistance - support
    mid_price  = candles[-1].close

    range_pct = range_size / mid_price if mid_price > 0 else 0
    if not (cfg.min_range_pct <= range_pct <= cfg.max_range_pct):
        return "NEUTRAL", support, resistance, range_start

    touch_band = range_size * 0.20
    top_band   = resistance - touch_band
    bot_band   = support    + touch_band

    top_touches = sum(1 for c in range_candles if c.high >= top_band)
    bot_touches = sum(1 for c in range_candles if c.low  <= bot_band)

    if top_touches < cfg.min_range_touches or bot_touches < cfg.min_range_touches:
        return "NEUTRAL", support, resistance, range_start

    trend_start   = range_start - cfg.trend_bars
    trend_candles = candles[max(0, trend_start):range_start]
    if len(trend_candles) < 4:
        return "NEUTRAL", support, resistance, range_start

    trend_move = trend_candles[-1].close - trend_candles[0].close
    trend_pct  = abs(trend_move) / trend_candles[0].close if trend_candles[0].close > 0 else 0

    if trend_pct >= 0.002:
        phase = "ACCUMULATION" if trend_move < 0 else "DISTRIBUTION"
    else:
        phase = "NEUTRAL"

    return phase, support, resistance, range_start


def _detect_spring(candles: List[OHLCV], range_start: int, cfg: WyckoffConfig) -> bool:
    n = len(candles)
    range_candles = candles[range_start:n]
    total_bars    = len(range_candles)

    establish_bars = max(4, total_bars - cfg.recent_bars)
    if establish_bars <= 0:
        return False

    early_range = range_candles[:establish_bars]
    support = min(c.low for c in early_range)
    avg_vol = _avg([c.volume for c in range_candles])

    scan_start = range_start + establish_bars
    for i in range(scan_start, n):
        c = candles[i]
        if (c.low < support and
                c.low >= support - cfg.spring_margin and
                c.close > support and
                c.volume > avg_vol):
            return True
    return False


def _detect_upthrust(candles: List[OHLCV], range_start: int, cfg: WyckoffConfig) -> bool:
    n = len(candles)
    range_candles = candles[range_start:n]
    total_bars    = len(range_candles)

    establish_bars = max(4, total_bars - cfg.recent_bars)
    if establish_bars <= 0:
        return False

    early_range  = range_candles[:establish_bars]
    resistance   = max(c.high for c in early_range)
    avg_vol      = _avg([c.volume for c in range_candles])

    scan_start = range_start + establish_bars
    for i in range(scan_start, n):
        c = candles[i]
        if (c.high > resistance and
                c.high <= resistance + cfg.upthrust_margin and
                c.close < resistance and
                c.volume > avg_vol):
            return True
    return False


def _confirm_volume(candles: List[OHLCV], phase: str, range_start: int) -> bool:
    if phase == "NEUTRAL":
        return False
    range_candles = candles[range_start:]
    up_vol = sum(c.volume for c in range_candles if c.close > c.open)
    dn_vol = sum(c.volume for c in range_candles if c.close <= c.open)
    total  = up_vol + dn_vol
    if total == 0:
        return False
    if phase == "ACCUMULATION":
        return (up_vol / total) > 0.55
    return (dn_vol / total) > 0.55


# ── Main ──────────────────────────────────────────────────────────────────────

_NEUTRAL = WyckoffResult(
    phase="NEUTRAL", spring=False, upthrust=False,
    volume_confirmed=False, wyckoff_signal="NEUTRAL", wyckoff_score=0.0
)


def analyze_wyckoff(candles: List[OHLCV], timeframe: str = "M5") -> WyckoffResult:
    """Analyse Wyckoff phase using the config calibrated for *timeframe*.

    Passing timeframe ensures that H1 analysis uses H1-appropriate thresholds
    (spring_margin, max_range_pct) instead of the M5-calibrated values.
    Callers that omit timeframe default to "M5" for backward compatibility.
    """
    cfg = _get_cfg(timeframe)

    if len(candles) < cfg.range_bars + cfg.trend_bars:
        return _NEUTRAL

    phase, _sup, _res, range_start = _detect_phase(candles, cfg)
    if phase == "NEUTRAL":
        return _NEUTRAL

    spring    = _detect_spring(candles, range_start, cfg)
    upthrust  = _detect_upthrust(candles, range_start, cfg)
    vol_conf  = _confirm_volume(candles, phase, range_start)

    # Contradiction check
    contradiction = (
        (phase == "ACCUMULATION" and upthrust and not spring) or
        (phase == "DISTRIBUTION" and spring and not upthrust)
    )
    if contradiction:
        return WyckoffResult(phase=phase, spring=spring, upthrust=upthrust,  # type: ignore
                             volume_confirmed=vol_conf,
                             wyckoff_signal="NEUTRAL", wyckoff_score=0.0)

    score_raw = 0.30
    if phase == "ACCUMULATION":
        signal = "BUY"
        if spring:   score_raw += 0.40
        if vol_conf: score_raw += 0.30
    else:
        signal = "SELL"
        if upthrust: score_raw += 0.40
        if vol_conf: score_raw += 0.30

    return WyckoffResult(
        phase=phase, spring=spring, upthrust=upthrust,  # type: ignore
        volume_confirmed=vol_conf,
        wyckoff_signal=signal,  # type: ignore
        wyckoff_score=round(min(1.0, score_raw), 2),
    )
