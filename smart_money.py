"""Smart money tracking using Birdeye, Solscan, and Arkham APIs."""

import logging
import os
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional

import httpx

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class WhaleActivity:
    """Whale wallet activity summary."""
    whale_buys_24h: int
    whale_sells_24h: int
    whale_net_flow: float  # Positive = accumulation
    large_txns_count: int  # Transactions > $10k
    smart_money_holding: float  # % held by known smart money


@dataclass(frozen=True)
class HolderAnalysis:
    """Token holder distribution analysis."""
    total_holders: int
    holder_change_24h: int  # New holders in 24h
    holder_change_pct: float
    top_10_concentration: float  # % held by top 10
    fresh_wallet_pct: float  # % of buyers from fresh wallets
    avg_hold_time_hours: float
    diamond_hands_pct: float  # Holders > 7 days


@dataclass(frozen=True)
class TopTraderSignal:
    """Signals from top profitable traders."""
    top_traders_buying: int  # Top 100 PnL traders buying
    top_traders_selling: int
    avg_trader_pnl: float  # Average PnL of traders in this token
    profitable_holder_pct: float  # % of holders in profit


@dataclass(frozen=True)
class SmartMoneyReport:
    """Combined smart money analysis."""
    token_address: str
    whale_activity: WhaleActivity
    holder_analysis: HolderAnalysis
    trader_signals: TopTraderSignal
    smart_money_score: int  # 0-100
    signal: str  # ACCUMULATION, DISTRIBUTION, NEUTRAL
    confidence: str  # HIGH, MEDIUM, LOW


class BirdeyeClient:
    """Birdeye API client for Solana token data."""

    BASE_URL = "https://public-api.birdeye.so"

    def __init__(self, api_key: Optional[str] = None) -> None:
        self._api_key = api_key or os.environ.get("BIRDEYE_API_KEY", "")
        self._headers = {
            "X-API-KEY": self._api_key,
            "x-chain": "solana",
        }

    async def get_token_overview(self, address: str) -> dict:
        """Get token overview including holder stats."""
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                response = await client.get(
                    f"{self.BASE_URL}/defi/token_overview",
                    params={"address": address},
                    headers=self._headers,
                )
                if response.status_code == 200:
                    return response.json().get("data", {})
                return {}
        except Exception as e:
            logger.warning(f"Birdeye token_overview error: {e}")
            return {}

    async def get_token_security(self, address: str) -> dict:
        """Get token security info including holder concentration."""
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                response = await client.get(
                    f"{self.BASE_URL}/defi/token_security",
                    params={"address": address},
                    headers=self._headers,
                )
                if response.status_code == 200:
                    return response.json().get("data", {})
                return {}
        except Exception as e:
            logger.warning(f"Birdeye token_security error: {e}")
            return {}

    async def get_top_traders(self, address: str) -> list:
        """Get top traders for a token."""
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                response = await client.get(
                    f"{self.BASE_URL}/defi/v2/tokens/top_traders",
                    params={"address": address, "time_frame": "24h"},
                    headers=self._headers,
                )
                if response.status_code == 200:
                    return response.json().get("data", {}).get("traders", [])
                return []
        except Exception as e:
            logger.warning(f"Birdeye top_traders error: {e}")
            return []

    async def get_price_volume(self, address: str) -> dict:
        """Get price and volume data."""
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                response = await client.get(
                    f"{self.BASE_URL}/defi/price_volume/single",
                    params={"address": address, "type": "24h"},
                    headers=self._headers,
                )
                if response.status_code == 200:
                    return response.json().get("data", {})
                return {}
        except Exception as e:
            logger.warning(f"Birdeye price_volume error: {e}")
            return {}


class SolscanClient:
    """Solscan API client for holder and transaction data."""

    BASE_URL = "https://pro-api.solscan.io/v2.0"

    def __init__(self, api_key: Optional[str] = None) -> None:
        self._api_key = api_key or os.environ.get("SOLSCAN_API_KEY", "")
        self._headers = {"token": self._api_key} if self._api_key else {}

    async def get_token_holders(self, address: str, limit: int = 20) -> list:
        """Get top token holders."""
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                response = await client.get(
                    f"{self.BASE_URL}/token/holders",
                    params={"address": address, "page": 1, "page_size": limit},
                    headers=self._headers,
                )
                if response.status_code == 200:
                    return response.json().get("data", [])
                return []
        except Exception as e:
            logger.warning(f"Solscan holders error: {e}")
            return []

    async def get_token_meta(self, address: str) -> dict:
        """Get token metadata including holder count."""
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                response = await client.get(
                    f"{self.BASE_URL}/token/meta",
                    params={"address": address},
                    headers=self._headers,
                )
                if response.status_code == 200:
                    return response.json().get("data", {})
                return {}
        except Exception as e:
            logger.warning(f"Solscan meta error: {e}")
            return {}

    async def get_token_transfer(self, address: str, limit: int = 50) -> list:
        """Get recent token transfers to detect whale movements."""
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                response = await client.get(
                    f"{self.BASE_URL}/token/transfer",
                    params={"address": address, "page": 1, "page_size": limit},
                    headers=self._headers,
                )
                if response.status_code == 200:
                    return response.json().get("data", [])
                return []
        except Exception as e:
            logger.warning(f"Solscan transfer error: {e}")
            return []


