"""Signal analyzer with technical indicators and scoring."""

import logging
from dataclasses import dataclass
from typing import Optional

from config import ScoringWeights
from fetcher import TokenData

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SignalAnalysis:
    """Analysis result for a token signal."""
    symbol: str
    address: str
    price_usd: float
    total_score: int
    liquidity_score: int
    volume_ratio_score: int
    momentum_score: int
    buy_pressure_score: int
    trend_score: int
    entry_price: float
    stop_loss: float
    take_profit_1: float
    take_profit_2: float
    take_profit_3: float
    risk_reward_ratio: float
    signal_strength: str

    @property
    def is_valid_signal(self) -> bool:
        return self.total_score >= 70


class SignalAnalyzer:
    """Analyzes token data and generates trading signals."""

    # Thresholds for scoring
    MIN_LIQUIDITY_USD = 50_000
    IDEAL_LIQUIDITY_USD = 500_000
    IDEAL_VOLUME_RATIO = 0.5
    MAX_VOLUME_RATIO = 2.0

    def __init__(self, weights: Optional[ScoringWeights] = None) -> None:
        self._weights = weights or ScoringWeights()

    def analyze(self, token_data: TokenData) -> SignalAnalysis:
        """Analyze token data and generate signal with scores."""

        # Calculate individual scores
        liquidity_score = self._score_liquidity(token_data.liquidity_usd)
        volume_ratio_score = self._score_volume_ratio(
            token_data.volume_24h,
            token_data.liquidity_usd
        )
        momentum_score = self._score_momentum(token_data)
        buy_pressure_score = self._score_buy_pressure(token_data)
        trend_score = self._score_trend(token_data)

        total_score = (
            liquidity_score +
            volume_ratio_score +
            momentum_score +
            buy_pressure_score +
            trend_score
        )

        # Calculate entry/exit points
        entry_price = token_data.price_usd
        stop_loss = entry_price * 0.92  # 8% stop loss
        take_profit_1 = entry_price * 1.15  # 15% TP1
        take_profit_2 = entry_price * 1.30  # 30% TP2
        take_profit_3 = entry_price * 1.50  # 50% TP3

        # Risk/reward ratio (using TP2 as target)
        risk = entry_price - stop_loss
        reward = take_profit_2 - entry_price
        risk_reward = reward / risk if risk > 0 else 0

        signal_strength = self._get_signal_strength(total_score)

        return SignalAnalysis(
            symbol=token_data.symbol,
            address=token_data.address,
            price_usd=entry_price,
            total_score=total_score,
            liquidity_score=liquidity_score,
            volume_ratio_score=volume_ratio_score,
            momentum_score=momentum_score,
            buy_pressure_score=buy_pressure_score,
            trend_score=trend_score,
            entry_price=entry_price,
            stop_loss=stop_loss,
            take_profit_1=take_profit_1,
            take_profit_2=take_profit_2,
            take_profit_3=take_profit_3,
            risk_reward_ratio=round(risk_reward, 2),
            signal_strength=signal_strength,
        )

    def _score_liquidity(self, liquidity_usd: float) -> int:
        """Score liquidity (0-20 points)."""
        max_points = self._weights.liquidity

        if liquidity_usd < self.MIN_LIQUIDITY_USD:
            return 0

        if liquidity_usd >= self.IDEAL_LIQUIDITY_USD:
            return max_points

        # Linear scale between min and ideal
        ratio = (liquidity_usd - self.MIN_LIQUIDITY_USD) / (
            self.IDEAL_LIQUIDITY_USD - self.MIN_LIQUIDITY_USD
        )
        return int(ratio * max_points)

    def _score_volume_ratio(self, volume_24h: float, liquidity: float) -> int:
        """Score volume/liquidity ratio (0-20 points)."""
        max_points = self._weights.volume_liquidity_ratio

        if liquidity <= 0:
            return 0

        ratio = volume_24h / liquidity

        # Best ratio is around 0.5-1.0 (healthy trading activity)
        if ratio < 0.1:
            return int(max_points * 0.2)  # Low activity
        elif ratio < self.IDEAL_VOLUME_RATIO:
            return int(max_points * (0.2 + 0.8 * (ratio / self.IDEAL_VOLUME_RATIO)))
        elif ratio <= 1.0:
            return max_points  # Ideal range
        elif ratio <= self.MAX_VOLUME_RATIO:
            # Slightly penalize very high ratios (potential manipulation)
            return int(max_points * 0.8)
        else:
            return int(max_points * 0.5)  # Very high ratio - caution

    def _score_momentum(self, data: TokenData) -> int:
        """Score price momentum (0-25 points)."""
        max_points = self._weights.price_momentum
        score = 0

        # Short-term momentum (5m, 1h) - more weight
        if data.price_change_5m > 0:
            score += min(5, data.price_change_5m / 2)  # Up to 5 points

        if data.price_change_1h > 0:
            score += min(8, data.price_change_1h / 1.5)  # Up to 8 points

        # Medium-term trend (6h, 24h)
        if data.price_change_6h > 0:
            score += min(6, data.price_change_6h / 2)  # Up to 6 points

        if data.price_change_24h > 0:
            score += min(6, data.price_change_24h / 3)  # Up to 6 points

        # Penalize extreme moves (potential pump and dump)
        if data.price_change_1h > 50:
            score *= 0.5

        return min(max_points, int(score))

    def _score_buy_pressure(self, data: TokenData) -> int:
        """Score buy pressure from transaction ratios (0-20 points)."""
        max_points = self._weights.buy_pressure

        # Calculate buy ratios for different timeframes
        def buy_ratio(buys: int, sells: int) -> float:
            total = buys + sells
            return buys / total if total > 0 else 0.5

        ratio_5m = buy_ratio(data.txns_buys_5m, data.txns_sells_5m)
        ratio_1h = buy_ratio(data.txns_buys_1h, data.txns_sells_1h)
        ratio_24h = buy_ratio(data.txns_buys_24h, data.txns_sells_24h)

        # Weight recent activity more heavily
        weighted_ratio = (ratio_5m * 0.4) + (ratio_1h * 0.35) + (ratio_24h * 0.25)

        # Score: 50% ratio = 0 points, 70%+ ratio = max points
        if weighted_ratio <= 0.5:
            return 0
        elif weighted_ratio >= 0.7:
            return max_points
        else:
            return int(((weighted_ratio - 0.5) / 0.2) * max_points)

    def _score_trend(self, data: TokenData) -> int:
        """Score trend strength and consistency (0-15 points)."""
        max_points = self._weights.trend_strength
        score = 0

        # Check for consistent uptrend across timeframes
        timeframes = [
            data.price_change_5m,
            data.price_change_1h,
            data.price_change_6h,
            data.price_change_24h,
        ]

        positive_count = sum(1 for t in timeframes if t > 0)

        # Bonus for consistency
        if positive_count == 4:
            score += 8  # All timeframes positive
        elif positive_count == 3:
            score += 5
        elif positive_count == 2:
            score += 2

        # Volume trend (increasing volume is bullish)
        if data.volume_1h > 0 and data.volume_24h > 0:
            hourly_avg_24h = data.volume_24h / 24
            if data.volume_1h > hourly_avg_24h * 1.5:
                score += 4  # Volume surge
            elif data.volume_1h > hourly_avg_24h:
                score += 2

        # Transaction activity trend
        total_txns_1h = data.txns_buys_1h + data.txns_sells_1h
        if total_txns_1h > 100:
            score += 3  # Active trading
        elif total_txns_1h > 50:
            score += 1

        return min(max_points, score)

    def _get_signal_strength(self, score: int) -> str:
        """Get signal strength description based on score."""
        if score >= 85:
            return "STRONG"
        elif score >= 70:
            return "MODERATE"
        elif score >= 50:
            return "WEAK"
        else:
            return "NO SIGNAL"
