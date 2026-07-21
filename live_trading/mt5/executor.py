"""
MetaAPI Order Executor — place, modify and close orders via MetaAPI SDK.
Platform-agnostic: works on Linux, Render, any Python environment.

Slippage control
────────────────
Every market order now carries a `deviation` parameter (broker points).
MetaAPI passes this as the "slippage" option, which tells the broker:
"fill me only if the execution price is within ±deviation points of the
requested price — otherwise reject the order."

For XAUUSD on a typical 5-digit broker 1 point = $0.001 per 0.01 lot.
Default 30 points ≈ $0.30 max slippage on a 1-lot trade — acceptable
for a 5-minute scalper whose SL is typically 150-400 points wide.
Set SLIPPAGE_POINTS=0 in env to rely entirely on the broker's default.
"""
from dataclasses import dataclass
from typing import Optional
from live_trading.logger import get_logger

log = get_logger()

# Uses the connection object managed by connector.py via its public accessor.
from live_trading.mt5.connector import get_connection


@dataclass
class TradeResult:
    success: bool
    position_id: Optional[str]
    message: str
    order_id: Optional[str] = None


# ── Lot normalisation ─────────────────────────────────────────────────────────

def _normalise_lot(lot: float,
                   vol_min: float = 0.01,
                   vol_step: float = 0.01,
                   vol_max: float = 500.0) -> float:
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
    deviation: int = 30,  # max slippage in broker points (0 = broker default)
) -> TradeResult:
    """
    Place a market order with slippage protection.

    Parameters
    ----------
    deviation : int
        Maximum acceptable slippage in broker points.
        Set to 0 to disable slippage control (broker default applies).
        Passed to MetaAPI as options["slippage"].
    """
    lot = _normalise_lot(lot_size)

    connection = get_connection()
    if connection is None:
        return TradeResult(False, None, "No MetaAPI connection")

    # Build order options — always include slippage when deviation > 0
    options: dict = {"comment": comment[:32]}
    if deviation > 0:
        options["slippage"] = deviation

    log.debug(
        f"Placing {direction} {lot} lots {symbol} — "
        f"SL={sl}  TP={tp}  slippage≤{deviation}pts"
    )

    try:
        if direction == "BUY":
            result = await connection.create_market_buy_order(
                symbol=symbol, volume=lot,
                stop_loss=round(sl, 2), take_profit=round(tp, 2),
                options=options,
            )
        else:
            result = await connection.create_market_sell_order(
                symbol=symbol, volume=lot,
                stop_loss=round(sl, 2), take_profit=round(tp, 2),
                options=options,
            )

        pos_id   = result.get("positionId")
        order_id = result.get("orderId")

        log.info(
            f"✅ Trade opened — positionId={pos_id}  "
            f"{direction} {lot} lots  SL={sl}  TP={tp}  "
            f"slippage≤{deviation}pts"
        )
        return TradeResult(True, pos_id, "OK", order_id)

    except Exception as exc:
        log.error(f"❌ place_market_order failed: {exc}")
        return TradeResult(False, None, str(exc))


# ── Close position ────────────────────────────────────────────────────────────

async def close_position(position_id: str) -> TradeResult:
    connection = get_connection()
    if connection is None:
        return TradeResult(False, None, "No MetaAPI connection")
    try:
        result = await connection.close_position(position_id)
        log.info(f"✅ Position {position_id} closed")
        return TradeResult(True, position_id, "OK",
                           result.get("orderId") if result else None)
    except Exception as exc:
        log.error(f"❌ close_position {position_id} failed: {exc}")
        return TradeResult(False, None, str(exc))


# ── Modify SL / TP ────────────────────────────────────────────────────────────

async def modify_sl_tp(position_id: str, sl: float, tp: float) -> TradeResult:
    connection = get_connection()
    if connection is None:
        return TradeResult(False, None, "No MetaAPI connection")
    try:
        await connection.modify_position(
            position_id=position_id,
            stop_loss=round(sl, 2),
            take_profit=round(tp, 2),
        )
        log.info(f"✅ SL/TP modified: pos={position_id}  SL={sl}  TP={tp}")
        return TradeResult(True, position_id, "OK")
    except Exception as exc:
        log.error(f"❌ modify_sl_tp {position_id} failed: {exc}")
        return TradeResult(False, None, str(exc))
