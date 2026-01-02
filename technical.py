"""Technical indicators module for signal analysis."""

import logging
from dataclasses import dataclass, field
from typing import Optional

import httpx

logger = logging.getLogger(__name__)


@dataclass
class TechnicalIndicators:
    """Technical analysis indicators."""

    rsi_14: float = 50.0  # Relative Strength Index (14 period)
    vwap: float = 0.0  # Volume Weighted Average Price
    vwap_deviation: float = 0.0  # % deviation from VWAP
    consolidation_break: bool = False  # Breakout from consolidation
    price_vs_vwap: str = "NEUTRAL"  # ABOVE, BELOW, NEUTRAL
    rsi_signal: str = "NEUTRAL"  # OVERSOLD, OVERBOUGHT, NEUTRAL
    technical_score: int = 0  # 0-100 score
    patterns: list[str] = field(default_factory=list)


class TechnicalAnalyzer:
    """Calculate technical indicators from price/volume data."""

    def __init__(self, timeout: float = 10.0) -> None:
        self._timeout = timeout

    def calculate_rsi(self, prices: list[float], period: int = 14) -> float:
        """Calculate RSI from price list."""
        if len(prices) < period + 1:
            return 50.0  # Default neutral

        # Calculate price changes
        changes = [prices[i] - prices[i - 1] for i in range(1, len(prices))]

        # Separate gains and losses
        gains = [c if c > 0 else 0 for c in changes]
        losses = [-c if c < 0 else 0 for c in changes]

        # Calculate average gain/loss (SMA for first, then EMA)
        avg_gain = sum(gains[:period]) / period
        avg_loss = sum(losses[:period]) / period

        # EMA smoothing for remaining periods
        for i in range(period, len(changes)):
            avg_gain = (avg_gain * (period - 1) + gains[i]) / period
            avg_loss = (avg_loss * (period - 1) + losses[i]) / period

        if avg_loss == 0:
            return 100.0

        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
        return round(rsi, 2)

    def calculate_vwap(
        self, prices: list[float], volumes: list[float]
    ) -> tuple[float, float]:
        """Calculate VWAP and deviation from current price."""
        if not prices or not volumes or len(prices) != len(volumes):
            return 0.0, 0.0

        total_volume = sum(volumes)
        if total_volume == 0:
            return prices[-1] if prices else 0.0, 0.0

        # VWAP = Σ(Price × Volume) / Σ(Volume)
        vwap = sum(p * v for p, v in zip(prices, volumes)) / total_volume
        current_price = prices[-1]

        # Calculate deviation percentage
        if vwap > 0:
            deviation = ((current_price - vwap) / vwap) * 100
        else:
            deviation = 0.0

        return round(vwap, 8), round(deviation, 2)

    def detect_consolidation_break(
        self,
        prices: list[float],
        current_price: float,
        lookback: int = 20,
        threshold: float = 0.05,
    ) -> bool:
        """Detect if price is breaking out of consolidation range."""
        if len(prices) < lookback:
            return False

        recent_prices = prices[-lookback:]
        high = max(recent_prices)
        low = min(recent_prices)
        range_size = high - low

        # Check if range is tight (consolidation)
        avg_price = sum(recent_prices) / len(recent_prices)
        if avg_price == 0:
            return False

        range_percent = range_size / avg_price

        # Consolidation: tight range, then breakout above
        if range_percent < threshold:
            # Breakout: current price above recent high
            if current_price > high * 1.02:  # 2% above range high
                return True

        return False

    def analyze(
        self,
        prices: list[float],
        volumes: list[float],
        current_price: float,
    ) -> TechnicalIndicators:
        """Perform full technical analysis."""
        result = TechnicalIndicators()
        patterns = []

        # RSI calculation
        if len(prices) >= 15:
            result.rsi_14 = self.calculate_rsi(prices)
            if result.rsi_14 < 30:
                result.rsi_signal = "OVERSOLD"
                patterns.append("RSI Oversold (<30)")
            elif result.rsi_14 > 70:
                result.rsi_signal = "OVERBOUGHT"
                patterns.append("RSI Overbought (>70)")
            else:
                result.rsi_signal = "NEUTRAL"

        # VWAP calculation
        if prices and volumes:
            result.vwap, result.vwap_deviation = self.calculate_vwap(prices, volumes)
            if result.vwap > 0:
                if current_price > result.vwap * 1.02:
                    result.price_vs_vwap = "ABOVE"
                    patterns.append("Price above VWAP")
                elif current_price < result.vwap * 0.98:
                    result.price_vs_vwap = "BELOW"
                    patterns.append("Price below VWAP")
                else:
                    result.price_vs_vwap = "NEUTRAL"

        # Consolidation breakout
        result.consolidation_break = self.detect_consolidation_break(
            prices, current_price
        )
        if result.consolidation_break:
            patterns.append("Consolidation breakout")

        result.patterns = patterns

        # Calculate technical score (0-100)
        score = 50  # Start neutral

        # RSI contribution (-15 to +15)
        if result.rsi_14 < 30:
            score += 15  # Oversold = bullish
        elif result.rsi_14 < 40:
            score += 10
        elif result.rsi_14 > 70:
            score -= 15  # Overbought = bearish risk
        elif result.rsi_14 > 60:
            score += 5  # Strong momentum

        # VWAP contribution (-15 to +15)
        if result.price_vs_vwap == "ABOVE":
            score += 15  # Bullish
        elif result.price_vs_vwap == "BELOW":
            score -= 10

        # Consolidation breakout (+20)
        if result.consolidation_break:
            score += 20

        result.technical_score = max(0, min(100, score))
        return result


