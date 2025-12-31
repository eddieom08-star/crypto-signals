"""Main bot loop for crypto signal scanner."""

import asyncio
import logging
import signal
import sys
from collections import deque
from contextlib import asynccontextmanager
from datetime import datetime
from typing import AsyncGenerator


from analyzer import SignalAnalysis, SignalAnalyzer
from config import Config, WATCHLIST, load_config
from fetcher import DEXScreenerClient
from notifier import TelegramNotifier
from security_checker import SecurityChecker
from signal_store import RedisSignalStore

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)

# Maximum signals to store in memory
MAX_SIGNALS = 100
MAX_SCANS = 50


class SignalStore:
    """In-memory storage for signals and scan results."""

    def __init__(self, max_signals: int = MAX_SIGNALS, max_scans: int = MAX_SCANS):
        self._signals: deque[dict] = deque(maxlen=max_signals)
        self._latest_scans: deque[dict] = deque(maxlen=max_scans)

    def add_signal(self, signal: SignalAnalysis, sent: bool) -> None:
        """Store a signal that met the threshold."""
        self._signals.appendleft({
            "timestamp": datetime.now().isoformat(),
            "symbol": signal.symbol,
            "address": signal.address,
            "price_usd": signal.price_usd,
            "total_score": signal.total_score,
            "pop_score": signal.pop.pop_score,
            "pop_confidence": signal.pop.confidence,
            "expected_return": signal.pop.expected_return,
            "max_drawdown": signal.pop.max_drawdown,
            "signal_strength": signal.signal_strength,
            "risk_level": signal.risk_level,
            "is_locked": signal.is_locked,
            "lock_percentage": signal.lock_percentage,
            "is_bundled": signal.is_bundled,
            "bundle_percentage": signal.bundle_percentage,
            "security_score": signal.security_score,
            "bundle_penalty": signal.bundle_penalty,
            "liquidity_score": signal.liquidity_score,
            "volume_ratio_score": signal.volume_ratio_score,
            "momentum_score": signal.momentum_score,
            "buy_pressure_score": signal.buy_pressure_score,
            "trend_score": signal.trend_score,
            "entry_price": signal.entry_price,
            "stop_loss": signal.stop_loss,
            "take_profit_1": signal.take_profit_1,
            "take_profit_2": signal.take_profit_2,
            "take_profit_3": signal.take_profit_3,
            "risk_reward_ratio": signal.risk_reward_ratio,
            "security_warnings": signal.security_warnings,
            "pop_factors": signal.pop.factors,
            "telegram_sent": sent,
        })

    def add_scan(self, signal: SignalAnalysis) -> None:
        """Store a scan result (all tokens, not just signals)."""
        self._latest_scans.appendleft({
            "timestamp": datetime.now().isoformat(),
            "symbol": signal.symbol,
            "price_usd": signal.price_usd,
            "total_score": signal.total_score,
            "pop_score": signal.pop.pop_score,
            "signal_strength": signal.signal_strength,
            "risk_level": signal.risk_level,
            "is_valid_signal": signal.is_valid_signal,
        })

    def get_signals(self, limit: int = 20) -> list[dict]:
        """Get recent signals."""
        return list(self._signals)[:limit]

    def get_scans(self, limit: int = 20) -> list[dict]:
        """Get recent scan results."""
        return list(self._latest_scans)[:limit]


class CryptoSignalBot:
    """Main bot class for scanning and sending signals."""

    def __init__(self, config: Config, signal_store: SignalStore, redis_store: RedisSignalStore) -> None:
        self._config = config
        self._fetcher = DEXScreenerClient(config)
        self._analyzer = SignalAnalyzer(config.scoring_weights)
        self._security_checker = SecurityChecker(config.request_timeout)
        self._notifier = TelegramNotifier(config)
        self._signal_store = signal_store
        self._redis_store = redis_store
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
            "watchlist": list(WATCHLIST.keys()),
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

                # Fetch security data
                security_report = await self._security_checker.analyze_token(
                    token_config.address
                )

                # Analyze signal with security data
                signal_result = self._analyzer.analyze(token_data, security_report)

                # Store scan result (local + Redis)
                self._signal_store.add_scan(signal_result)
                await self._redis_store.add_scan(signal_result)

                logger.debug(
                    f"{symbol}: Score {signal_result.total_score}/100 PoP:{signal_result.pop.pop_score}% "
                    f"(L:{signal_result.liquidity_score} V:{signal_result.volume_ratio_score} "
                    f"M:{signal_result.momentum_score} B:{signal_result.buy_pressure_score} "
                    f"T:{signal_result.trend_score} S:{signal_result.security_score} P:-{signal_result.bundle_penalty})"
                )

                # Send alert if signal meets threshold and PoP is acceptable
                if signal_result.is_valid_signal:
                    sent = await self._notifier.send_signal(signal_result)
                    self._signal_store.add_signal(signal_result, sent)
                    await self._redis_store.add_signal(signal_result, sent)
                    if sent:
                        self._signals_sent += 1

                # Small delay between tokens to avoid rate limiting
                await asyncio.sleep(0.5)

            except Exception as e:
                logger.error(f"Error processing {symbol}: {e}")

        # Update status in Redis after each full scan
        await self._redis_store.update_status(self.status)


@asynccontextmanager
async def create_bot(config: Config) -> AsyncGenerator[CryptoSignalBot, None]:
    """Context manager for bot lifecycle."""
    signal_store = SignalStore()
    redis_store = RedisSignalStore()
    bot = CryptoSignalBot(config, signal_store, redis_store)

    if redis_store.is_enabled:
        logger.info("Redis signal store enabled - signals will be stored remotely")
    else:
        logger.info("Redis not configured - running in local-only mode")

    try:
        yield bot
    finally:
        await bot.stop()


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
