"""
MetaAPI Connector — replaces native MetaTrader5 package.
Works on Linux, macOS, Render, Railway, Fly.io — anywhere Python runs.

MetaAPI docs: https://metaapi.cloud/docs/client/python/
"""
import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import List, Optional

from live_trading.signals.gold_engine import OHLCV
from live_trading.logger import get_logger

log = get_logger()

# ── MetaAPI lazy import ───────────────────────────────────────────────────────
try:
    from metaapi_cloud_sdk import MetaApi
    METAAPI_AVAILABLE = True
except ImportError:
    MetaApi = None  # type: ignore
    METAAPI_AVAILABLE = False

# Module-level state (single connection shared across calls)
_api         = None
_account     = None
_connection  = None   # StreamingMetaApiConnection
_connected   = False


# ── MetaAPI timeframe map ────────────────────────────────────────────────────

_TF_MAP = {
    "1m": "1m", "5m": "5m", "15m": "15m", "30m": "30m",
    "1h": "1h", "4h": "4h",  "1d":  "1d",
    # legacy aliases
    "M1": "1m", "M5": "5m", "M15": "15m", "M30": "30m",
    "H1": "1h", "H4": "4h",  "D1":  "1d",
}


# ── Connection lifecycle ──────────────────────────────────────────────────────

async def connect(token: str, account_id: str,
                  sync_timeout: int = 120) -> bool:
    global _api, _account, _connection, _connected

    if not METAAPI_AVAILABLE:
        log.error("metaapi-cloud-sdk not installed. "
                  "Run:  pip install metaapi-cloud-sdk")
        return False
    if not token or not account_id:
        log.error("METAAPI_TOKEN and METAAPI_ACCOUNT_ID must be set.")
        return False

    try:
        log.info("Connecting to MetaAPI …")
        _api     = MetaApi(token)
        _account = await _api.metatrader_account_api.get_account(account_id)

        # Deploy if not already deployed
        if _account.state not in ("DEPLOYED", "DEPLOYING"):
            log.info("Deploying MetaAPI account (first-time setup, ~30s) …")
            await _account.deploy()

        await _account.wait_deployed(timeout_in_seconds=sync_timeout)
        log.info(f"Account deployed: {_account.name}  broker={_account.broker}")

        # Streaming connection (real-time terminal state)
        _connection = _account.get_streaming_connection()
        await _connection.connect()
        await _connection.wait_synchronized(timeout_in_seconds=sync_timeout)

        _connected = True
        log.info("✅ MetaAPI connected and synchronized")
        return True

    except Exception as exc:
        log.error(f"❌ MetaAPI connection failed: {exc}")
        _connected = False
        return False


async def disconnect() -> None:
    global _connection, _connected
    if _connection:
        try:
            await _connection.close()
        except Exception as exc:
            # Log the exception instead of swallowing it silently.
            # A streaming session that fails to close gracefully may leave
            # a dangling WebSocket on the MetaAPI side; logging lets operators
            # investigate if they see unexpected MetaAPI session warnings.
            log.warning(f"MetaAPI disconnect — connection.close() raised: {exc}")
    _connected = False
    log.info("MetaAPI connection closed")


def is_connected() -> bool:
    return _connected and _connection is not None


def get_connection():
    """
    Return the active MetaAPI streaming connection object, or None.

    Prefer this public accessor over accessing `_connection` directly from
    other modules. The underscore-prefixed module variable is an implementation
    detail; using this function ensures that any future refactoring of the
    connection lifecycle remains encapsulated here.
    """
    return _connection


async def ensure_connected(token: str, account_id: str,
                            sync_timeout: int = 120,
                            attempt: int = 1) -> bool:
    """
    Reconnect with exponential backoff built-in.

    The caller passes the current attempt number (tracked externally in live_loop)
    so this function can log it clearly.  The actual sleep between attempts is
    managed by live_loop — this function is a single attempt wrapper.
    """
    if is_connected():
        return True
    log.warning(f"MetaAPI not connected — reconnect attempt #{attempt} …")
    return await connect(token, account_id, sync_timeout)


# ── Account information ───────────────────────────────────────────────────────

async def get_account_info() -> dict:
    if not is_connected():
        return {}
    try:
        info = _connection.terminal_state.account_information
        if not info:
            return {}
        return {
            "login":       info.get("login"),
            "server":      info.get("broker"),
            "balance":     info.get("balance", 0.0),
            "equity":      info.get("equity",  0.0),
            "margin":      info.get("margin",  0.0),
            "margin_free": info.get("freeMargin", 0.0),
            "profit":      info.get("profit",  0.0),
            "currency":    info.get("currency", "USD"),
            "leverage":    info.get("leverage", 0),
        }
    except Exception as exc:
        log.warning(f"get_account_info error: {exc}")
        return {}


async def get_account_balance() -> float:
    info = await get_account_info()
    return float(info.get("balance", 0.0))


# ── Candle fetching ───────────────────────────────────────────────────────────

