"""
GoldScalperPro v4 — Live Trading Configuration
All signal parameters match the TypeScript backtest exactly.
MT5 access via MetaAPI (platform-agnostic: Linux / Render / Windows).
"""
import os

# ── MetaAPI Credentials ───────────────────────────────────────────────────────
# Get these from https://app.metaapi.cloud → Accounts → Copy Account ID
# and https://app.metaapi.cloud → API → Copy token
METAAPI_TOKEN      = os.getenv("METAAPI_TOKEN", "")
METAAPI_ACCOUNT_ID = os.getenv("METAAPI_ACCOUNT_ID", "")

# ── Symbol & Timeframe ────────────────────────────────────────────────────────
SYMBOL             = os.getenv("SYMBOL", "XAUUSD")
TIMEFRAME          = "5m"         # MetaAPI format: 1m / 5m / 15m / 1h / 4h / 1d
CANDLE_WINDOW      = 300          # bars sent to signal engine

# ── Risk & Trade Rules ────────────────────────────────────────────────────────
RISK_PERCENT       = float(os.getenv("RISK_PERCENT", "1.0"))  # % of balance
MIN_CONFIRMATIONS  = int(os.getenv("MIN_CONFIRMATIONS", "3"))  # 3 or 4
MAX_OPEN_TRADES    = 1            # never open more than 1 XAUUSD position
USE_ATR_HIGH_VOL_FILTER = False   # disabled — reduced backtest profits

# ── Order Settings ────────────────────────────────────────────────────────────
COMMENT            = "GSPv4"

# ── Loop Timing ───────────────────────────────────────────────────────────────
BAR_CHECK_INTERVAL = 15           # seconds between "did a new M5 bar open?" checks
RECONNECT_DELAY    = 30           # seconds to wait before reconnect attempt
SYNC_TIMEOUT       = 120          # seconds to wait for MetaAPI sync

# ── File Paths (for Telegram panel) ──────────────────────────────────────────
STATE_FILE         = os.getenv("STATE_FILE",    "robot_state.json")
MT5_SNAPSHOT       = os.getenv("MT5_SNAPSHOT",  "robot_mt5_snapshot.json")
COMMANDS_FILE       = os.getenv("COMMANDS_FILE",       "robot_commands.json")
GUARDIAN_STATE_FILE = os.getenv("GUARDIAN_STATE_FILE", "guardian_state.json")
LOG_FILE           = os.getenv("LOG_FILE",      "live_trading/robot.log")

# ── Risk Guardian — Circuit Breakers ─────────────────────────────────────────
# Halt trading if intraday PnL drops below this % of session-open balance.
# Resets automatically at UTC midnight.
DAILY_LOSS_LIMIT_PCT = float(os.getenv("DAILY_LOSS_LIMIT_PCT", "3.0"))

# Halt trading if live equity drops more than this % below the session equity peak.
# Does NOT auto-reset — requires manual /reset_guardian command in Telegram.
MAX_DRAWDOWN_PCT     = float(os.getenv("MAX_DRAWDOWN_PCT",     "8.0"))

# Maximum allowed slippage for market orders (in broker points).
# Prevents fills at catastrophically bad prices during fast markets.
# 30 points ≈ $0.30 on XAUUSD with standard 5-digit broker.
SLIPPAGE_POINTS      = int(os.getenv("SLIPPAGE_POINTS",        "30"))

# ── Wyckoff Calibration (set at runtime from live candles) ───────────────────
WYCKOFF_MAX_RANGE_PCT = 0.01163
WYCKOFF_SPRING_MARGIN = 2.06

# ── Redis IPC — cross-service state sharing on Render ─────────────────────────
# Set to the Render Redis Internal URL (e.g. redis://red-xxxx:6379).
# Without this, the robot and Telegram panel use file-based IPC, which does NOT
# work across separate Render services (they have separate filesystems).
# Add REDIS_URL to both the robot and panel service environment variables in
# render.yaml or the Render dashboard.
REDIS_URL = os.getenv("REDIS_URL", "")
