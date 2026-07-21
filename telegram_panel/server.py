"""
Render free-tier web service wrapper — Telegram Control Panel.
Runs a /health HTTP endpoint on $PORT alongside the Telegram bot.
Ping /health every 14 min (e.g. UptimeRobot free) to keep awake.
"""
import asyncio
import os
import sys

_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _root not in sys.path:
    sys.path.insert(0, _root)

from aiohttp import web

PORT = int(os.environ.get("PORT", 8081))


async def _health(_req: web.Request) -> web.Response:
    return web.Response(text="OK", content_type="text/plain")


async def _run_health_server() -> None:
    app = web.Application()
    app.router.add_get("/", _health)
    app.router.add_get("/health", _health)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()
    print(f"[health] Listening on 0.0.0.0:{PORT}", flush=True)
    while True:
        await asyncio.sleep(3600)


async def _run_panel() -> None:
    from telegram_panel.main import TelegramPanel
    panel = TelegramPanel()
    await panel.run()


async def _main() -> None:
    await asyncio.gather(_run_health_server(), _run_panel())


if __name__ == "__main__":
    try:
        asyncio.run(_main())
    except KeyboardInterrupt:
        print("[server] Shutting down.", flush=True)