def _metaapi_candle_to_ohlcv(c: dict) -> Optional[OHLCV]:
    try:
        t = c.get("time") or c.get("brokerTime", "")
        if isinstance(t, datetime):
            iso = t.strftime("%Y-%m-%dT%H:%M:%SZ")
        else:
            iso = str(t)[:19].replace(" ", "T") + "Z"
        return OHLCV(
            time=iso,
            open=float(c["open"]),
            high=float(c["high"]),
            low=float(c["low"]),
            close=float(c["close"]),
            volume=float(c.get("tickVolume", c.get("volume", 1))),
        )
    except Exception:
        return None


async def fetch_candles(symbol: str, timeframe: str = "5m",
                        count: int = 300) -> List[OHLCV]:
    """Return up to `count` recently completed candles."""
    if not METAAPI_AVAILABLE or _account is None:
        log.warning("MetaAPI not available — returning empty candle list")
        return []

    tf = _TF_MAP.get(timeframe, timeframe)

    try:
        # MetaAPI returns candles newest-first; we request count+1 and drop
        # the still-forming current bar (it has the most recent timestamp).
        end_time = datetime.now(timezone.utc)
        raw = await _account.get_historical_candles(
            symbol, tf, end_time, count + 1
        )

        if not raw:
            log.warning(f"No candles returned for {symbol}/{tf}")
            return []

        # Sort oldest → newest, drop the last (forming) bar.
        # MetaAPI may return `time` as a datetime object or as a string depending
        # on SDK version. Normalise to ISO string so sorting never raises TypeError
        # from comparing datetime vs str.
        def _sort_key(c: dict) -> str:
            t = c.get("time", "")
            if isinstance(t, datetime):
                return t.isoformat()
            return str(t)

        raw_sorted = sorted(raw, key=_sort_key)
        raw_sorted = raw_sorted[:-1]  # exclude forming bar

        # Deduplicate by time key — prevents duplicate candles from MetaAPI SDK
        # from shifting indicator calculations by one bar (ST-06 / M-01).
        # Only the first occurrence of each timestamp is kept; sort order is
        # already ascending so the first occurrence is always the earliest.
        # Trading logic is unaffected: duplicate candles carry identical OHLCV
        # data — removing them produces the same candle sequence as if the SDK
        # had never returned the duplicate.
        seen_times: set = set()
        deduped: list = []
        for c in raw_sorted:
            t_key = _sort_key(c)
            if t_key not in seen_times:
                seen_times.add(t_key)
                deduped.append(c)
        if len(deduped) < len(raw_sorted):
            log.warning(
                f"fetch_candles: removed {len(raw_sorted) - len(deduped)} "
                f"duplicate candle(s) for {symbol}/{tf}"
            )
        raw_sorted = deduped

        candles: List[OHLCV] = []
        for c in raw_sorted:
            parsed = _metaapi_candle_to_ohlcv(c)
            if parsed:
                candles.append(parsed)

        log.debug(f"Fetched {len(candles)} candles for {symbol}/{tf}")
        return candles

    except Exception as exc:
        log.error(f"fetch_candles error: {exc}")
        return []


async def get_last_completed_bar_time(symbol: str,
                                       timeframe: str = "5m") -> Optional[datetime]:
    """Return the open-time of the last COMPLETED candle."""
    tf  = _TF_MAP.get(timeframe, timeframe)
    end = datetime.now(timezone.utc)
    try:
        raw = await _account.get_historical_candles(symbol, tf, end, 2)
        if not raw or len(raw) < 2:
            return None
        raw_sorted = sorted(raw, key=lambda c: c.get("time", "").isoformat()
                            if isinstance(c.get("time"), datetime) else str(c.get("time", "")))
        # second-to-last = last completed bar
        t = raw_sorted[-2].get("time")
        if isinstance(t, datetime):
            return t.replace(tzinfo=timezone.utc) if t.tzinfo is None else t
        return datetime.fromisoformat(str(t).replace("Z", "+00:00"))
    except Exception as exc:
        log.debug(f"get_last_completed_bar_time error: {exc}")
        return None


# ── Open positions ────────────────────────────────────────────────────────────

def get_open_positions(symbol: str) -> list:
    """Return list of open positions for this symbol from terminal state."""
    if not is_connected():
        return []
    try:
        positions = _connection.terminal_state.positions or []
        return [p for p in positions
                if p.get("symbol") == symbol]
    except Exception as exc:
        log.warning(f"get_open_positions error: {exc}")
        return []


def mt5_pos_to_dict(pos: dict) -> dict:
    direction = "BUY" if pos.get("type") == "POSITION_TYPE_BUY" else "SELL"
    return {
        "id":         pos.get("id"),
        "symbol":     pos.get("symbol"),
        "direction":  direction,
        "lot_size":   pos.get("volume"),
        "price_open": pos.get("openPrice"),
        "sl":         pos.get("stopLoss"),
        "tp":         pos.get("takeProfit"),
        "profit":     pos.get("profit"),
        "time_str":   str(pos.get("time", "")),
    }