class ArkhamClient:
    """Arkham Intelligence API client for entity tracking."""

    BASE_URL = "https://api.arkhamintelligence.com"

    def __init__(self, api_key: Optional[str] = None) -> None:
        self._api_key = api_key or os.environ.get("ARKHAM_API_KEY", "")
        self._headers = {"API-Key": self._api_key} if self._api_key else {}

    async def get_address_label(self, address: str) -> Optional[str]:
        """Get entity label for an address if known."""
        if not self._api_key:
            return None

        try:
            async with httpx.AsyncClient(timeout=15) as client:
                response = await client.get(
                    f"{self.BASE_URL}/intelligence/address/{address}",
                    headers=self._headers,
                )
                if response.status_code == 200:
                    data = response.json()
                    return data.get("arkhamEntity", {}).get("name")
                return None
        except Exception as e:
            logger.warning(f"Arkham label error: {e}")
            return None

    async def check_smart_money(self, addresses: list[str]) -> dict[str, bool]:
        """Check if addresses are known smart money / institutions."""
        results = {}
        known_smart_money_keywords = [
            "fund", "capital", "ventures", "trading", "whale",
            "institution", "market maker", "mm", "hedge"
        ]

        for addr in addresses[:10]:  # Limit API calls
            label = await self.get_address_label(addr)
            if label:
                is_smart = any(kw in label.lower() for kw in known_smart_money_keywords)
                results[addr] = is_smart
            else:
                results[addr] = False

        return results


