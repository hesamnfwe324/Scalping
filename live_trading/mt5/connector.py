"""
mtapi.io Connector — replaces MetaAPI SDK with a lightweight REST client.

mtapi.io connects directly to the MT5 broker server using the broker name
(e.g. "AMarkets-Demo") without needing a local MT5 terminal or Windows.

Required env vars:
    MTAPI_URL      — URL of the mtapi Docker instance (self-hosted on Render)
    MT5_HOST       — broker server name, e.g. "AMarkets-Demo"
    MT5_PORT       — usually 443
    MT5_USER       — MT5 account number
    MT5_PASSWORD   — MT5 account password

mtapi.io REST reference: https://mt5.mtapi.io/index.html
"""
import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import List, Optional
from urllib.parse import urlencode

import aiohttp

from live_trading.config import (
    MTAPI_URL, MT5_HOST, MT5_PORT, MT5_USER, MT5_PASSWORD
)
from live_trading.signals.gold_engine import OHLCV
from live_trading.logger import get_logger

log = get_logger()

# ── Module-level state ────────────────────────────────────────────────────────
_session:      Optional[aiohttp.ClientSession] = None
_token:        Optional[str]  = None   # connection token from /Connect
_connected:    bool           = False

# ── Timeframe → MT5 period map ───────────────────────────────────────────────
_TF_MAP = {
    "1m":  "M1",  "5m":  "M5",  "15m": "M15", "30m": "M30",
    "1h":  "H1",  "4h":  "H4",  "1d":  "D1",
    "M1":  "M1",  "M5":  "M5",  "M15": "M15", "M30": "M30",
    "H1":  "H1",  "H4":  "H4",  "D1":  "D1",
}

# Candle period duration in seconds (for bar-close detection)
_TF_SECONDS = {
    "M1": 60, "M5": 300, "M15": 900, "M30": 1800,
    "H1": 3600, "H4": 14400, "D1": 86400,
}


# ── HTTP helper ───────────────────────────────────────────────────────────────

async def _get(path: str, params: dict) -> dict:
    """GET {MTAPI_URL}/{path}?{params} and return parsed JSON."""
    global _session
    if _session is None or _session.closed:
        _session = aiohttp.ClientSession()
    url = f"{MTAPI_URL.rstrip('/')}/{path}?{urlencode(params)}"
    async with _session.get(url, timeout=aiohttp.ClientTimeout(total=15)) as resp:
        data = await resp.json(content_type=None)
        return data


# ── Connection lifecycle ──────────────────────────────────────────────────────

async def connect(*args, **kwargs) -> bool:
    """
    Connect to the MT5 broker via mtapi.io.
    Signature kept compatible with old MetaAPI connect(token, account_id).
    Actual credentials come from env vars (MT5_USER, MT5_PASSWORD, etc.).
    """
    global _token, _connected

    if not MTAPI_URL:
        log.error("MTAPI_URL is not set. Set it to your mtapi Docker service URL.")
        return False
    if not MT5_USER or not MT5_PASSWORD:
        log.error("MT5_USER and MT5_PASSWORD must be set.")
        return False

    try:
        log.info(f"Connecting to MT5 via mtapi.io → {MT5_HOST} user={MT5_USER}")
        # Use ConnectEx with serverName — /Connect?host= needs an IP address,
        # but MT5_HOST is a broker server name like 'AMarkets-Demo'.
        # ConnectEx resolves the broker name to the correct IP automatically.
        result = await _get("ConnectEx", {
            "user":       MT5_USER,
            "password":   MT5_PASSWORD,
            "serverName": MT5_HOST,
        })

        if isinstance(result, str):
            # Success: mtapi returns the connection token as a plain string
            _token = result
            _connected = True
            log.info(f"✅ Connected to MT5 broker — token={_token[:12]}…")
            return True

        # Error response is a dict with "code" and "message"
        code = result.get("code", "UNKNOWN")
        msg  = result.get("message", str(result))
        log.error(f"❌ MT5 connect failed [{code}]: {msg}")
        _connected = False
        return False

    except Exception as exc:
        log.error(f"❌ MT5 connect error: {exc}")
        _connected = False
        return False


async def disconnect() -> None:
    global _token, _connected, _session
    _token     = None
    _connected = False
    if _session and not _session.closed:
        await _session.close()
    log.info("MT5 connection closed")


