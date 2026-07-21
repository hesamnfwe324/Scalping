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
    # Start the health server as a background task first so that Render's
    # health check can respond while the panel is initialising or if the
    # panel exits early due to missing configuration.  The 1-second sleep
    # gives the TCP server time to bind before the panel starts.
    health_task = asyncio.create_task(_run_health_server())
    await asyncio.sleep(1)

    try:
        await _run_panel()
    except SystemExit:
        # Re-raise so Render sees a non-zero exit code and restarts the
        # service automatically according to its restart policy.
        raise
    except Exception as exc:
        print(f"[server] Unhandled panel exception: {exc}", flush=True)
        sys.exit(1)
    finally:
        health_task.cancel()
        try:
            await health_task
        except asyncio.CancelledError:
            pass


if __name__ == "__main__":
    try:
        asyncio.run(_main())
    except KeyboardInterrupt:
        print("[server] Shutting down.", flush=True)
