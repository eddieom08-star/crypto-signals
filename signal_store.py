"""Signal storage using Upstash Redis REST API."""

import json
import logging
import os
from datetime import datetime
from typing import Optional

import httpx

from analyzer import SignalAnalysis

logger = logging.getLogger(__name__)


class RedisSignalStore:
    """Store signals in Upstash Redis using REST API."""

    def __init__(self) -> None:
        self._url = os.environ.get("UPSTASH_REDIS_REST_URL")
        self._token = os.environ.get("UPSTASH_REDIS_REST_TOKEN")
        self._enabled = bool(self._url and self._token)

        if not self._enabled:
            logger.warning("Upstash Redis not configured - signals won't be stored remotely")

    @property
    def is_enabled(self) -> bool:
        return self._enabled

    async def _execute(self, *args) -> Optional[dict]:
        """Execute Redis command via REST API."""
        if not self._enabled:
            return None

        try:
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.post(
                    self._url,
                    headers={"Authorization": f"Bearer {self._token}"},
                    json=list(args),
                )
                response.raise_for_status()
                return response.json()
        except Exception as e:
            logger.error(f"Redis error: {e}")
            return None

    async def add_signal(self, signal: SignalAnalysis, sent: bool) -> None:
        """Store a signal."""
        if not self._enabled:
            return

        data = {
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
        }

        # Add to list (LPUSH) and trim to 100 entries
        await self._execute("LPUSH", "signals", json.dumps(data))
        await self._execute("LTRIM", "signals", "0", "99")

    async def add_scan(self, signal: SignalAnalysis) -> None:
        """Store a scan result."""
        if not self._enabled:
            return

        data = {
            "timestamp": datetime.now().isoformat(),
            "symbol": signal.symbol,
            "price_usd": signal.price_usd,
            "total_score": signal.total_score,
            "pop_score": signal.pop.pop_score,
            "signal_strength": signal.signal_strength,
            "risk_level": signal.risk_level,
            "is_valid_signal": signal.is_valid_signal,
        }

        await self._execute("LPUSH", "scans", json.dumps(data))
        await self._execute("LTRIM", "scans", "0", "49")

    async def update_status(self, status: dict) -> None:
        """Update bot status."""
        if not self._enabled:
            return

        status["updated_at"] = datetime.now().isoformat()
        await self._execute("SET", "bot_status", json.dumps(status))
        await self._execute("EXPIRE", "bot_status", "120")  # 2 min TTL

    async def get_signals(self, limit: int = 20) -> list[dict]:
        """Get recent signals."""
        if not self._enabled:
            return []

        result = await self._execute("LRANGE", "signals", "0", str(limit - 1))
        if result and result.get("result"):
            return [json.loads(s) for s in result["result"]]
        return []

    async def get_scans(self, limit: int = 20) -> list[dict]:
        """Get recent scans."""
        if not self._enabled:
            return []

        result = await self._execute("LRANGE", "scans", "0", str(limit - 1))
        if result and result.get("result"):
            return [json.loads(s) for s in result["result"]]
        return []

    async def get_status(self) -> Optional[dict]:
        """Get bot status."""
        if not self._enabled:
            return None

        result = await self._execute("GET", "bot_status")
        if result and result.get("result"):
            return json.loads(result["result"])
        return None
