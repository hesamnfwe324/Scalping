"""
State Writer — writes robot_state.json and robot_mt5_snapshot.json
so the Telegram Control Panel can display live status and take commands.
"""
import json
import os
from datetime import datetime, timezone
from typing import List, Optional
from live_trading.signals.decision_engine import DecisionResult
from live_trading.logger import get_logger

# Import env-configured paths from config so that STATE_FILE, MT5_SNAPSHOT,
# and COMMANDS_FILE env-var overrides are honoured here as well as in live_loop.
# config.py has no imports that could cause circular dependency.
from live_trading.config import (
    STATE_FILE    as _CFG_STATE_FILE,
    MT5_SNAPSHOT  as _CFG_SNAPSHOT_FILE,
    COMMANDS_FILE as _CFG_COMMANDS_FILE,
)

log = get_logger()

STATE_FILE    = _CFG_STATE_FILE
SNAPSHOT_FILE = _CFG_SNAPSHOT_FILE
COMMANDS_FILE = _CFG_COMMANDS_FILE

# Track last N trade log entries in state
MAX_TRADE_HISTORY = 50

# Maximum age (in seconds) for a queued command before it is considered stale.
# Prevents commands that were issued before a crash from replaying on restart.
_COMMAND_MAX_AGE_SECONDS = int(os.getenv("COMMAND_MAX_AGE_SECONDS", "300"))

# Explicit mapping from Telegram panel command names to engine dict keys.
# Panel commands not present in this table are silently ignored.
_PANEL_COMMAND_MAP: dict = {
    "PAUSE":          "pause",
    "RESUME":         "resume",
    "EMERGENCY_STOP": "stop",
    "SAFE_SHUTDOWN":  "stop",
    "CLOSE_ALL":      "close_all",
    "RESET_GUARDIAN": "reset_guardian",
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _safe_write(path: str, data: dict) -> None:
    tmp = path + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, default=str)
        os.replace(tmp, path)
    except Exception as exc:
        log.error(f"State write failed ({path}): {exc}")


# ── Write robot_state.json ────────────────────────────────────────────────────

def write_robot_state(
    status:            str,        # "RUNNING", "PAUSED", "WAITING", "SCANNING"
    decision:          Optional[DecisionResult],
    open_position:     Optional[dict],
    account_info:      dict,
    trade_history:     List[dict],
    loop_count:        int,
    last_signal_time:  Optional[str] = None,
    extra:             Optional[dict] = None,
) -> None:

    pos_data = None
    if open_position:
        pos_data = {
            "ticket":    open_position.get("ticket"),
            "symbol":    open_position.get("symbol"),
            "direction": open_position.get("direction"),
            "lot_size":  open_position.get("lot_size"),
            "entry":     open_position.get("price_open"),
            "sl":        open_position.get("sl"),
            "tp":        open_position.get("tp"),
            "profit":    open_position.get("profit"),
            "open_time": open_position.get("time_str"),
        }

    dec_data = None
    if decision:
        dec_data = {
            "allowed":    decision.allowed,
            "direction":  decision.direction,
            "confidence": decision.confidence,
            "grade":      decision.grade,
            "regime":     decision.regime,
            "regime_label": decision.regime_label,
            "reasoning":  decision.reasoning[:8],
            "blocked_reasons": decision.blocked_reasons,
            "components": {
                "smc":        decision.components.smc_score,
                "trend":      decision.components.trend_score,
                "pa":         decision.components.pa_score,
                "wyckoff":    decision.components.wyckoff_score,
                "liquidity":  decision.components.liquidity_score,
                "volatility": decision.components.volatility_score,
                "total":      decision.components.total,
            },
            "trade_params": {
                "entry":  decision.trade_params.entry_price,
                "sl":     decision.trade_params.stop_loss,
                "tp":     decision.trade_params.take_profit,
                "lot":    decision.trade_params.lot_size,
                "rr":     decision.trade_params.risk_reward_ratio,
                "risk_usd": decision.trade_params.risk_amount,
            } if decision.trade_params else None,
        }

    state = {
        "status":           status,
        "last_update":      _now_iso(),
        "last_signal_time": last_signal_time,
        "loop_count":       loop_count,
        "account": {
            "balance":     account_info.get("balance", 0),
            "equity":      account_info.get("equity", 0),
            "profit":      account_info.get("profit", 0),
            "margin_free": account_info.get("margin_free", 0),
            "currency":    account_info.get("currency", "USD"),
        },
        "open_position":    pos_data,
        "last_decision":    dec_data,
        "recent_trades":    trade_history[-MAX_TRADE_HISTORY:],
        "trade_count":      len(trade_history),
    }
    if extra:
        state.update(extra)

    _safe_write(STATE_FILE, state)


