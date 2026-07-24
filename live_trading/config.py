"""
GoldScalperPro v4 — Live Trading Configuration
MT5 access via MetaAPI.cloud (full broker database, no local MT5 terminal needed).
"""
import os

# ── MetaAPI.cloud ─────────────────────────────────────────────────────────────
# Sign up free at https://metaapi.cloud, add your MT5 account, then set these
# two env vars on Render (robot service):
#   METAAPI_TOKEN      — API token from the MetaAPI dashboard
#   METAAPI_ACCOUNT_ID — the MT5 account ID shown in MetaAPI dashboard
METAAPI_TOKEN      = os.getenv("METAAPI_TOKEN",      "")
METAAPI_ACCOUNT_ID = os.getenv("METAAPI_ACCOUNT_ID", "")

# ── MT5 Broker Credentials (shown in logs / state only) ──────────────────────
MTAPI_URL     = os.getenv("MTAPI_URL",     "")   # no longer used

# ── MT5 Broker Credentials ────────────────────────────────────────────────────
# MT5_HOST: broker server name exactly as shown in MT5 terminal
#   (e.g. "AMarkets-Demo", "ICMarkets-Demo02", "Exness-MT5Trial")
MT5_HOST      = os.getenv("MT5_HOST",     "AMarkets-Demo")
MT5_PORT      = int(os.getenv("MT5_PORT", "443"))
MT5_USER      = os.getenv("MT5_USER",     "")   # MT5 account number (login)
MT5_PASSWORD  = os.getenv("MT5_PASSWORD", "")   # MT5 account password

# ── Symbol & Timeframe ────────────────────────────────────────────────────────
SYMBOL        = os.getenv("SYMBOL",    "XAUUSD")
TIMEFRAME     = "5m"          # mtapi period: M1/M5/M15/M30/H1/H4/D1
CANDLE_WINDOW = 300           # bars sent to signal engine

# ── Risk & Trade Rules ────────────────────────────────────────────────────────
RISK_PERCENT       = float(os.getenv("RISK_PERCENT",      "1.0"))
MIN_CONFIRMATIONS  = int(os.getenv("MIN_CONFIRMATIONS",    "3"))
MAX_OPEN_TRADES    = 1
USE_ATR_HIGH_VOL_FILTER = False

# ── Order Settings ────────────────────────────────────────────────────────────
COMMENT       = "GSPv4"

# ── Loop Timing ───────────────────────────────────────────────────────────────
BAR_CHECK_INTERVAL = 15       # seconds between candle-close checks
RECONNECT_DELAY    = 30       # seconds before reconnect attempt
SYNC_TIMEOUT       = 120      # seconds to wait for initial connect

# ── File Paths (for Telegram panel) ──────────────────────────────────────────
STATE_FILE          = os.getenv("STATE_FILE",           "robot_state.json")
MT5_SNAPSHOT        = os.getenv("MT5_SNAPSHOT",         "robot_mt5_snapshot.json")
COMMANDS_FILE       = os.getenv("COMMANDS_FILE",        "robot_commands.json")
GUARDIAN_STATE_FILE = os.getenv("GUARDIAN_STATE_FILE",  "guardian_state.json")
LOG_FILE            = os.getenv("LOG_FILE",             "live_trading/robot.log")

# ── Risk Guardian — Circuit Breakers ─────────────────────────────────────────
DAILY_LOSS_LIMIT_PCT = float(os.getenv("DAILY_LOSS_LIMIT_PCT", "3.0"))
MAX_DRAWDOWN_PCT     = float(os.getenv("MAX_DRAWDOWN_PCT",      "8.0"))
SLIPPAGE_POINTS      = int(os.getenv("SLIPPAGE_POINTS",         "30"))

# ── Wyckoff Calibration ───────────────────────────────────────────────────────
WYCKOFF_MAX_RANGE_PCT = 0.01163
WYCKOFF_SPRING_MARGIN = 2.06

# ── Redis IPC ─────────────────────────────────────────────────────────────────
REDIS_URL = os.getenv("REDIS_URL", "")

# (METAAPI_TOKEN and METAAPI_ACCOUNT_ID are now read from env at the top)
