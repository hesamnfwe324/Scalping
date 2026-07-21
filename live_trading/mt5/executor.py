"""
mtapi.io Order Executor — place, modify and close orders via mtapi REST API.

Uses the connection token managed by connector.py.
mtapi.io REST reference: https://mt5.mtapi.io/index.html
"""
from dataclasses import dataclass
from typing import Optional
from live_trading.logger import get_logger
from live_trading.mt5.connector import _get, get_connection

log = get_logger()


@dataclass
class TradeResult:
    success:     bool
    position_id: Optional[str]
    message:     str
    order_id:    Optional[str] = None


# ── Lot normalisation ─────────────────────────────────────────────────────────

def _normalise_lot(lot: float,
                   vol_min: float  = 0.01,
                   vol_step: float = 0.01,
                   vol_max: float  = 500.0) -> float:
    steps  = round((lot - vol_min) / vol_step)
    result = vol_min + steps * vol_step
    return max(vol_min, min(vol_max, round(result, 4)))


# ── Place market order ────────────────────────────────────────────────────────

async def place_market_order(
    symbol:    str,
    direction: str,       # "BUY" | "SELL"
    lot_size:  float,
    sl:        float,
    tp:        float,
    comment:   str = "GSPv4",
    deviation: int = 30,
) -> TradeResult:
    token = get_connection()
    if token is None:
        return TradeResult(False, None, "No MT5 connection")

    lot       = _normalise_lot(lot_size)
    operation = "Buy" if direction == "BUY" else "Sell"

    log.debug(f"Placing {direction} {lot} lots {symbol} — SL={sl}  TP={tp}")

    try:
        result = await _get("OrderSend", {
            "id":        token,
            "symbol":    symbol,
            "operation": operation,
            "volume":    lot,
            "sl":        round(sl, 2),
            "tp":        round(tp, 2),
            "comment":   comment[:32],
        })

        # mtapi returns {"order": <ticket>, "retcode": 10009} on success
        retcode = result.get("retcode", -1)
        if retcode == 10009 or "order" in result:
            ticket  = str(result.get("order", ""))
            log.info(f"✅ Trade opened — ticket={ticket}  {direction} {lot} lots  SL={sl}  TP={tp}")
            return TradeResult(True, ticket, "OK", ticket)

        msg = result.get("message", str(result))
        log.error(f"❌ OrderSend failed: {msg}")
        return TradeResult(False, None, msg)

    except Exception as exc:
        log.error(f"❌ place_market_order error: {exc}")
        return TradeResult(False, None, str(exc))


# ── Close position ────────────────────────────────────────────────────────────

async def close_position(position_id: str) -> TradeResult:
    token = get_connection()
    if token is None:
        return TradeResult(False, None, "No MT5 connection")

    try:
        result = await _get("ClosePosition", {
            "id":     token,
            "ticket": position_id,
        })

        retcode = result.get("retcode", -1)
        if retcode == 10009 or result.get("order"):
            log.info(f"✅ Position {position_id} closed")
            return TradeResult(True, position_id, "Closed")

        msg = result.get("message", str(result))
        log.error(f"❌ ClosePosition failed: {msg}")
        return TradeResult(False, None, msg)

    except Exception as exc:
        log.error(f"❌ close_position error: {exc}")
        return TradeResult(False, None, str(exc))


# ── Modify position ───────────────────────────────────────────────────────────

async def modify_position(position_id: str,
                           sl: float,
                           tp: float) -> TradeResult:
    token = get_connection()
    if token is None:
        return TradeResult(False, None, "No MT5 connection")

    try:
        result = await _get("PositionModify", {
            "id":     token,
            "ticket": position_id,
            "sl":     round(sl, 2),
            "tp":     round(tp, 2),
        })

        retcode = result.get("retcode", -1)
        if retcode == 10009 or result.get("order"):
            log.info(f"✅ Position {position_id} modified — SL={sl}  TP={tp}")
            return TradeResult(True, position_id, "Modified")

        msg = result.get("message", str(result))
        log.error(f"❌ PositionModify failed: {msg}")
        return TradeResult(False, None, msg)

    except Exception as exc:
        log.error(f"❌ modify_position error: {exc}")
        return TradeResult(False, None, str(exc))