def is_connected() -> bool:
    return _connected and _token is not None


def get_connection():
    """Compatibility shim — executor.py calls this; we return the token."""
    return _token


async def ensure_connected(*args, **kwargs) -> bool:
    if is_connected():
        return True
    log.warning("MT5 not connected — reconnecting …")
    return await connect()


# ── Candle data ───────────────────────────────────────────────────────────────

async def fetch_candles(symbol: str,
                         timeframe: str = "5m",
                         count: int = 300) -> List[OHLCV]:
    if not is_connected():
        return []
    period = _TF_MAP.get(timeframe, "M5")
    try:
        raw = await _get("Quotehistory", {
            "id":     _token,
            "symbol": symbol,
            "period": period,
            "bars":   count,
        })
        if not isinstance(raw, list):
            log.warning(f"Unexpected Quotehistory response: {raw}")
            return []

        candles: List[OHLCV] = []
        for c in raw:
            candles.append(OHLCV(
                open   = float(c.get("open",  0)),
                high   = float(c.get("high",  0)),
                low    = float(c.get("low",   0)),
                close  = float(c.get("close", 0)),
                volume = float(c.get("tickVolume", c.get("volume", 0))),
                time   = _parse_time(c.get("time", "")),
            ))
        return candles
    except Exception as exc:
        log.warning(f"fetch_candles error: {exc}")
        return []


# ── Account info ──────────────────────────────────────────────────────────────

async def get_account_info() -> dict:
    if not is_connected():
        return {}
    try:
        data = await _get("AccountSummary", {"id": _token})
        if isinstance(data, dict) and "balance" in data:
            return {
                "balance":    float(data.get("balance", 0)),
                "equity":     float(data.get("equity",  0)),
                "margin":     float(data.get("margin",  0)),
                "freeMargin": float(data.get("freeMargin", 0)),
                "currency":   data.get("currency", "USD"),
                "name":       data.get("name", ""),
                "server":     MT5_HOST,
                "leverage":   data.get("leverage", 0),
            }
        log.warning(f"Unexpected AccountSummary response: {data}")
        return {}
    except Exception as exc:
        log.warning(f"get_account_info error: {exc}")
        return {}


async def get_account_balance() -> float:
    info = await get_account_info()
    return info.get("balance", 0.0)


# ── Positions ─────────────────────────────────────────────────────────────────

async def get_open_positions(symbol: str) -> list:
    if not is_connected():
        return []
    try:
        data = await _get("OpenedOrders", {"id": _token})
        if not isinstance(data, list):
            return []
        # Filter by symbol; type 0 = BUY, 1 = SELL in MT5
        return [p for p in data if p.get("symbol") == symbol]
    except Exception as exc:
        log.warning(f"get_open_positions error: {exc}")
        return []


def mt5_pos_to_dict(pos: dict) -> dict:
    ptype     = pos.get("type", 0)
    direction = "BUY" if ptype == 0 else "SELL"
    return {
        "id":         str(pos.get("ticket", pos.get("id", ""))),
        "symbol":     pos.get("symbol", ""),
        "direction":  direction,
        "lot_size":   pos.get("volume", 0),
        "price_open": pos.get("openPrice", pos.get("priceOpen", 0)),
        "sl":         pos.get("sl", pos.get("stopLoss", 0)),
        "tp":         pos.get("tp", pos.get("takeProfit", 0)),
        "profit":     pos.get("profit", 0),
        "time_str":   str(pos.get("openTime", pos.get("time", ""))),
    }


# ── Bar-close detection ───────────────────────────────────────────────────────

async def get_last_completed_bar_time(symbol: str,
                                       timeframe: str = "5m") -> Optional[datetime]:
    candles = await fetch_candles(symbol, timeframe, count=2)
    if len(candles) < 2:
        return None
    # Second-to-last = last completed bar
    return candles[-2].time


# ── Helpers ───────────────────────────────────────────────────────────────────

def _parse_time(raw) -> datetime:
    if isinstance(raw, datetime):
        return raw.replace(tzinfo=timezone.utc) if raw.tzinfo is None else raw
    try:
        return datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except Exception:
        return datetime.now(timezone.utc)