class SmartMoneyTracker:
    """Combines multiple data sources for smart money analysis."""

    # Thresholds
    WHALE_TXN_THRESHOLD_USD = 10_000
    LARGE_HOLDER_THRESHOLD_PCT = 1.0  # 1% of supply = large holder
    FRESH_WALLET_AGE_HOURS = 24

    def __init__(self) -> None:
        self._birdeye = BirdeyeClient()
        self._solscan = SolscanClient()
        self._arkham = ArkhamClient()

    async def analyze(self, token_address: str) -> Optional[SmartMoneyReport]:
        """Perform comprehensive smart money analysis."""
        try:
            # Fetch data from all sources in parallel
            birdeye_overview = await self._birdeye.get_token_overview(token_address)
            birdeye_security = await self._birdeye.get_token_security(token_address)
            top_traders = await self._birdeye.get_top_traders(token_address)
            solscan_holders = await self._solscan.get_token_holders(token_address)
            solscan_meta = await self._solscan.get_token_meta(token_address)

            # Analyze whale activity
            whale_activity = self._analyze_whale_activity(
                birdeye_overview,
                solscan_holders
            )

            # Analyze holder distribution
            holder_analysis = self._analyze_holders(
                birdeye_security,
                solscan_meta,
                solscan_holders
            )

            # Analyze top trader signals
            trader_signals = self._analyze_traders(top_traders)

            # Calculate smart money score
            score, signal, confidence = self._calculate_score(
                whale_activity,
                holder_analysis,
                trader_signals
            )

            return SmartMoneyReport(
                token_address=token_address,
                whale_activity=whale_activity,
                holder_analysis=holder_analysis,
                trader_signals=trader_signals,
                smart_money_score=score,
                signal=signal,
                confidence=confidence,
            )

        except Exception as e:
            logger.error(f"Smart money analysis failed: {e}")
            return None

    def _analyze_whale_activity(
        self,
        overview: dict,
        holders: list
    ) -> WhaleActivity:
        """Analyze whale buying/selling activity."""
        # Extract from Birdeye overview
        buy_24h = overview.get("buy24h", 0)
        sell_24h = overview.get("sell24h", 0)

        # Count large holders (whales)
        whale_count = 0
        for holder in holders:
            pct = holder.get("amount_percentage", 0)
            if pct >= self.LARGE_HOLDER_THRESHOLD_PCT:
                whale_count += 1

        # Estimate whale activity from trade data
        trade_24h = overview.get("trade24h", 0)
        volume_24h = overview.get("v24hUSD", 0)

        # Large transactions estimate
        avg_txn_size = volume_24h / trade_24h if trade_24h > 0 else 0
        large_txn_estimate = int(trade_24h * 0.1) if avg_txn_size > 1000 else 0

        # Net flow (buys - sells in USD)
        buy_volume = overview.get("vBuy24hUSD", 0)
        sell_volume = overview.get("vSell24hUSD", 0)
        net_flow = buy_volume - sell_volume

        # Smart money holding estimate
        top_10_pct = sum(
            h.get("amount_percentage", 0)
            for h in holders[:10]
        )

        return WhaleActivity(
            whale_buys_24h=buy_24h,
            whale_sells_24h=sell_24h,
            whale_net_flow=net_flow,
            large_txns_count=large_txn_estimate,
            smart_money_holding=min(top_10_pct, 100),
        )

    def _analyze_holders(
        self,
        security: dict,
        meta: dict,
        holders: list
    ) -> HolderAnalysis:
        """Analyze holder distribution and behavior."""
        # Total holders
        total_holders = meta.get("holder", 0) or security.get("holderCount", 0)

        # Top 10 concentration
        top_10_pct = security.get("top10HolderPercent", 0)
        if not top_10_pct and holders:
            top_10_pct = sum(h.get("amount_percentage", 0) for h in holders[:10])

        # Holder change (estimate from Birdeye data)
        holder_change = security.get("holderChange24h", 0)
        holder_change_pct = (holder_change / total_holders * 100) if total_holders > 0 else 0

        # Fresh wallet analysis (simplified - would need more data for accuracy)
        fresh_wallet_pct = min(20, max(5, holder_change_pct * 2)) if holder_change > 0 else 10

        # Average hold time and diamond hands (estimates)
        avg_hold_time = 48.0  # Default estimate
        diamond_hands = 30.0  # Default estimate

        return HolderAnalysis(
            total_holders=total_holders,
            holder_change_24h=holder_change,
            holder_change_pct=round(holder_change_pct, 2),
            top_10_concentration=round(top_10_pct, 2),
            fresh_wallet_pct=round(fresh_wallet_pct, 2),
            avg_hold_time_hours=avg_hold_time,
            diamond_hands_pct=diamond_hands,
        )

    def _analyze_traders(self, traders: list) -> TopTraderSignal:
        """Analyze signals from top traders."""
        if not traders:
            return TopTraderSignal(
                top_traders_buying=0,
                top_traders_selling=0,
                avg_trader_pnl=0,
                profitable_holder_pct=50,
            )

        buying = 0
        selling = 0
        total_pnl = 0
        profitable = 0

        for trader in traders[:100]:
            # Check if trader is net buyer or seller
            volume_buy = trader.get("volumeBuy", 0)
            volume_sell = trader.get("volumeSell", 0)

            if volume_buy > volume_sell:
                buying += 1
            elif volume_sell > volume_buy:
                selling += 1

            # PnL analysis
            pnl = trader.get("pnl", 0)
            total_pnl += pnl
            if pnl > 0:
                profitable += 1

        avg_pnl = total_pnl / len(traders) if traders else 0
        profitable_pct = (profitable / len(traders) * 100) if traders else 50

        return TopTraderSignal(
            top_traders_buying=buying,
            top_traders_selling=selling,
            avg_trader_pnl=round(avg_pnl, 2),
            profitable_holder_pct=round(profitable_pct, 2),
        )

    def _calculate_score(
        self,
        whale: WhaleActivity,
        holders: HolderAnalysis,
        traders: TopTraderSignal
    ) -> tuple[int, str, str]:
        """Calculate overall smart money score and signal."""
        score = 50  # Start neutral

        # Whale activity signals (+/- 20 points)
        if whale.whale_net_flow > 0:
            score += min(15, whale.whale_net_flow / 10000)  # Positive flow = bullish
        else:
            score += max(-15, whale.whale_net_flow / 10000)

        buy_ratio = whale.whale_buys_24h / (whale.whale_buys_24h + whale.whale_sells_24h + 1)
        if buy_ratio > 0.6:
            score += 10
        elif buy_ratio < 0.4:
            score -= 10

        # Holder growth signals (+/- 15 points)
        if holders.holder_change_24h > 100:
            score += 10
        elif holders.holder_change_24h > 50:
            score += 5
        elif holders.holder_change_24h < -50:
            score -= 10

        # Concentration risk (-10 points max)
        if holders.top_10_concentration > 70:
            score -= 10
        elif holders.top_10_concentration > 50:
            score -= 5

        # Fresh wallet risk (-5 points)
        if holders.fresh_wallet_pct > 30:
            score -= 5

        # Top trader signals (+/- 15 points)
        if traders.top_traders_buying > traders.top_traders_selling * 1.5:
            score += 15
        elif traders.top_traders_selling > traders.top_traders_buying * 1.5:
            score -= 15

        if traders.profitable_holder_pct > 60:
            score += 5
        elif traders.profitable_holder_pct < 40:
            score -= 5

        # Clamp score
        score = max(0, min(100, score))

        # Determine signal
        if score >= 65:
            signal = "ACCUMULATION"
        elif score <= 35:
            signal = "DISTRIBUTION"
        else:
            signal = "NEUTRAL"

        # Determine confidence
        data_quality = sum([
            1 if whale.whale_buys_24h > 0 else 0,
            1 if holders.total_holders > 0 else 0,
            1 if traders.top_traders_buying + traders.top_traders_selling > 0 else 0,
        ])

        if data_quality >= 3 and (score >= 70 or score <= 30):
            confidence = "HIGH"
        elif data_quality >= 2:
            confidence = "MEDIUM"
        else:
            confidence = "LOW"

        return score, signal, confidence
