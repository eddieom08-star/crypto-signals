"""Telegram notification service for trading signals."""

import logging
from datetime import datetime, timedelta
from typing import Dict

import httpx

from analyzer import SignalAnalysis
from config import Config

logger = logging.getLogger(__name__)


class TelegramNotifier:
    """Sends trading signals to Telegram."""

    def __init__(self, config: Config) -> None:
        self._bot_token = config.telegram_bot_token
        self._chat_id = config.telegram_chat_id
        self._cooldown_minutes = config.signal_cooldown_minutes
        self._timeout = config.request_timeout
        self._sent_signals: Dict[str, datetime] = {}

    @property
    def _api_url(self) -> str:
        return f"https://api.telegram.org/bot{self._bot_token}"

    async def send_signal(self, signal: SignalAnalysis) -> bool:
        """Send trading signal to Telegram if not in cooldown."""

        # Check cooldown
        if self._is_in_cooldown(signal.symbol):
            logger.debug(f"Signal for {signal.symbol} in cooldown, skipping")
            return False

        message = self._format_signal_message(signal)

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.post(
                    f"{self._api_url}/sendMessage",
                    json={
                        "chat_id": self._chat_id,
                        "text": message,
                        "parse_mode": "HTML",
                        "disable_web_page_preview": True,
                    }
                )
                response.raise_for_status()

                # Update cooldown tracker
                self._sent_signals[signal.symbol] = datetime.now()
                logger.info(f"Sent signal for {signal.symbol} (score: {signal.total_score})")
                return True

        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error sending Telegram message: {e.response.status_code}")
            return False
        except httpx.RequestError as e:
            logger.error(f"Request error sending Telegram message: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error sending Telegram message: {e}")
            return False

    def _is_in_cooldown(self, symbol: str) -> bool:
        """Check if symbol is in cooldown period."""
        if symbol not in self._sent_signals:
            return False

        last_sent = self._sent_signals[symbol]
        cooldown_end = last_sent + timedelta(minutes=self._cooldown_minutes)
        return datetime.now() < cooldown_end

    def _format_signal_message(self, signal: SignalAnalysis) -> str:
        """Format signal as Telegram message."""

        # Signal strength emoji
        strength_emoji = {
            "STRONG": "🟢🟢🟢",
            "MODERATE": "🟡🟡",
            "WEAK": "🔴",
            "NO SIGNAL": "⚫",
        }.get(signal.signal_strength, "⚫")

        message = f"""
<b>🚀 CRYPTO SIGNAL ALERT</b>

<b>Token:</b> ${signal.symbol}
<b>Signal:</b> {strength_emoji} {signal.signal_strength}
<b>Score:</b> {signal.total_score}/100

━━━━━━━━━━━━━━━━━━━━

<b>📊 ANALYSIS BREAKDOWN</b>
• Liquidity: {signal.liquidity_score}/20
• Volume Ratio: {signal.volume_ratio_score}/20
• Momentum: {signal.momentum_score}/25
• Buy Pressure: {signal.buy_pressure_score}/20
• Trend: {signal.trend_score}/15

━━━━━━━━━━━━━━━━━━━━

<b>💰 TRADE SETUP</b>
<b>Entry:</b> ${self._format_price(signal.entry_price)}
<b>Stop Loss:</b> ${self._format_price(signal.stop_loss)} (-8%)

<b>Take Profits:</b>
• TP1: ${self._format_price(signal.take_profit_1)} (+15%)
• TP2: ${self._format_price(signal.take_profit_2)} (+30%)
• TP3: ${self._format_price(signal.take_profit_3)} (+50%)

<b>R:R Ratio:</b> 1:{signal.risk_reward_ratio}

━━━━━━━━━━━━━━━━━━━━

<b>⚠️ RISK MANAGEMENT</b>
• Position size: Max 2-5% of portfolio
• Scale out at each TP level
• Move SL to entry after TP1 hit
• Never risk more than you can afford to lose

<b>📍 Contract:</b>
<code>{signal.address}</code>

<i>DYOR - Not financial advice</i>
"""
        return message.strip()

    def _format_price(self, price: float) -> str:
        """Format price with appropriate decimal places."""
        if price >= 1:
            return f"{price:.4f}"
        elif price >= 0.0001:
            return f"{price:.6f}"
        else:
            return f"{price:.10f}"

    async def send_startup_message(self) -> bool:
        """Send bot startup notification."""
        message = """
<b>🤖 Crypto Signal Bot Started</b>

Bot is now monitoring tokens for trading signals.
Scan interval: 60 seconds
Signal threshold: 70/100

<i>You will receive alerts when strong signals are detected.</i>
"""
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.post(
                    f"{self._api_url}/sendMessage",
                    json={
                        "chat_id": self._chat_id,
                        "text": message.strip(),
                        "parse_mode": "HTML",
                    }
                )
                response.raise_for_status()
                logger.info("Sent startup message to Telegram")
                return True
        except Exception as e:
            logger.error(f"Failed to send startup message: {e}")
            return False

    async def send_error_alert(self, error_message: str) -> bool:
        """Send error notification to Telegram."""
        message = f"""
<b>⚠️ Bot Error Alert</b>

{error_message}

<i>Bot will continue attempting to recover.</i>
"""
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.post(
                    f"{self._api_url}/sendMessage",
                    json={
                        "chat_id": self._chat_id,
                        "text": message.strip(),
                        "parse_mode": "HTML",
                    }
                )
                response.raise_for_status()
                return True
        except Exception:
            return False
