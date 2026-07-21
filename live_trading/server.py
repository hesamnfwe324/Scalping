"""
    Render web-service wrapper — GoldScalperPro v4 Live Trading Engine.

    Design:
    • The aiohttp health server starts first and runs FOREVER — Render always
      sees a healthy process.  The service is never restarted by Render;
      the robot loop restarts internally with exponential backoff.
    • The robot is restarted in-process on any failure (connection drop,
      exception, or clean exit).  Backoff starts at 30 s and caps at 5 min.

    Ping /health every 14 min (e.g. UptimeRobot free) to keep the free-tier
    Render service warm and prevent the 15-minute sleep window.
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

    # ── Robot restart backoff ─────────────────────────────────────────────────────
    _BACKOFF_BASE    = 30   # first-failure wait (seconds)
    _BACKOFF_MAX     = 300  # cap (5 minutes)
    _backoff_seconds = _BACKOFF_BASE


    def _reset_backoff() -> None:
      global _backoff_seconds
      _backoff_seconds = _BACKOFF_BASE


    def _next_backoff() -> int:
      global _backoff_seconds
      wait = _backoff_seconds
      _backoff_seconds = min(_backoff_seconds * 2, _BACKOFF_MAX)
      return wait


    # ── Health state ──────────────────────────────────────────────────────────────
    _robot_status: str = "STARTING"


    async def _health(_req: web.Request) -> web.Response:
      return web.Response(
          text=f"OK\nrobot_status={_robot_status}",
          content_type="text/plain",
      )


    async def _run_health_server() -> None:
      app = web.Application()
      app.router.add_get("/", _health)
      app.router.add_get("/health", _health)
      runner = web.AppRunner(app)
      await runner.setup()
      site = web.TCPSite(runner, "0.0.0.0", PORT)
      await site.start()
      print(f"[health] Listening on 0.0.0.0:{PORT}", flush=True)
      # Run forever — this coroutine never returns.
      while True:
          await asyncio.sleep(3600)


    # ── Robot loop (restartable) ──────────────────────────────────────────────────

    async def _run_robot_once() -> None:
      """
      Run one attempt of the trading engine.  Raises on failure so the outer
      supervisor can log and schedule a restart.
      """
      global _robot_status

      from live_trading.config import MTAPI_URL, MT5_USER, MT5_PASSWORD
      from live_trading.logger import get_logger
      from live_trading.trading.live_loop import GoldScalperLive

      log = get_logger()

      missing = [v for v, val in [("MT5_USER", MT5_USER), ("MT5_PASSWORD", MT5_PASSWORD), ("MTAPI_URL", MTAPI_URL)] if not val]
      if missing:
          for var in missing:
              log.error(f"Required env var {var!r} is not set.")
          _robot_status = "CONFIG_ERROR"
          raise RuntimeError(f"Missing env vars: {', '.join(missing)}")

      log.info(f"MTAPI_URL  : {MTAPI_URL}")
      log.info(f"MT5 user   : {MT5_USER}")
      log.info("Starting GoldScalperPro v4 trading engine …")
      _robot_status = "CONNECTING"

      engine = GoldScalperLive()
      connected = await engine.start()

      if connected is False:
          _robot_status = "DISCONNECTED"
          raise RuntimeError("Engine.start() returned False — MT5 connection failed.")

      # start() returned a truthy value only if the trading loop exited cleanly
      _robot_status = "STOPPED"


    async def _robot_supervisor() -> None:
      """
      Continuously run the robot, restarting with exponential backoff on failure.
      This coroutine never returns.
      """
      global _robot_status
      attempt = 0
      while True:
          attempt += 1
          print(f"[supervisor] Robot attempt #{attempt} …", flush=True)
          try:
              await _run_robot_once()
              # Clean exit (unusual — the engine loop runs indefinitely)
              print("[supervisor] Robot exited cleanly.", flush=True)
              _reset_backoff()
          except Exception as exc:
              wait = _next_backoff()
              print(
                  f"[supervisor] Robot failed: {exc}. "
                  f"Restarting in {wait}s …",
                  flush=True,
              )
              _robot_status = f"RETRYING_IN_{wait}s"
              await asyncio.sleep(wait)


    async def _main() -> None:
      # Start health server first — it must be accepting connections before
      # Render's health-check fires.  asyncio.create_task schedules it to run
      # on the event loop; the await below yields control so the server can
      # bind its socket before we start the robot.
      health_task = asyncio.create_task(_run_health_server())
      await asyncio.sleep(0.5)   # let the health server bind
      print("[server] Health server ready.", flush=True)

      # Run the supervisor as a second task.  Both tasks run concurrently and
      # neither returns, so _main() itself never returns either.
      supervisor_task = asyncio.create_task(_robot_supervisor())
      await asyncio.gather(health_task, supervisor_task)


    if __name__ == "__main__":
      try:
          asyncio.run(_main())
      except KeyboardInterrupt:
          print("[server] Shutting down.", flush=True)
    