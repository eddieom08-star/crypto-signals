"""Main bot loop for crypto signal scanner."""

import asyncio
import logging
import signal
import sys
from contextlib import asynccontextmanager
from datetime import datetime
from typing import AsyncGenerator

from aiohttp import web

from analyzer import SignalAnalyzer
from config import Config, WATCHLIST, load_config
from fetcher import DEXScreenerClient
from notifier import TelegramNotifier

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)


class CryptoSignalBot:
    """Main bot class for scanning and sending signals."""

    def __init__(self, config: Config) -> None:
        self._config = config
        self._fetcher = DEXScreenerClient(config)
        self._analyzer = SignalAnalyzer(config.scoring_weights)
        self._notifier = TelegramNotifier(config)
        self._running = False
        self._scan_count = 0
        self._signals_sent = 0
        self._last_scan: datetime | None = None
        self._errors_count = 0

    @property
    def status(self) -> dict:
        """Get bot status for health check."""
        return {
            "status": "running" if self._running else "stopped",
            "scan_count": self._scan_count,
            "signals_sent": self._signals_sent,
            "errors_count": self._errors_count,
            "last_scan": self._last_scan.isoformat() if self._last_scan else None,
            "watchlist_size": len(WATCHLIST),
        }

    async def start(self) -> None:
        """Start the bot main loop."""
        self._running = True
        logger.info("Starting Crypto Signal Bot...")

        # Send startup message
        await self._notifier.send_startup_message()

        while self._running:
            try:
                await self._scan_watchlist()
                self._last_scan = datetime.now()
                self._scan_count += 1

                if self._scan_count % 10 == 0:
                    logger.info(
                        f"Scan #{self._scan_count} complete. "
                        f"Signals sent: {self._signals_sent}"
                    )

            except Exception as e:
                self._errors_count += 1
                logger.error(f"Error during scan: {e}")

                if self._errors_count % 10 == 0:
                    await self._notifier.send_error_alert(
                        f"Multiple scan errors ({self._errors_count} total). "
                        f"Latest: {str(e)[:100]}"
                    )

            await asyncio.sleep(self._config.scan_interval_seconds)

    async def stop(self) -> None:
        """Stop the bot."""
        logger.info("Stopping Crypto Signal Bot...")
        self._running = False

    async def _scan_watchlist(self) -> None:
        """Scan all tokens in watchlist."""
        for symbol, token_config in WATCHLIST.items():
            try:
                # Fetch token data
                token_data = await self._fetcher.fetch_token_data(token_config)

                if not token_data:
                    logger.debug(f"No data available for {symbol}")
                    continue

                # Analyze signal
                signal = self._analyzer.analyze(token_data)

                logger.debug(
                    f"{symbol}: Score {signal.total_score}/100 "
                    f"(L:{signal.liquidity_score} V:{signal.volume_ratio_score} "
                    f"M:{signal.momentum_score} B:{signal.buy_pressure_score} "
                    f"T:{signal.trend_score})"
                )

                # Send alert if signal meets threshold
                if signal.total_score >= self._config.signal_threshold:
                    sent = await self._notifier.send_signal(signal)
                    if sent:
                        self._signals_sent += 1

                # Small delay between tokens to avoid rate limiting
                await asyncio.sleep(0.5)

            except Exception as e:
                logger.error(f"Error processing {symbol}: {e}")


class HealthCheckServer:
    """Simple HTTP server for health checks."""

    def __init__(self, bot: CryptoSignalBot, port: int) -> None:
        self._bot = bot
        self._port = port
        self._app = web.Application()
        self._app.router.add_get("/health", self._health_handler)
        self._app.router.add_get("/", self._health_handler)
        self._runner: web.AppRunner | None = None

    async def _health_handler(self, request: web.Request) -> web.Response:
        """Handle health check requests."""
        status = self._bot.status
        return web.json_response(status)

    async def start(self) -> None:
        """Start the health check server."""
        self._runner = web.AppRunner(self._app)
        await self._runner.setup()
        site = web.TCPSite(self._runner, "0.0.0.0", self._port)
        await site.start()
        logger.info(f"Health check server started on port {self._port}")

    async def stop(self) -> None:
        """Stop the health check server."""
        if self._runner:
            await self._runner.cleanup()
            logger.info("Health check server stopped")


@asynccontextmanager
async def create_bot(config: Config) -> AsyncGenerator[CryptoSignalBot, None]:
    """Context manager for bot lifecycle."""
    bot = CryptoSignalBot(config)
    health_server = HealthCheckServer(bot, config.health_check_port)

    await health_server.start()

    try:
        yield bot
    finally:
        await bot.stop()
        await health_server.stop()


async def main() -> None:
    """Main entry point."""
    try:
        config = load_config()
    except ValueError as e:
        logger.error(f"Configuration error: {e}")
        sys.exit(1)

    logger.info("Configuration loaded successfully")
    logger.info(f"Watchlist: {list(WATCHLIST.keys())}")
    logger.info(f"Signal threshold: {config.signal_threshold}")
    logger.info(f"Scan interval: {config.scan_interval_seconds}s")

    # Setup signal handlers for graceful shutdown
    loop = asyncio.get_running_loop()
    shutdown_event = asyncio.Event()

    def handle_shutdown(sig: signal.Signals) -> None:
        logger.info(f"Received signal {sig.name}, initiating shutdown...")
        shutdown_event.set()

    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, handle_shutdown, sig)

    async with create_bot(config) as bot:
        # Run bot and wait for shutdown signal
        bot_task = asyncio.create_task(bot.start())
        shutdown_task = asyncio.create_task(shutdown_event.wait())

        done, pending = await asyncio.wait(
            [bot_task, shutdown_task],
            return_when=asyncio.FIRST_COMPLETED,
        )

        # Cancel pending tasks
        for task in pending:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    logger.info("Bot shutdown complete")


if __name__ == "__main__":
    asyncio.run(main())
