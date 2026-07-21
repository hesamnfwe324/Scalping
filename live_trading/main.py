"""
GoldScalperPro v4 — Live Trading Entry Point (MetaAPI / Linux-compatible)

Usage:
    python -m live_trading.main

Required environment variables:
    METAAPI_TOKEN       — from https://app.metaapi.cloud → API
    METAAPI_ACCOUNT_ID  — from https://app.metaapi.cloud → Accounts

Optional:
    SYMBOL              — default: XAUUSD
    RISK_PERCENT        — default: 1.0
    MIN_CONFIRMATIONS   — default: 3
    DAILY_LOSS_LIMIT_PCT — default: 3.0
    MAX_DRAWDOWN_PCT    — default: 8.0
    SLIPPAGE_POINTS     — default: 30
"""
import asyncio
import sys
import os

# Python version guard — 3.11+ required for asyncio stability and timezone support.
# 3.10 is insufficient: asyncio.Runner not yet available; utcnow deprecation not patched.
if sys.version_info < (3, 11):
    print(
        f"ERROR: GoldScalperPro requires Python 3.11 or higher. "
        f"You are running Python {sys.version_info.major}.{sys.version_info.minor}."
    )
    sys.exit(1)

# Allow  python main.py  from inside live_trading/
if __name__ == "__main__" and __package__ is None:
    _root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if _root not in sys.path:
        sys.path.insert(0, _root)

from live_trading.logger import get_logger
from live_trading.config import METAAPI_TOKEN, METAAPI_ACCOUNT_ID
from live_trading.trading.live_loop import GoldScalperLive

log = get_logger()


async def _main() -> None:
    if not METAAPI_TOKEN:
        log.error("MetaAPI credentials are not configured.")
        log.error("Set METAAPI_TOKEN and METAAPI_ACCOUNT_ID environment variables.")
        log.error("Get credentials from: https://app.metaapi.cloud")
        sys.exit(1)
    if not METAAPI_ACCOUNT_ID:
        log.error("MetaAPI credentials are not configured.")
        log.error("Set METAAPI_TOKEN and METAAPI_ACCOUNT_ID environment variables.")
        log.error("Get credentials from: https://app.metaapi.cloud")
        sys.exit(1)

    engine = GoldScalperLive()
    connected = await engine.start()

    # If start() returned False (MetaAPI connection failure), exit with non-zero
    # code so Render / supervisor / systemd will auto-restart the process.
    if connected is False:
        log.error(
            "Engine failed to connect to MetaAPI. "
            "Exiting with error code 1 so the process manager can restart."
        )
        sys.exit(1)


def main() -> None:
    try:
        asyncio.run(_main())
    except KeyboardInterrupt:
        log.info("Keyboard interrupt — shutting down")


if __name__ == "__main__":
    main()
