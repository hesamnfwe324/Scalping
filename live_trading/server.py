"""
Render free-tier web service wrapper — Live Trading Engine.
Runs a /health HTTP endpoint on $PORT alongside the trading engine.
Ping /health every 14 min (e.g. UptimeRobot free) to keep awake.
"""
import asyncio
import os
import sys

if sys.version_info < (3, 11):
    print(f"ERROR: Python 3.11+ required. Got {sys.version_info.major}.{sys.version_info.minor}.")
    sys.exit(1)

_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _root not in sys.path:
    sys.path.insert(0, _root)

from aiohttp import web

PORT = int(os.environ.get("PORT", 8080))


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


async def _run_robot() -> None:
    from live_trading.config import METAAPI_TOKEN, METAAPI_ACCOUNT_ID
    from live_trading.logger import get_logger
    from live_trading.trading.live_loop import GoldScalperLive

    log = get_logger()
    if not METAAPI_TOKEN or not METAAPI_ACCOUNT_ID:
        log.error("METAAPI_TOKEN and METAAPI_ACCOUNT_ID must be set.")
        sys.exit(1)
    log.info("Starting GoldScalperPro Live Trading Engine...")
    engine = GoldScalperLive()
    connected = await engine.start()
    if connected is False:
        log.error("Engine failed — exiting so Render restarts automatically.")
        sys.exit(1)


async def _main() -> None:
    # Start the health server as a background task first so that Render's
    # health check can respond while the trading engine is initialising
    # (MetaAPI sync can take 30-120 s) or if the engine exits due to a
    # bad configuration.  The 1-second sleep gives the TCP server time to
    # bind before the robot starts.
    health_task = asyncio.create_task(_run_health_server())
    await asyncio.sleep(1)

    try:
        await _run_robot()
    except SystemExit:
        # Re-raise so Render sees a non-zero exit code and restarts the
        # service automatically according to its restart policy.
        raise
    except Exception as exc:
        print(f"[server] Unhandled robot exception: {exc}", flush=True)
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
