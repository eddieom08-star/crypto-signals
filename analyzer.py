"""Signal analyzer with technical indicators, security scoring, smart money, and PoP calculation."""

import logging
from dataclasses import dataclass
from typing import Optional

from config import ScoringWeights
from fetcher import TokenData
from security_checker import SecurityReport, RiskLevel
from smart_money import SmartMoneyReport

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PoPAnalysis:
    """Probability of Profit analysis."""
    pop_score: int  # 0-100 percentage
    confidence: str  # LOW, MEDIUM, HIGH
    factors: dict  # Contributing factors breakdown
    expected_return: float  # Expected return percentage
    max_drawdown: float  # Expected max drawdown percentage


@dataclass(frozen=True)
class SignalAnalysis:
    """Analysis result for a token signal."""
    symbol: str
    address: str
    price_usd: float

    # Core scores
    total_score: int
    liquidity_score: int
    volume_ratio_score: int
    momentum_score: int
    buy_pressure_score: int
    trend_score: int

    # Security scores
    security_score: int
    lock_score: int
    bundle_penalty: int

    # Smart money scores
    smart_money_score: int
    smart_money_signal: str  # ACCUMULATION, DISTRIBUTION, NEUTRAL
    smart_money_confidence: str  # HIGH, MEDIUM, LOW
    whale_net_flow: float
    top_traders_buying: int
    top_traders_selling: int

    # Social sentiment scores
    social_score: int
    social_sentiment: str  # BULLISH, BEARISH, NEUTRAL
    social_mentions_24h: int
    social_mentions_change: float
    influencer_mentions: int
    galaxy_score: int

    # PoP analysis
    pop: PoPAnalysis

    # Trade setup
    entry_price: float
    stop_loss: float
    take_profit_1: float
    take_profit_2: float
    take_profit_3: float
    risk_reward_ratio: float
    signal_strength: str

    # Security details
    is_locked: bool
    lock_percentage: float
    is_bundled: bool
    bundle_percentage: float
    risk_level: str
    security_warnings: list[str]

    @property
    def is_valid_signal(self) -> bool:
        return self.total_score >= 70 and self.pop.pop_score >= 50


