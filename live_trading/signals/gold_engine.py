"""
Gold Engine — EMA, ATR, RSI, Bollinger Bands
Ported from goldEngine.ts
"""
from typing import List
from dataclasses import dataclass


@dataclass
class OHLCV:
    time: str
    open: float
    high: float
    low: float
    close: float
    volume: float


def calc_ema(closes: List[float], period: int) -> float:
    if len(closes) < period:
        return closes[-1] if closes else 0.0
    k = 2.0 / (period + 1)
    ema = sum(closes[:period]) / period
    for price in closes[period:]:
        ema = price * k + ema * (1 - k)
    return round(ema, 4)


def calc_ema_array(closes: List[float], period: int) -> List[float]:
    """Returns EMA value at every bar (same length as closes)."""
    if len(closes) < period:
        return closes[:]
    k = 2.0 / (period + 1)
    result = [0.0] * len(closes)
    ema = sum(closes[:period]) / period
    for i in range(period):
        result[i] = ema
    for i in range(period, len(closes)):
        ema = closes[i] * k + ema * (1 - k)
        result[i] = ema
    return result


def calc_atr(candles: List[OHLCV], period: int = 14) -> float:
    """Returns the most recent ATR value."""
    if len(candles) < 2:
        return 0.0
    trs = []
    for i in range(1, len(candles)):
        c, p = candles[i], candles[i - 1]
        trs.append(max(c.high - c.low,
                       abs(c.high - p.close),
                       abs(c.low - p.close)))
    if not trs:
        return 0.0
    # Wilder smoothing
    if len(trs) < period:
        return sum(trs) / len(trs)
    atr = sum(trs[:period]) / period
    for tr in trs[period:]:
        atr = (atr * (period - 1) + tr) / period
    return round(atr, 4)


def calc_atr_array(candles: List[OHLCV], period: int = 14) -> List[float]:
    """Returns ATR at every bar."""
    result = [0.0] * len(candles)
    if len(candles) < 2:
        return result
    trs = []
    for i in range(1, len(candles)):
        c, p = candles[i], candles[i - 1]
        trs.append(max(c.high - c.low,
                       abs(c.high - p.close),
                       abs(c.low - p.close)))
    if not trs:
        return result
    atr = sum(trs[:period]) / min(period, len(trs))
    for i, tr in enumerate(trs):
        if i >= period:
            atr = (atr * (period - 1) + tr) / period
        result[i + 1] = atr
    return result
