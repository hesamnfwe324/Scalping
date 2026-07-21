"""
Trading Handler — position and order management.
"""

import logging
from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler
from .base import BaseHandler
from ..keyboards.inline import Keyboards
from ..formatters.messages import MessageFormatter

logger = logging.getLogger(__name__)

# States for entering values
ASK_LOTS, ASK_PRICE, ASK_TRAIL_DIST = range(3)


class TradingHandler(BaseHandler):
    def __init__(
        self,
        trade_service,
        auth_middleware,
        formatter: MessageFormatter,
    ) -> None:
        self._trades = trade_service
        self._auth = auth_middleware
        self._fmt = formatter

    async def show_trading(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        ok, user = await self._auth.check_permission(update, "can_view_dashboard")
        if not ok:
            return
        await self.edit_or_reply(
            update, context,
            "💹 <b>TRADE MANAGEMENT</b>\n\n"
            "Select an option below to manage open positions and orders.",
            Keyboards.trading_menu(),
        )

    async def show_positions(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        ok, _ = await self._auth.check_permission(update, "can_view_dashboard")
        if not ok:
            return
        positions = await self._trades.get_open_positions()
        text = self._fmt.positions_list(positions)
        await self.edit_or_reply(update, context, text, Keyboards.positions_list(positions))

    async def show_position_detail(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE, ticket: int
    ) -> None:
        ok, _ = await self._auth.check_permission(update, "can_view_dashboard")
        if not ok:
            return
        positions = await self._trades.get_open_positions()
        pos = next((p for p in positions if p.ticket == ticket), None)
        if not pos:
            await self.answer_callback(update, "Position not found", show_alert=True)
            return
        text = self._fmt.position_detail(pos)
        await self.edit_or_reply(update, context, text, Keyboards.position_detail(ticket))

    async def close_position_confirm(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE, ticket: int
    ) -> None:
        ok, _ = await self._auth.check_permission(update, "can_manage_trades")
        if not ok:
            return
        await self.edit_or_reply(
            update, context,
            f"⚠️ Close position <b>#{ticket}</b>?\n\nThis will immediately close the trade at market price.",
            Keyboards.confirm_cancel(
                f"trading:close_confirmed:{ticket}",
                f"trading:position_detail:{ticket}",
            ),
        )

    async def close_position(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE, ticket: int
    ) -> None:
        ok, user = await self._auth.check_permission(update, "can_manage_trades")
        if not ok:
            return
        result = await self._trades.close_position(ticket)
        success = result.get("success", False)
        await self._auth.record_action(
            user, "TRADE_CLOSE", f"Closed position #{ticket}", success=success
        )
        await self.answer_callback(
            update, "✅ Close order sent" if success else "❌ Failed to close", show_alert=True
        )
        await self.show_positions(update, context)

    async def set_breakeven(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE, ticket: int
    ) -> None:
        ok, user = await self._auth.check_permission(update, "can_manage_trades")
        if not ok:
            return
        result = await self._trades.set_breakeven(ticket)
        success = result.get("success", False)
        await self._auth.record_action(
            user, "TRADE_BREAKEVEN", f"Set BE on #{ticket}", success=success
        )
        await self.answer_callback(
            update, "✅ Break even set" if success else "❌ Failed", show_alert=True
        )

    async def close_all_confirm(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE, close_type: str = "all"
    ) -> None:
        ok, _ = await self._auth.check_permission(update, "can_manage_trades")
        if not ok:
            return
        labels = {
            "all": "ALL positions",
            "buy": "all BUY positions",
            "sell": "all SELL positions",
            "profit": "all PROFITABLE positions",
            "loss": "all LOSING positions",
        }
        label = labels.get(close_type, "positions")
        await self.edit_or_reply(
            update, context,
            f"🚨 <b>Close {label}?</b>\n\nThis will close all matching trades at market price.",
            Keyboards.confirm_cancel(
                f"trading:close_{close_type}_confirmed",
                "trading:menu",
            ),
        )

    async def close_bulk(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE, close_type: str
    ) -> None:
        ok, user = await self._auth.check_permission(update, "can_manage_trades")
        if not ok:
            return
        fn_map = {
            "all": self._trades.close_all,
            "buy": self._trades.close_buy,
            "sell": self._trades.close_sell,
            "profit": self._trades.close_profitable,
            "loss": self._trades.close_losing,
        }
        fn = fn_map.get(close_type)
        result = await fn() if fn else {"success": False}
        success = result.get("success", False)
        await self._auth.record_action(
            user, f"TRADE_CLOSE_{close_type.upper()}", f"Bulk close: {close_type}", success=success
        )
        await self.answer_callback(
            update, "✅ Command sent" if success else "❌ Failed", show_alert=True
        )
        await self.show_positions(update, context)

    async def show_pending(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        ok, _ = await self._auth.check_permission(update, "can_view_dashboard")
        if not ok:
            return
        orders = await self._trades.get_pending_orders()
        if not orders:
            text = "⏳ <b>PENDING ORDERS</b>\n\nNo pending orders."
        else:
            lines = [f"⏳ <b>PENDING ORDERS ({len(orders)})</b>"]
            for o in orders:
                lines.append(
                    f"\n{o.type_icon} <b>#{o.ticket}</b> {o.symbol}\n"
                    f"  📦 {o.volume}L @ {o.open_price:.5f}\n"
                    f"  🛑 SL: {o.stop_loss or '—'}  🎯 TP: {o.take_profit or '—'}"
                )
            text = "\n".join(lines)
        await self.edit_or_reply(
            update, context, text, Keyboards.back_only("trading:menu")
        )
