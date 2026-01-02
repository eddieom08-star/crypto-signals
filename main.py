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
from smart_money import SmartMoneyTracker
from technical import TechnicalAnalyzer, MarketContextAnalyzer, MarketContext

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
            "smart_money_score": signal.smart_money_score,
            "smart_money_signal": signal.smart_money_signal,
            "smart_money_confidence": signal.smart_money_confidence,
            "whale_net_flow": signal.whale_net_flow,
            "top_traders_buying": signal.top_traders_buying,
            "top_traders_selling": signal.top_traders_selling,
            "social_score": signal.social_score,
            "social_sentiment": signal.social_sentiment,
            "social_mentions_24h": signal.social_mentions_24h,
            "social_mentions_change": signal.social_mentions_change,
            "influencer_mentions": signal.influencer_mentions,
            "galaxy_score": signal.galaxy_score,
            "liquidity_score": signal.liquidity_score,
            "volume_ratio_score": signal.volume_ratio_score,
            "momentum_score": signal.momentum_score,
            "buy_pressure_score": signal.buy_pressure_score,
            "trend_score": signal.trend_score,
            "technical_score": signal.technical_score,
            "rsi_14": signal.rsi_14,
            "rsi_signal": signal.rsi_signal,
            "vwap_deviation": signal.vwap_deviation,
            "price_vs_vwap": signal.price_vs_vwap,
            "consolidation_break": signal.consolidation_break,
            "market_context_score": signal.market_context_score,
            "btc_trend_bullish": signal.btc_trend_bullish,
            "fear_greed_index": signal.fear_greed_index,
            "fear_greed_label": signal.fear_greed_label,
            "market_favorable": signal.market_favorable,
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
        self._smart_money_tracker = SmartMoneyTracker()
        self._technical_analyzer = TechnicalAnalyzer(config.request_timeout)
        self._market_context_analyzer = MarketContextAnalyzer(config.request_timeout)
        self._notifier = TelegramNotifier(config)
        self._signal_store = signal_store
        self._redis_store = redis_store
        self._running = False
        self._scan_count = 0
        self._signals_sent = 0
        self._last_scan: datetime | None = None
        self._errors_count = 0
        self._cached_market_context: MarketContext | None = None
        self._market_context_updated: datetime | None = None

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
        # Update market context every 5 minutes
        now = datetime.now()
        if (
            self._cached_market_context is None
            or self._market_context_updated is None
            or (now - self._market_context_updated).seconds > 300
        ):
            self._cached_market_context = await self._market_context_analyzer.analyze()
            self._market_context_updated = now
            logger.debug(
                f"Market context updated: BTC {'above' if self._cached_market_context.btc_above_ema20 else 'below'} EMA20, "
                f"Fear & Greed: {self._cached_market_context.fear_greed_index} ({self._cached_market_context.fear_greed_label})"
            )

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

                # Fetch smart money data (pass symbol for social APIs)
                smart_money_report = await self._smart_money_tracker.analyze(
                    token_config.address, symbol=symbol
                )

                # Calculate technical indicators from token data
                # Use available price change data to approximate price history
                prices = self._approximate_price_history(token_data)
                volumes = self._approximate_volume_history(token_data)
                technical_indicators = self._technical_analyzer.analyze(
                    prices, volumes, token_data.price_usd
                )

                # Analyze signal with all data sources
                signal_result = self._analyzer.analyze(
                    token_data,
                    security_report,
                    smart_money_report,
                    technical_indicators,
                    self._cached_market_context,
                )

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

    def _approximate_price_history(self, token_data) -> list[float]:
        """Approximate price history from available change data.

        Uses price changes at different timeframes to reconstruct
        approximate historical prices for RSI/VWAP calculation.
        """
        current_price = token_data.price_usd
        if current_price <= 0:
            return []

        # Work backwards from current price using change percentages
        # This gives us approximate prices at different points in time
        prices = []

        # 24h ago
        if token_data.price_change_24h != 0:
            price_24h_ago = current_price / (1 + token_data.price_change_24h / 100)
            prices.append(price_24h_ago)

        # 6h ago
        if token_data.price_change_6h != 0:
            price_6h_ago = current_price / (1 + token_data.price_change_6h / 100)
            prices.append(price_6h_ago)

        # 1h ago
        if token_data.price_change_1h != 0:
            price_1h_ago = current_price / (1 + token_data.price_change_1h / 100)
            prices.append(price_1h_ago)

        # 5m ago
        if token_data.price_change_5m != 0:
            price_5m_ago = current_price / (1 + token_data.price_change_5m / 100)
            prices.append(price_5m_ago)

        # Current price
        prices.append(current_price)

        # Interpolate to get ~20 data points for RSI calculation
        if len(prices) >= 2:
            interpolated = []
            for i in range(len(prices) - 1):
                start, end = prices[i], prices[i + 1]
                steps = 5
                for j in range(steps):
                    interpolated.append(start + (end - start) * (j / steps))
            interpolated.append(prices[-1])
            return interpolated

        return prices if prices else [current_price] * 20

    def _approximate_volume_history(self, token_data) -> list[float]:
        """Approximate volume history from available data."""
        # Use 24h volume divided by periods
        if token_data.volume_24h <= 0:
            return []

        hourly_avg = token_data.volume_24h / 24
        current_hour_vol = token_data.volume_1h if token_data.volume_1h > 0 else hourly_avg

        # Create approximate volume distribution
        # Assume recent volume is more representative
        volumes = []
        for i in range(20):
            # Gradual transition from average to current
            weight = i / 19
            vol = hourly_avg * (1 - weight) + current_hour_vol * weight
            volumes.append(vol)

        return volumes


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