# ── Write robot_mt5_snapshot.json ─────────────────────────────────────────────

def write_mt5_snapshot(
    candle_time: str,
    price:       float,
    regime:      str,
    adx:         float,
    atr:         float,
    smc_signal:  str,
    trend:       str,
) -> None:
    snap = {
        "timestamp":   _now_iso(),
        "candle_time": candle_time,
        "price":       price,
        "regime":      regime,
        "adx":         round(adx, 1),
        "atr":         round(atr, 4),
        "smc_signal":  smc_signal,
        "trend":       trend,
    }
    _safe_write(SNAPSHOT_FILE, snap)


# ── Read robot_commands.json ──────────────────────────────────────────────────

def read_commands() -> dict:
    """Read commands written by Telegram panel.  Returns {} if none.

    Supports two on-disk formats:
      • Dict format (legacy / future): ``{"pause": true, ...}`` — returned as-is.
      • List format (current panel):   ``[{"command": "PAUSE", "issued_at": "..."}]``
        — translated to engine dict keys; unknown commands and stale entries
        are silently discarded.

    Invalid or corrupted files always return {} without raising.
    """
    try:
        if not os.path.exists(COMMANDS_FILE):
            return {}
        with open(COMMANDS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return {}

    # ── Dict format — backward-compatible pass-through ────────────────────────
    if isinstance(data, dict):
        return data

    # ── List format — translate to engine dict keys ───────────────────────────
    if not isinstance(data, list):
        return {}

    now = datetime.now(timezone.utc)
    result: dict = {}

    for item in data:
        if not isinstance(item, dict):
            continue

        # Stale-command check — discard anything older than the age threshold
        issued_at_str = item.get("issued_at")
        if issued_at_str:
            try:
                issued_at = datetime.fromisoformat(issued_at_str)
                # Normalise naive timestamps to UTC (panel writes UTC without tz)
                if issued_at.tzinfo is None:
                    issued_at = issued_at.replace(tzinfo=timezone.utc)
                age_seconds = (now - issued_at).total_seconds()
                if age_seconds > _COMMAND_MAX_AGE_SECONDS:
                    log.warning(
                        f"Discarding stale command '{item.get('command')}' "
                        f"(age={age_seconds:.0f}s > {_COMMAND_MAX_AGE_SECONDS}s)"
                    )
                    continue
            except Exception:
                # Unparseable timestamp — process the command rather than silently drop it
                pass

        # Translate panel command name → engine dict key
        cmd_name   = str(item.get("command", "")).strip().upper()
        engine_key = _PANEL_COMMAND_MAP.get(cmd_name)
        if engine_key:
            result[engine_key] = True

    return result


def clear_command(key: str) -> None:
    cmds = read_commands()
    if key in cmds:
        del cmds[key]
        _safe_write(COMMANDS_FILE, cmds)


def log_trade(trade_history: List[dict], entry: dict) -> None:
    entry["logged_at"] = _now_iso()
    trade_history.append(entry)
    if len(trade_history) > MAX_TRADE_HISTORY:
        trade_history[:] = trade_history[-MAX_TRADE_HISTORY:]