class SignalAnalyzer:
    """Analyzes token data and generates trading signals with security analysis."""

    # Thresholds for scoring
    MIN_LIQUIDITY_USD = 50_000
    IDEAL_LIQUIDITY_USD = 500_000
    IDEAL_VOLUME_RATIO = 0.5
    MAX_VOLUME_RATIO = 2.0

    # PoP model weights (based on historical patterns)
    POP_WEIGHTS = {
        "momentum": 0.15,
        "volume": 0.10,
        "buy_pressure": 0.15,
        "liquidity": 0.10,
        "security": 0.20,
        "trend": 0.10,
        "smart_money": 0.20,  # New: smart money signals
    }

    def __init__(self, weights: Optional[ScoringWeights] = None) -> None:
        self._weights = weights or ScoringWeights()

    def analyze(
        self,
        token_data: TokenData,
        security_report: Optional[SecurityReport] = None,
        smart_money_report: Optional[SmartMoneyReport] = None
    ) -> SignalAnalysis:
        """Analyze token data with security, smart money integration, and PoP calculation."""

        # Calculate technical scores
        liquidity_score = self._score_liquidity(token_data.liquidity_usd)
        volume_ratio_score = self._score_volume_ratio(
            token_data.volume_24h,
            token_data.liquidity_usd
        )
        momentum_score = self._score_momentum(token_data)
        buy_pressure_score = self._score_buy_pressure(token_data)
        trend_score = self._score_trend(token_data)

        # Calculate security scores
        security_score, lock_score, bundle_penalty, security_warnings = \
            self._score_security(security_report)

        # Calculate smart money scores
        sm_score, sm_signal, sm_confidence, sm_bonus = self._score_smart_money(smart_money_report)

        # Total technical score (before security adjustments)
        base_score = (
            liquidity_score +
            volume_ratio_score +
            momentum_score +
            buy_pressure_score +
            trend_score
        )

        # Apply security and smart money adjustments
        total_score = max(0, min(100, base_score + security_score - bundle_penalty + sm_bonus))

        # Calculate PoP
        pop = self._calculate_pop(
            token_data,
            security_report,
            smart_money_report,
            liquidity_score,
            volume_ratio_score,
            momentum_score,
            buy_pressure_score,
            trend_score,
            bundle_penalty
        )

        # Extract smart money details
        whale_net_flow = smart_money_report.whale_activity.whale_net_flow if smart_money_report else 0
        top_traders_buying = smart_money_report.trader_signals.top_traders_buying if smart_money_report else 0
        top_traders_selling = smart_money_report.trader_signals.top_traders_selling if smart_money_report else 0

        # Extract social sentiment details
        social_score = smart_money_report.social_sentiment.social_score if smart_money_report else 50
        social_sentiment = smart_money_report.social_sentiment.sentiment if smart_money_report else "NEUTRAL"
        social_mentions_24h = smart_money_report.social_sentiment.mentions_24h if smart_money_report else 0
        social_mentions_change = smart_money_report.social_sentiment.mentions_change_pct if smart_money_report else 0
        influencer_mentions = smart_money_report.social_sentiment.influencer_mentions if smart_money_report else 0
        galaxy_score = smart_money_report.social_sentiment.galaxy_score if smart_money_report else 0

        # Calculate entry/exit points (adjusted for risk)
        entry_price = token_data.price_usd
        risk_multiplier = self._get_risk_multiplier(security_report)

        stop_loss = entry_price * (1 - 0.08 * risk_multiplier)
        take_profit_1 = entry_price * (1 + 0.15 / risk_multiplier)
        take_profit_2 = entry_price * (1 + 0.30 / risk_multiplier)
        take_profit_3 = entry_price * (1 + 0.50 / risk_multiplier)

        # Risk/reward ratio
        risk = entry_price - stop_loss
        reward = take_profit_2 - entry_price
        risk_reward = reward / risk if risk > 0 else 0

        signal_strength = self._get_signal_strength(total_score, pop.pop_score)

        # Extract security details
        is_locked = security_report.liquidity_lock.is_locked if security_report else False
        lock_pct = security_report.liquidity_lock.lock_percentage if security_report else 0
        is_bundled = security_report.bundle_analysis.is_bundled if security_report else False
        bundle_pct = security_report.bundle_analysis.bundle_percentage if security_report else 0
        risk_level = security_report.risk_level.value if security_report else "UNKNOWN"

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
            security_score=security_score,
            lock_score=lock_score,
            bundle_penalty=bundle_penalty,
            smart_money_score=sm_score,
            smart_money_signal=sm_signal,
            smart_money_confidence=sm_confidence,
            whale_net_flow=whale_net_flow,
            top_traders_buying=top_traders_buying,
            top_traders_selling=top_traders_selling,
            social_score=social_score,
            social_sentiment=social_sentiment,
            social_mentions_24h=social_mentions_24h,
            social_mentions_change=social_mentions_change,
            influencer_mentions=influencer_mentions,
            galaxy_score=galaxy_score,
            pop=pop,
            entry_price=entry_price,
            stop_loss=stop_loss,
            take_profit_1=take_profit_1,
            take_profit_2=take_profit_2,
            take_profit_3=take_profit_3,
            risk_reward_ratio=round(risk_reward, 2),
            signal_strength=signal_strength,
            is_locked=is_locked,
            lock_percentage=lock_pct,
            is_bundled=is_bundled,
            bundle_percentage=bundle_pct,
            risk_level=risk_level,
            security_warnings=security_warnings,
        )

    def _score_security(
        self,
        report: Optional[SecurityReport]
    ) -> tuple[int, int, int, list[str]]:
        """Score security factors. Returns (security_score, lock_score, bundle_penalty, warnings)."""
        warnings = []

        if not report:
            return 0, 0, 0, ["Security data unavailable"]

        # Lock score (0-10 bonus points)
        lock_score = 0
        if report.liquidity_lock.is_locked:
            if report.liquidity_lock.lock_percentage >= 95:
                lock_score = 10
            elif report.liquidity_lock.lock_percentage >= 80:
                lock_score = 7
            elif report.liquidity_lock.lock_percentage >= 50:
                lock_score = 4
        else:
            warnings.append("Liquidity NOT locked")

        # Bundle penalty (0-25 points deducted)
        bundle_penalty = 0
        bundle = report.bundle_analysis

        if bundle.is_bundled:
            warnings.append(f"Token bundled ({bundle.bundle_percentage:.1f}% concentrated)")
            bundle_penalty += 10

        if bundle.deployer_holdings_pct > 20:
            warnings.append(f"Deployer holds {bundle.deployer_holdings_pct:.1f}%")
            bundle_penalty += 8

        if bundle.top_10_holders_pct > 60:
            warnings.append(f"Top 10 hold {bundle.top_10_holders_pct:.1f}%")
            bundle_penalty += 7

        if bundle.sniper_count > 20:
            warnings.append(f"High sniper activity ({bundle.sniper_count} wallets)")
            bundle_penalty += 5

        # Contract risk penalties
        if report.is_mintable:
            warnings.append("Mint authority enabled")
            bundle_penalty += 5

        if report.is_freezable:
            warnings.append("Freeze authority enabled")
            bundle_penalty += 5

        if report.is_mutable:
            warnings.append("Metadata is mutable")
            bundle_penalty += 2

        # Security score based on RugCheck
        security_score = lock_score
        if report.rugcheck_score:
            # RugCheck: 0-1000, convert to 0-5 bonus
            security_score += min(5, report.rugcheck_score // 200)

        return security_score, lock_score, bundle_penalty, warnings

    def _score_smart_money(
        self,
        report: Optional[SmartMoneyReport]
    ) -> tuple[int, str, str, int]:
        """Score smart money signals. Returns (score, signal, confidence, bonus_points)."""
        if not report:
            return 50, "NEUTRAL", "LOW", 0

        score = report.smart_money_score
        signal = report.signal
        confidence = report.confidence

        # Calculate bonus/penalty based on smart money activity
        bonus = 0

        # Accumulation signal = bullish
        if signal == "ACCUMULATION":
            bonus += 10 if confidence == "HIGH" else 5

        # Distribution signal = bearish
        elif signal == "DISTRIBUTION":
            bonus -= 10 if confidence == "HIGH" else 5

        # Whale net flow bonus
        whale = report.whale_activity
        if whale.whale_net_flow > 50000:
            bonus += 5
        elif whale.whale_net_flow < -50000:
            bonus -= 5

        # Top traders signal
        traders = report.trader_signals
        if traders.top_traders_buying > traders.top_traders_selling * 2:
            bonus += 5
        elif traders.top_traders_selling > traders.top_traders_buying * 2:
            bonus -= 5

        # High profitable holder % is bullish
        if traders.profitable_holder_pct > 70:
            bonus += 3
        elif traders.profitable_holder_pct < 30:
            bonus -= 3

        return score, signal, confidence, bonus

    def _calculate_pop(
        self,
        token_data: TokenData,
        security_report: Optional[SecurityReport],
        smart_money_report: Optional[SmartMoneyReport],
        liquidity_score: int,
        volume_ratio_score: int,
        momentum_score: int,
        buy_pressure_score: int,
        trend_score: int,
        bundle_penalty: int,
    ) -> PoPAnalysis:
        """Calculate Probability of Profit using multiple factors."""

        # Normalize scores to 0-1 range
        momentum_norm = momentum_score / 25
        volume_norm = volume_ratio_score / 20
        buy_pressure_norm = buy_pressure_score / 20
        liquidity_norm = liquidity_score / 20
        trend_norm = trend_score / 15

        # Security factor (inverted - lower risk = higher PoP)
        if security_report:
            security_norm = max(0, 1 - (security_report.risk_score / 100))
        else:
            security_norm = 0.5  # Neutral if unknown

        # Smart money factor (0-100 score normalized to 0-1)
        if smart_money_report:
            smart_money_norm = smart_money_report.smart_money_score / 100
            # Boost for accumulation, reduce for distribution
            if smart_money_report.signal == "ACCUMULATION":
                smart_money_norm = min(1.0, smart_money_norm * 1.2)
            elif smart_money_report.signal == "DISTRIBUTION":
                smart_money_norm = max(0, smart_money_norm * 0.8)
        else:
            smart_money_norm = 0.5  # Neutral if unknown

        # Bundle penalty reduces PoP significantly
        bundle_factor = max(0, 1 - (bundle_penalty / 30))

        # Weighted PoP calculation
        base_pop = (
            momentum_norm * self.POP_WEIGHTS["momentum"] +
            volume_norm * self.POP_WEIGHTS["volume"] +
            buy_pressure_norm * self.POP_WEIGHTS["buy_pressure"] +
            liquidity_norm * self.POP_WEIGHTS["liquidity"] +
            security_norm * self.POP_WEIGHTS["security"] +
            trend_norm * self.POP_WEIGHTS["trend"] +
            smart_money_norm * self.POP_WEIGHTS["smart_money"]
        )

        # Apply bundle factor
        adjusted_pop = base_pop * bundle_factor

        # Additional adjustments based on market conditions
        # Strong momentum + buy pressure = higher PoP
        if momentum_norm > 0.7 and buy_pressure_norm > 0.7:
            adjusted_pop *= 1.1

        # Locked + low bundle = higher PoP
        if security_report and security_report.liquidity_lock.is_locked:
            if not security_report.bundle_analysis.is_bundled:
                adjusted_pop *= 1.15

        # Extreme moves reduce PoP (potential reversal)
        if token_data.price_change_1h > 50:
            adjusted_pop *= 0.7
        elif token_data.price_change_1h > 30:
            adjusted_pop *= 0.85

        # Convert to percentage (0-100)
        pop_score = min(95, max(5, int(adjusted_pop * 100)))

        # Determine confidence level
        data_completeness = sum([
            1 if liquidity_score > 0 else 0,
            1 if volume_ratio_score > 0 else 0,
            1 if security_report is not None else 0,
            1 if smart_money_report is not None else 0,
            1 if token_data.txns_buys_1h + token_data.txns_sells_1h > 50 else 0,
        ]) / 5

        if data_completeness >= 0.75 and pop_score >= 60:
            confidence = "HIGH"
        elif data_completeness >= 0.5:
            confidence = "MEDIUM"
        else:
            confidence = "LOW"

        # Expected return calculation
        # Based on PoP and typical outcomes
        if pop_score >= 70:
            expected_return = 15 + (pop_score - 70) * 0.5  # 15-27.5%
            max_drawdown = 8 + (100 - pop_score) * 0.2
        elif pop_score >= 50:
            expected_return = 5 + (pop_score - 50) * 0.5  # 5-15%
            max_drawdown = 12 + (70 - pop_score) * 0.3
        else:
            expected_return = -5 + pop_score * 0.2  # -5 to 5%
            max_drawdown = 15 + (50 - pop_score) * 0.4

        factors = {
            "momentum": round(momentum_norm * 100),
            "volume": round(volume_norm * 100),
            "buy_pressure": round(buy_pressure_norm * 100),
            "liquidity": round(liquidity_norm * 100),
            "security": round(security_norm * 100),
            "trend": round(trend_norm * 100),
            "smart_money": round(smart_money_norm * 100),
            "bundle_impact": round((1 - bundle_factor) * 100),
        }

        return PoPAnalysis(
            pop_score=pop_score,
            confidence=confidence,
            factors=factors,
            expected_return=round(expected_return, 1),
            max_drawdown=round(max_drawdown, 1),
        )

    def _get_risk_multiplier(self, report: Optional[SecurityReport]) -> float:
        """Get risk multiplier for trade sizing based on security."""
        if not report:
            return 1.5  # Conservative if unknown

        if report.risk_level == RiskLevel.LOW:
            return 1.0
        elif report.risk_level == RiskLevel.MEDIUM:
            return 1.25
        elif report.risk_level == RiskLevel.HIGH:
            return 1.5
        else:  # CRITICAL
            return 2.0

    def _score_liquidity(self, liquidity_usd: float) -> int:
        """Score liquidity (0-20 points)."""
        max_points = self._weights.liquidity

        if liquidity_usd < self.MIN_LIQUIDITY_USD:
            return 0

        if liquidity_usd >= self.IDEAL_LIQUIDITY_USD:
            return max_points

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

        if ratio < 0.1:
            return int(max_points * 0.2)
        elif ratio < self.IDEAL_VOLUME_RATIO:
            return int(max_points * (0.2 + 0.8 * (ratio / self.IDEAL_VOLUME_RATIO)))
        elif ratio <= 1.0:
            return max_points
        elif ratio <= self.MAX_VOLUME_RATIO:
            return int(max_points * 0.8)
        else:
            return int(max_points * 0.5)

    def _score_momentum(self, data: TokenData) -> int:
        """Score price momentum (0-25 points)."""
        max_points = self._weights.price_momentum
        score = 0

        if data.price_change_5m > 0:
            score += min(5, data.price_change_5m / 2)

        if data.price_change_1h > 0:
            score += min(8, data.price_change_1h / 1.5)

        if data.price_change_6h > 0:
            score += min(6, data.price_change_6h / 2)

        if data.price_change_24h > 0:
            score += min(6, data.price_change_24h / 3)

        if data.price_change_1h > 50:
            score *= 0.5

        return min(max_points, int(score))

    def _score_buy_pressure(self, data: TokenData) -> int:
        """Score buy pressure from transaction ratios (0-20 points)."""
        max_points = self._weights.buy_pressure

        def buy_ratio(buys: int, sells: int) -> float:
            total = buys + sells
            return buys / total if total > 0 else 0.5

        ratio_5m = buy_ratio(data.txns_buys_5m, data.txns_sells_5m)
        ratio_1h = buy_ratio(data.txns_buys_1h, data.txns_sells_1h)
        ratio_24h = buy_ratio(data.txns_buys_24h, data.txns_sells_24h)

        weighted_ratio = (ratio_5m * 0.4) + (ratio_1h * 0.35) + (ratio_24h * 0.25)

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

        timeframes = [
            data.price_change_5m,
            data.price_change_1h,
            data.price_change_6h,
            data.price_change_24h,
        ]

        positive_count = sum(1 for t in timeframes if t > 0)

        if positive_count == 4:
            score += 8
        elif positive_count == 3:
            score += 5
        elif positive_count == 2:
            score += 2

        if data.volume_1h > 0 and data.volume_24h > 0:
            hourly_avg_24h = data.volume_24h / 24
            if data.volume_1h > hourly_avg_24h * 1.5:
                score += 4
            elif data.volume_1h > hourly_avg_24h:
                score += 2

        total_txns_1h = data.txns_buys_1h + data.txns_sells_1h
        if total_txns_1h > 100:
            score += 3
        elif total_txns_1h > 50:
            score += 1

        return min(max_points, score)

    def _get_signal_strength(self, score: int, pop_score: int) -> str:
        """Get signal strength based on score and PoP."""
        combined = (score + pop_score) / 2

        if combined >= 80 and pop_score >= 65:
            return "STRONG"
        elif combined >= 65 and pop_score >= 50:
            return "MODERATE"
        elif combined >= 50:
            return "WEAK"
        else:
            return "NO SIGNAL"