@dataclass
class MarketContext:
    """Broader market context data."""

    btc_price: float = 0.0
    btc_24h_change: float = 0.0
    btc_above_ema20: bool = False
    fear_greed_index: int = 50  # 0-100
    fear_greed_label: str = "Neutral"  # Extreme Fear, Fear, Neutral, Greed, Extreme Greed
    sol_price: float = 0.0
    sol_24h_change: float = 0.0
    funding_rate: float = 0.0  # Perpetual funding rate
    market_favorable: bool = True
    context_score: int = 50  # 0-100


class MarketContextAnalyzer:
    """Fetch and analyze broader market conditions."""

    FEAR_GREED_API = "https://api.alternative.me/fng/"
    COINGECKO_API = "https://api.coingecko.com/api/v3"

    def __init__(self, timeout: float = 10.0) -> None:
        self._timeout = timeout
        self._btc_ema20: float = 0.0

    async def fetch_fear_greed(self) -> tuple[int, str]:
        """Fetch Fear & Greed Index."""
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.get(self.FEAR_GREED_API)
                response.raise_for_status()
                data = response.json()

                if data.get("data"):
                    fng = data["data"][0]
                    value = int(fng.get("value", 50))
                    label = fng.get("value_classification", "Neutral")
                    return value, label
        except Exception as e:
            logger.debug(f"Fear & Greed fetch error: {e}")

        return 50, "Neutral"

    async def fetch_btc_sol_prices(self) -> tuple[dict, dict]:
        """Fetch BTC and SOL market data from CoinGecko."""
        btc_data = {"price": 0.0, "change_24h": 0.0}
        sol_data = {"price": 0.0, "change_24h": 0.0}

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.get(
                    f"{self.COINGECKO_API}/simple/price",
                    params={
                        "ids": "bitcoin,solana",
                        "vs_currencies": "usd",
                        "include_24hr_change": "true",
                    },
                )
                response.raise_for_status()
                data = response.json()

                if "bitcoin" in data:
                    btc_data["price"] = data["bitcoin"].get("usd", 0)
                    btc_data["change_24h"] = data["bitcoin"].get("usd_24h_change", 0)

                if "solana" in data:
                    sol_data["price"] = data["solana"].get("usd", 0)
                    sol_data["change_24h"] = data["solana"].get("usd_24h_change", 0)

        except Exception as e:
            logger.debug(f"CoinGecko fetch error: {e}")

        return btc_data, sol_data

    async def fetch_btc_ema20(self) -> float:
        """Fetch BTC 20-day EMA (approximated from recent prices)."""
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.get(
                    f"{self.COINGECKO_API}/coins/bitcoin/market_chart",
                    params={"vs_currency": "usd", "days": "30"},
                )
                response.raise_for_status()
                data = response.json()

                prices = [p[1] for p in data.get("prices", [])]
                if len(prices) >= 20:
                    # Calculate 20-period EMA
                    ema = self._calculate_ema(prices, 20)
                    return ema

        except Exception as e:
            logger.debug(f"BTC EMA fetch error: {e}")

        return 0.0

    def _calculate_ema(self, prices: list[float], period: int) -> float:
        """Calculate EMA for given period."""
        if len(prices) < period:
            return prices[-1] if prices else 0.0

        multiplier = 2 / (period + 1)
        ema = sum(prices[:period]) / period  # Start with SMA

        for price in prices[period:]:
            ema = (price - ema) * multiplier + ema

        return ema

    async def analyze(self) -> MarketContext:
        """Perform full market context analysis."""
        result = MarketContext()

        # Fetch all data
        fear_greed, fg_label = await self.fetch_fear_greed()
        btc_data, sol_data = await self.fetch_btc_sol_prices()
        btc_ema20 = await self.fetch_btc_ema20()

        result.fear_greed_index = fear_greed
        result.fear_greed_label = fg_label
        result.btc_price = btc_data["price"]
        result.btc_24h_change = btc_data["change_24h"]
        result.sol_price = sol_data["price"]
        result.sol_24h_change = sol_data["change_24h"]

        # Check if BTC is above 20 EMA
        if btc_ema20 > 0 and result.btc_price > 0:
            result.btc_above_ema20 = result.btc_price > btc_ema20

        # Determine if market is favorable
        # Favorable: Fear & Greed not extreme fear, BTC above EMA, BTC not dumping
        favorable_conditions = 0

        if result.fear_greed_index > 25:  # Not extreme fear
            favorable_conditions += 1

        if result.btc_above_ema20:
            favorable_conditions += 1

        if result.btc_24h_change > -5:  # BTC not crashing
            favorable_conditions += 1

        if result.sol_24h_change > -10:  # SOL not crashing
            favorable_conditions += 1

        result.market_favorable = favorable_conditions >= 3

        # Calculate context score
        score = 50

        # Fear & Greed contribution (-20 to +20)
        if result.fear_greed_index < 20:
            score -= 20  # Extreme fear - risky
        elif result.fear_greed_index < 40:
            score -= 5  # Fear - cautious
        elif result.fear_greed_index > 75:
            score -= 10  # Extreme greed - potential top
        elif result.fear_greed_index > 55:
            score += 15  # Greed - bullish momentum

        # BTC trend contribution (-15 to +15)
        if result.btc_above_ema20:
            score += 15
        else:
            score -= 10

        # BTC 24h change contribution (-10 to +10)
        if result.btc_24h_change > 3:
            score += 10
        elif result.btc_24h_change > 0:
            score += 5
        elif result.btc_24h_change < -5:
            score -= 10
        elif result.btc_24h_change < 0:
            score -= 5

        result.context_score = max(0, min(100, score))
        return result
