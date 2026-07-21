"""
    Render web-service wrapper — GoldScalperPro v4 Live Trading Engine.

    Design:
    * Health server starts first and runs FOREVER — Render always sees a
      healthy service.  The process never exits.
    * Robot loop restarts internally on any failure with exponential backoff.
    * reuse_port=True lets the health server bind even during rolling deploys.

    Ping /health every 14 min (UptimeRobot free) to keep the free-tier service warm.
    """
    import asyncio
    import os
    import sys
    import traceback

    _root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if _root not in sys.path:
      sys.path.insert(0, _root)

    from aiohttp import web

    PORT = int(os.environ.get("PORT", 10000))

    # ── Robot restart backoff ─────────────────────────────────────────────────────
    _BACKOFF_BASE = 30    # seconds — first-failure wait
    _BACKOFF_MAX  = 300   # seconds — cap (5 minutes)
    _backoff      = _BACKOFF_BASE

    _robot_status = "STARTING"


    # ── Health endpoint ───────────────────────────────────────────────────────────

    async def _health(_req: web.Request) -> web.Response:
      return web.Response(text=f"OK status={_robot_status}", content_type="text/plain")


    async def _run_health_server() -> None:
      """Start the aiohttp health server and keep it running forever."""
      app = web.Application()
      app.router.add_get("/", _health)
      app.router.add_get("/health", _health)
      runner = web.AppRunner(app)
      await runner.setup()
      site = web.TCPSite(runner, "0.0.0.0", PORT, reuse_port=True)
      await site.start()
      print(f"[health] Listening on 0.0.0.0:{PORT}", flush=True)
      while True:
          await asyncio.sleep(60)


    # ── Robot supervisor ──────────────────────────────────────────────────────────

    async def _run_robot_once() -> None:
      global _robot_status
      from live_trading.config import MTAPI_URL, MT5_USER, MT5_PASSWORD
      from live_trading.logger import get_logger
      from live_trading.trading.live_loop import GoldScalperLive

      log = get_logger()
      missing = [v for v, val in [
          ("MT5_USER", MT5_USER),
          ("MT5_PASSWORD", MT5_PASSWORD),
          ("MTAPI_URL", MTAPI_URL),
      ] if not val]
      if missing:
          msg = f"Missing required env vars: {', '.join(missing)}"
          print(f"[robot] {msg}", flush=True)
          _robot_status = "CONFIG_ERROR"
          raise RuntimeError(msg)

      print(f"[robot] MTAPI_URL={MTAPI_URL}  MT5_USER={MT5_USER}", flush=True)
      _robot_status = "CONNECTING"
      engine = GoldScalperLive()
      result = await engine.start()
      if result is False:
          _robot_status = "DISCONNECTED"
          raise RuntimeError("engine.start() returned False — MT5 connection failed")
      _robot_status = "STOPPED"


    async def _robot_supervisor() -> None:
      global _backoff, _robot_status
      attempt = 0
      while True:
          attempt += 1
          print(f"[supervisor] Starting robot attempt #{attempt} …", flush=True)
          try:
              await _run_robot_once()
              print("[supervisor] Robot exited cleanly — scheduling restart.", flush=True)
              _backoff = _BACKOFF_BASE     # reset on clean exit
          except Exception:
              wait = min(_backoff, _BACKOFF_MAX)
              _backoff = min(_backoff * 2, _BACKOFF_MAX)
              _robot_status = f"RETRY_IN_{wait}s"
              print(
                  f"[supervisor] Robot error (attempt #{attempt}), retrying in {wait}s:",
                  flush=True,
              )
              traceback.print_exc()
              await asyncio.sleep(wait)
          else:
              await asyncio.sleep(_BACKOFF_BASE)


    # ── Entry point ───────────────────────────────────────────────────────────────

    async def _main() -> None:
      print(f"[server] Python {sys.version}  PORT={PORT}", flush=True)
      # Create both tasks — they run concurrently and neither should return.
      health = asyncio.create_task(_run_health_server())
      # Give the health server a moment to bind before loading the trading engine.
      await asyncio.sleep(1)
      supervisor = asyncio.create_task(_robot_supervisor())
      # Await both; propagate the first exception (should never happen).
      await asyncio.gather(health, supervisor)


    if __name__ == "__main__":
      try:
          asyncio.run(_main())
      except KeyboardInterrupt:
          print("[server] Keyboard interrupt — shutting down.", flush=True)
    