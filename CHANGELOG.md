# Changelog

All notable changes to GoldScalperPro are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

**Strategy freeze notice:** No entry in this changelog modifies trading signals,
entries, exits, confidence scores, risk thresholds, position sizing, or any
metric that affects trading behaviour. Strategy is frozen at v4 Stable.

---

## [4.0.2] — 2026-07-19 — Production Blocker Resolution

### Fixed — Live Trading Engine

- **[FIX-01] Dependency pinning** (`live_trading/requirements.txt`)
  - All three dependencies pinned to exact versions:
    `metaapi-cloud-sdk==27.0.2`, `aiohttp==3.9.5`, `aiofiles==23.2.1`
  - Prevents silent breakage from upstream breaking changes in metaapi-cloud-sdk
  - _Why unchanged:_ Packaging only — no code paths affected

- **[FIX-02] Log rotation** (`live_trading/logger.py`)
  - Replaced `FileHandler` with `RotatingFileHandler` (10 MB × 5 backups)
  - Prevents `robot.log` growing indefinitely on long deployments
  - File handler creation failure now prints a warning to stderr instead of passing silently
  - _Why unchanged:_ Logging only — no trading logic reads the log file

- **[FIX-03] Non-zero exit on MetaAPI connection failure** (`live_trading/main.py`, `live_trading/trading/live_loop.py`)
  - `start()` now returns `False` on connection failure; `main()` calls `sys.exit(1)`
  - Cloud process managers (Render, systemd) will now auto-restart on auth failures
  - _Why unchanged:_ Exit code change only — trading loop is not entered on failure

- **[FIX-04] Python version guard raised to 3.11** (`live_trading/main.py`)
  - Previous guard allowed Python 3.10, which lacks asyncio stability needed for production
  - Now exits with clear message if Python < 3.11
  - _Why unchanged:_ Startup-only check — no trading path reached before this check

- **[FIX-05] Candle deduplication** (`live_trading/mt5/connector.py`)
  - Added deduplication by time key after sorting in `fetch_candles()`
  - Removes duplicate bars that MetaAPI SDK may return, preventing indicator shift
  - Logs a warning when duplicates are detected
  - _Why unchanged:_ Duplicate candles carry identical OHLCV data — removing them
    produces the same unique candle sequence that would have been present without the
    SDK bug. No new decisions are added or removed.

- **[FIX-06] Disconnect exception logged** (`live_trading/mt5/connector.py`)
  - `disconnect()` now logs exception from `_connection.close()` at WARNING level
    instead of silently swallowing it
  - _Why unchanged:_ Logging only — no trading path affected

- **[FIX-07] Complete `.env.example`** (`live_trading/.env.example`)
  - Created comprehensive environment variable template for live trading engine
  - Includes all Guardian circuit breaker variables with explanatory comments
  - _Why unchanged:_ Documentation file only

### Fixed — Telegram Panel

- **[FIX-08] Dependency pinning** (`telegram_panel/requirements.txt`)
  - Added missing `APScheduler==3.10.4` (required by `python-telegram-bot[job-queue]`)
  - All dependencies now at exact versions
  - _Why unchanged:_ Packaging only

- **[FIX-09] Encryption key enforcement** (`telegram_panel/config/settings.py`)
  - `validate()` now returns an error if `PANEL_ENCRYPTION_KEY` is missing or malformed
  - Panel refuses to start without a valid Fernet key
  - Also validates key format (must be valid 32-byte URL-safe base64)
  - _Why unchanged:_ Panel startup validation only — the trading engine has no dependency
    on the panel's encryption service

- **[FIX-10] Shutdown double-call guard** (`telegram_panel/main.py`)
  - Added `self._shutdown_called` flag to prevent double-call from signal handler + finally block
  - Replaced deprecated `asyncio.get_event_loop().stop()` with `asyncio.get_running_loop().stop()`
  - Python 3.12 compatible — no DeprecationWarning on shutdown
  - _Why unchanged:_ Panel lifecycle only — trading engine is a separate process

- **[FIX-11] Audit log sensitive field masking** (`telegram_panel/security/audit.py`)
  - Added `_mask_if_sensitive()` utility and `_SENSITIVE_FIELD_NAMES` constant
  - Fields matching known credential names (password, token, key, etc.) are masked as
    `***MASKED***` in audit log target values
  - _Why unchanged:_ Audit logging only — no trading path affected

### Added

- **[ADD-01] Render panel service** (`render.yaml`)
  - Added Telegram panel as a second worker service in `render.yaml`
  - Added Guardian env vars: `DAILY_LOSS_LIMIT_PCT`, `MAX_DRAWDOWN_PCT`, `SLIPPAGE_POINTS`
  - Added filesystem persistence warnings and path configuration
  - _Why unchanged:_ Deployment configuration only

- **[ADD-02] Engineering test suite** (`tests/`)
  - `test_config_validation.py` — env var parsing for live_trading config
  - `test_state_persistence.py` — state file write/read/corruption handling
  - `test_settings_validation.py` — panel settings required field enforcement
  - `test_encryption.py` — encryption round-trip and key generation
  - `test_logger_setup.py` — RotatingFileHandler configuration
  - `test_connector_dedup.py` — candle deduplication logic
  - `test_audit_masking.py` — sensitive field masking
  - _Why unchanged:_ Test files never affect production execution

- **[ADD-03] Production documentation**
  - `README.md` — project overview, quick start, architecture
  - `LICENSE` — MIT License with risk disclaimer
  - `CHANGELOG.md` — this file
  - `audit_reports/DEPLOYMENT_GUIDE.md` — full deployment instructions
  - `audit_reports/OPERATIONS_GUIDE.md` — runbook for operators

### Not Fixed (require strategy modification or live test)

| ID | Issue | Reason |
|----|-------|--------|
| C-01 | Balance fallback 10,000 in `_on_new_bar` | Changes lot sizing in failure mode |
| C-02 | Double-entry on abrupt disconnect | Requires live test environment to verify |
| C-03 | Backtest uses synthetic data | Requires real XAUUSD historical CSV |
| H-07 | SMC hardcoded 20-bar lookback vs config 5 | Changes SMC signals |
| M-05 | Corrupted commands.json silently ignored | Changing return value affects command flow |
| M-06 | Guardian uses balance not equity | Intentional design; changing breaks Guardian |

---

## [4.0.1] — 2026-07-19 — Phase 1 Audit Fixes

### Fixed (9 fixes — full detail in REGRESSION_REPORT.md)

- TG-01: Database startup crash on bare filename paths
- TG-02: Settings startup crash on malformed env vars
- TG-04: EventBus silently swallowed subscriber exceptions
- TG-05: Deprecated `datetime.utcnow()` in session manager
- PY-04: State file paths not respecting env-var overrides
- PY-05: Misleading "REJECTED" grade for above-minimum confidence
- PY-06: Candle sort key TypeError on datetime-type time field
- PY-07: Direct access to private `_connection` variable
- PY-08: Undefined priority for simultaneous pause + resume commands

---

## [4.0.0] — 2026-07-19 — Initial Submission

Original GoldScalperPro v4 as submitted for independent audit.
