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

    # How long (seconds) to keep the health server alive after startup before
    # allowing the process to exit on a fatal error.  Render polls /health on a
    # schedule; 30 s ensures at least 2-3 successful responses so the deploy is
    # marked healthy before Render's restart policy takes over.
    _HEALTH_GRACE_SECONDS = 30


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
      from live_trading.config import MTAPI_URL, MT5_USER, MT5_PASSWORD
      from live_trading.logger import get_logger
      from live_trading.trading.live_loop import GoldScalperLive

      log = get_logger()

      missing = []
      if not MT5_USER:
          missing.append("MT5_USER")
      if not MT5_PASSWORD:
          missing.append("MT5_PASSWORD")
      if not MTAPI_URL:
          missing.append("MTAPI_URL")

      if missing:
          for var in missing:
              log.error(f"Environment variable {var} is not set.")
          log.error("Set the missing variables in the Render dashboard → Environment.")
          sys.exit(1)

      log.info(f"MTAPI_URL  : {MTAPI_URL}")
      log.info(f"MT5 user   : {MT5_USER}")
      log.info("Starting GoldScalperPro Live Trading Engine...")
      engine = GoldScalperLive()
      connected = await engine.start()
      if connected is False:
          log.error("Engine failed — exiting so Render restarts automatically.")
          sys.exit(1)


    async def _main() -> None:
      # Start the health server as a background task.  It must be able to
      # respond to Render's health check polling BEFORE we exit for any reason
      # (bad config, MT5 connection failure).  We hold the process alive for at
      # least _HEALTH_GRACE_SECONDS so Render records several successful checks
      # and marks the deploy healthy; its restart policy then handles re-launch.
      health_task = asyncio.create_task(_run_health_server())

      # Give the TCP server time to bind before anything else runs.
      await asyncio.sleep(1)
      print("[server] Health server ready. Starting trading engine...", flush=True)

      _exit_code = 0
      try:
          await _run_robot()
      except SystemExit as exc:
          _exit_code = exc.code if exc.code is not None else 1
      except Exception as exc:
          print(f"[server] Unhandled robot exception: {exc}", flush=True)
          _exit_code = 1

      if _exit_code != 0:
          elapsed = 1  # already slept 1 s above
          remaining = max(0, _HEALTH_GRACE_SECONDS - elapsed)
          print(
              f"[server] Engine exited (code {_exit_code}). "
              f"Keeping health server alive for {remaining}s before exit.",
              flush=True,
          )
          await asyncio.sleep(remaining)

      health_task.cancel()
      try:
          await health_task
      except asyncio.CancelledError:
          pass

      sys.exit(_exit_code)


    if __name__ == "__main__":
      try:
          asyncio.run(_main())
      except KeyboardInterrupt:
          print("[server] Shutting down.", flush=True)
    