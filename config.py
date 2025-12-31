"""Configuration management for crypto signal bot."""

import os
from dataclasses import dataclass
from typing import Dict


@dataclass(frozen=True)
class TokenConfig:
    """Token configuration."""
    symbol: str
    address: str
    chain: str = "solana"


@dataclass(frozen=True)
class ScoringWeights:
    """Scoring weights for signal analysis."""
    liquidity: int = 20
    volume_liquidity_ratio: int = 20
    price_momentum: int = 25
    buy_pressure: int = 20
    trend_strength: int = 15


@dataclass(frozen=True)
class Config:
    """Application configuration."""

    # Telegram settings
    telegram_bot_token: str
    telegram_chat_id: str

    # Scan settings
    scan_interval_seconds: int = 60
    signal_threshold: int = 70
    signal_cooldown_minutes: int = 30

    # API settings
    dexscreener_base_url: str = "https://api.dexscreener.com/latest/dex"
    request_timeout: int = 30

    # Health check
    health_check_port: int = 8080

    # Scoring weights
    scoring_weights: ScoringWeights = ScoringWeights()


# Watchlist: Solana tokens
WATCHLIST: Dict[str, TokenConfig] = {
    "BONK": TokenConfig(
        symbol="BONK",
        address="DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263"
    ),
    "WIF": TokenConfig(
        symbol="WIF",
        address="EKpQGSJtjMFqKZ9KQanSqYXRcF8fBopzLHYxdM65zcjm"
    ),
    "JUP": TokenConfig(
        symbol="JUP",
        address="JUPyiwrYJFskUPiHa7hkeR8VUtAeFoSYbKedZNsDvCN"
    ),
}


def load_config() -> Config:
    """Load configuration from environment variables."""
    telegram_bot_token = os.environ.get("TELEGRAM_BOT_TOKEN")
    telegram_chat_id = os.environ.get("TELEGRAM_CHAT_ID")

    if not telegram_bot_token:
        raise ValueError("TELEGRAM_BOT_TOKEN environment variable is required")
    if not telegram_chat_id:
        raise ValueError("TELEGRAM_CHAT_ID environment variable is required")

    return Config(
        telegram_bot_token=telegram_bot_token,
        telegram_chat_id=telegram_chat_id,
        scan_interval_seconds=int(os.environ.get("SCAN_INTERVAL", "60")),
        signal_threshold=int(os.environ.get("SIGNAL_THRESHOLD", "70")),
        signal_cooldown_minutes=int(os.environ.get("SIGNAL_COOLDOWN", "30")),
        health_check_port=int(os.environ.get("PORT", "8080")),
    )
