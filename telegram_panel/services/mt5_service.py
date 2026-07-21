"""
MT5 Service — interface to MetaTrader 5 account data.

Reads live account and position data from MT5 via:
  - Python MetaTrader5 library (if available and on Windows/Wine)
  - JSON state files written by the robot (default, cross-platform)
  - Mock data for testing without an MT5 connection

The robot engine is the authoritative source of live MT5 data.
This service reads the account snapshot file the robot maintains.
"""

import os
import json
import asyncio
import logging
from datetime import datetime
from typing import Optional, Any
from ..config.constants import ConnectionStatus, TradeDirection, TradeStatus
from ..models.account import Account
from ..models.trade import Trade, Position, PendingOrder

logger = logging.getLogger(__name__)


class MT5Service:
    """
    Reads live MT5 data from the account snapshot file.
    Falls back to stub data gracefully — never raises to callers.
    """

    def __init__(self, snapshot_path: str = "robot_mt5_snapshot.json") -> None:
        self._snapshot_path = snapshot_path
        self._cache: dict[str, Any] = {}
        self._cache_ts: Optional[float] = None
        self._cache_ttl: float = 3.0

    async def get_account_info(self, account: Account) -> dict[str, Any]:
        """Return live balance/equity/margin from MT5 snapshot."""
        snapshot = await self._read_snapshot()
        info = snapshot.get("account_info", {})
        return {
            "balance": info.get("balance", account.balance),
            "equity": info.get("equity", account.equity),
            "margin": info.get("margin", account.margin),
            "free_margin": info.get("free_margin", account.free_margin),
            "margin_level": info.get("margin_level", account.margin_level),
            "floating_profit": info.get("floating_profit", account.floating_profit),
            "currency": info.get("currency", account.currency),
            "leverage": info.get("leverage", account.leverage),
            "broker": info.get("broker", account.broker),
            "server": info.get("server", account.server),
            "login": info.get("login", account.login),
            "connection_status": info.get("connection_status", "disconnected"),
        }

    async def get_open_positions(self) -> list[Position]:
        snapshot = await self._read_snapshot()
        positions_raw = snapshot.get("open_positions", [])
        positions = []
        for raw in positions_raw:
            try:
                pos = Position(
                    ticket=raw.get("ticket", 0),
                    symbol=raw.get("symbol", "XAUUSD"),
                    direction=TradeDirection(raw.get("type", "BUY")),
                    volume=raw.get("volume", 0.01),
                    open_price=raw.get("open_price", 0.0),
                    current_price=raw.get("current_price", 0.0),
                    stop_loss=raw.get("sl"),
                    take_profit=raw.get("tp"),
                    open_time=datetime.fromisoformat(raw["open_time"])
                        if raw.get("open_time") else datetime.utcnow(),
                    profit=raw.get("profit", 0.0),
                    commission=raw.get("commission", 0.0),
                    swap=raw.get("swap", 0.0),
                    status=TradeStatus.OPEN,
                    comment=raw.get("comment"),
                    magic=raw.get("magic", 0),
                    floating_profit=raw.get("profit", 0.0),
                    breakeven_activated=raw.get("be_done", False),
                    trailing_stop_active=raw.get("trail_active", False),
                )
                positions.append(pos)
            except Exception as e:
                logger.warning(f"Failed to parse position: {e}")
        return positions

    async def get_pending_orders(self) -> list[PendingOrder]:
        snapshot = await self._read_snapshot()
        orders_raw = snapshot.get("pending_orders", [])
        orders = []
        for raw in orders_raw:
            try:
                order = PendingOrder(
                    ticket=raw.get("ticket", 0),
                    symbol=raw.get("symbol", "XAUUSD"),
                    order_type=raw.get("order_type", "BUY_LIMIT"),
                    volume=raw.get("volume", 0.01),
                    open_price=raw.get("price", 0.0),
                    stop_loss=raw.get("sl"),
                    take_profit=raw.get("tp"),
                    placed_at=datetime.fromisoformat(raw["placed_at"])
                        if raw.get("placed_at") else datetime.utcnow(),
                    comment=raw.get("comment"),
                    magic=raw.get("magic", 0),
                )
                orders.append(order)
            except Exception as e:
                logger.warning(f"Failed to parse pending order: {e}")
        return orders

    async def get_connection_status(self) -> ConnectionStatus:
        snapshot = await self._read_snapshot()
        raw = snapshot.get("connection_status", "disconnected")
        try:
            return ConnectionStatus(raw)
        except ValueError:
            return ConnectionStatus.DISCONNECTED

    async def get_today_profit(self) -> float:
        snapshot = await self._read_snapshot()
        return snapshot.get("today_profit", 0.0)

    async def get_floating_profit(self) -> float:
        snapshot = await self._read_snapshot()
        return snapshot.get("floating_profit", 0.0)

    async def get_drawdown(self) -> dict[str, float]:
        snapshot = await self._read_snapshot()
        dd = snapshot.get("drawdown", {})
        return {
            "current": dd.get("current", 0.0),
            "max": dd.get("max", 0.0),
            "current_percent": dd.get("current_percent", 0.0),
            "max_percent": dd.get("max_percent", 0.0),
        }

    async def send_trade_command(self, command: str, params: dict[str, Any]) -> dict[str, Any]:
        """
        Write a trade command to the MT5 command queue file.
        The robot engine processes these on next tick.
        """
        cmd_path = self._snapshot_path.replace("snapshot", "trade_commands")
        cmd = {"command": command, "params": params, "issued_at": datetime.utcnow().isoformat()}
        try:
            loop = asyncio.get_event_loop()
            def _write():
                existing = []
                if os.path.exists(cmd_path):
                    try:
                        with open(cmd_path) as f:
                            existing = json.load(f)
                    except Exception:
                        existing = []
                existing.append(cmd)
                with open(cmd_path, "w") as f:
                    json.dump(existing, f)
            await loop.run_in_executor(None, _write)
            return {"success": True}
        except Exception as e:
            logger.error(f"Trade command failed: {e}")
            return {"success": False, "error": str(e)}

    async def _read_snapshot(self) -> dict[str, Any]:
        now = asyncio.get_event_loop().time()
        if self._cache_ts and (now - self._cache_ts) < self._cache_ttl:
            return self._cache

        if not os.path.exists(self._snapshot_path):
            return {}
        try:
            loop = asyncio.get_event_loop()
            def _read():
                with open(self._snapshot_path) as f:
                    return json.load(f)
            data = await loop.run_in_executor(None, _read)
            self._cache = data
            self._cache_ts = now
            return data
        except Exception as e:
            logger.warning(f"Failed to read MT5 snapshot: {e}")
            return {}
