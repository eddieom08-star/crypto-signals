"""Security checker for token risk analysis using RugCheck and on-chain data."""

import logging
from dataclasses import dataclass
from typing import Optional
from enum import Enum

import httpx

logger = logging.getLogger(__name__)


class RiskLevel(Enum):
    """Risk level classification."""
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


@dataclass(frozen=True)
class LiquidityLock:
    """Liquidity lock information."""
    is_locked: bool
    lock_percentage: float  # 0-100
    unlock_date: Optional[str]  # ISO date string
    locker_name: Optional[str]  # e.g., "Raydium", "Meteora"
    lock_duration_days: int


@dataclass(frozen=True)
class BundleAnalysis:
    """Bundle detection results."""
    is_bundled: bool
    bundle_percentage: float  # Percentage of supply in bundled wallets
    bundled_wallets_count: int
    deployer_holdings_pct: float
    top_10_holders_pct: float
    sniper_count: int  # Wallets that bought in first blocks


@dataclass(frozen=True)
class SecurityReport:
    """Complete security analysis report."""
    token_address: str
    risk_level: RiskLevel
    risk_score: int  # 0-100, lower is safer

    # Liquidity analysis
    liquidity_lock: LiquidityLock

    # Bundle analysis
    bundle_analysis: BundleAnalysis

    # Contract risks
    is_mintable: bool
    is_freezable: bool
    has_blacklist: bool
    is_mutable: bool  # Metadata can be changed

    # Trading risks
    buy_tax: float
    sell_tax: float
    max_buy_limit: Optional[float]

    # Audit status
    is_audited: bool
    audit_provider: Optional[str]

    # RugCheck specific
    rugcheck_score: Optional[int]
    rugcheck_risks: list[str]


class SecurityChecker:
    """Checks token security using multiple data sources."""

    RUGCHECK_API = "https://api.rugcheck.xyz/v1"
    SOLSCAN_API = "https://pro-api.solscan.io/v2.0"

    def __init__(self, timeout: int = 30) -> None:
        self._timeout = timeout

    async def analyze_token(self, token_address: str) -> Optional[SecurityReport]:
        """Perform comprehensive security analysis on a token."""
        try:
            # Fetch data from multiple sources in parallel
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                # RugCheck API
                rugcheck_data = await self._fetch_rugcheck(client, token_address)

                # Holder analysis for bundle detection
                holder_data = await self._analyze_holders(client, token_address)

                return self._build_report(token_address, rugcheck_data, holder_data)

        except Exception as e:
            logger.error(f"Security analysis failed for {token_address}: {e}")
            return None

    async def _fetch_rugcheck(self, client: httpx.AsyncClient, address: str) -> dict:
        """Fetch security data from RugCheck API."""
        try:
            response = await client.get(
                f"{self.RUGCHECK_API}/tokens/{address}/report"
            )
            if response.status_code == 200:
                return response.json()
            return {}
        except Exception as e:
            logger.warning(f"RugCheck API error: {e}")
            return {}

    async def _analyze_holders(self, client: httpx.AsyncClient, address: str) -> dict:
        """Analyze token holder distribution for bundle detection."""
        try:
            # Use DexScreener's holder data or fallback to estimation
            response = await client.get(
                f"https://api.dexscreener.com/latest/dex/tokens/{address}"
            )
            if response.status_code == 200:
                data = response.json()
                pairs = data.get("pairs", [])
                if pairs:
                    pair = pairs[0]
                    return {
                        "fdv": pair.get("fdv", 0),
                        "liquidity": pair.get("liquidity", {}).get("usd", 0),
                        "pair_created_at": pair.get("pairCreatedAt"),
                        "txns": pair.get("txns", {}),
                    }
            return {}
        except Exception as e:
            logger.warning(f"Holder analysis error: {e}")
            return {}

    def _build_report(
        self,
        address: str,
        rugcheck: dict,
        holder_data: dict
    ) -> SecurityReport:
        """Build security report from collected data."""

        # Parse RugCheck data
        risks = rugcheck.get("risks", [])
        risk_names = [r.get("name", "") for r in risks]
        rugcheck_score = rugcheck.get("score")

        # Detect lock status from RugCheck
        token_meta = rugcheck.get("tokenMeta", {})

        # Check for liquidity locks
        is_locked = any("lock" in r.lower() for r in risk_names) is False
        lock_info = self._parse_lock_info(rugcheck)

        # Bundle detection
        bundle_analysis = self._detect_bundles(rugcheck, holder_data)

        # Contract risks
        is_mintable = "Mintable" in risk_names or rugcheck.get("mintAuthority") is not None
        is_freezable = "Freezable" in risk_names or rugcheck.get("freezeAuthority") is not None
        has_blacklist = "Blacklist" in risk_names
        is_mutable = rugcheck.get("mutable", False)

        # Calculate overall risk score (0-100, lower is safer)
        risk_score = self._calculate_risk_score(
            rugcheck_score,
            lock_info,
            bundle_analysis,
            is_mintable,
            is_freezable,
            is_mutable
        )

        risk_level = self._get_risk_level(risk_score)

        return SecurityReport(
            token_address=address,
            risk_level=risk_level,
            risk_score=risk_score,
            liquidity_lock=lock_info,
            bundle_analysis=bundle_analysis,
            is_mintable=is_mintable,
            is_freezable=is_freezable,
            has_blacklist=has_blacklist,
            is_mutable=is_mutable,
            buy_tax=0.0,  # Solana tokens typically don't have transfer taxes
            sell_tax=0.0,
            max_buy_limit=None,
            is_audited=False,
            audit_provider=None,
            rugcheck_score=rugcheck_score,
            rugcheck_risks=risk_names,
        )

    def _parse_lock_info(self, rugcheck: dict) -> LiquidityLock:
        """Parse liquidity lock information from RugCheck data."""
        markets = rugcheck.get("markets", [])

        # Check if LP tokens are locked
        total_lp_locked_pct = 0.0
        locker_name = None

        for market in markets:
            lp_locked = market.get("lp", {}).get("lpLockedPct", 0)
            if lp_locked > total_lp_locked_pct:
                total_lp_locked_pct = lp_locked
                locker_name = market.get("marketType", "Unknown")

        is_locked = total_lp_locked_pct >= 50  # Consider locked if >50%

        return LiquidityLock(
            is_locked=is_locked,
            lock_percentage=total_lp_locked_pct,
            unlock_date=None,  # Would need additional API for exact date
            locker_name=locker_name if is_locked else None,
            lock_duration_days=0,
        )

    def _detect_bundles(self, rugcheck: dict, holder_data: dict) -> BundleAnalysis:
        """Detect if token was bundled during launch."""

        # Get top holder information from RugCheck
        top_holders = rugcheck.get("topHolders", [])

        # Calculate concentrations
        deployer_pct = 0.0
        top_10_pct = 0.0
        bundled_wallets = 0

        creator = rugcheck.get("creator", "")

        for i, holder in enumerate(top_holders[:10]):
            pct = holder.get("pct", 0)
            top_10_pct += pct

            # Check if holder is creator/deployer
            if holder.get("address") == creator:
                deployer_pct = pct

            # Detect potential bundle wallets (high concentration, early entry)
            if pct > 5 and i < 5:  # Top 5 holders with >5% each
                bundled_wallets += 1

        # Bundle detection heuristics:
        # - Multiple wallets with similar large holdings
        # - High concentration in top holders
        # - Deployer still holding significant amount
        is_bundled = (
            bundled_wallets >= 3 or
            deployer_pct > 10 or
            top_10_pct > 50
        )

        bundle_pct = top_10_pct if is_bundled else 0

        # Estimate sniper count from early transactions
        txns = holder_data.get("txns", {})
        buys_5m = txns.get("m5", {}).get("buys", 0)
        sniper_estimate = min(buys_5m, 50) if buys_5m > 20 else 0

        return BundleAnalysis(
            is_bundled=is_bundled,
            bundle_percentage=bundle_pct,
            bundled_wallets_count=bundled_wallets,
            deployer_holdings_pct=deployer_pct,
            top_10_holders_pct=top_10_pct,
            sniper_count=sniper_estimate,
        )

    def _calculate_risk_score(
        self,
        rugcheck_score: Optional[int],
        lock_info: LiquidityLock,
        bundle_analysis: BundleAnalysis,
        is_mintable: bool,
        is_freezable: bool,
        is_mutable: bool,
    ) -> int:
        """Calculate overall risk score (0-100, lower is safer)."""
        score = 0

        # RugCheck base score (inverted - they use higher = safer)
        if rugcheck_score is not None:
            # RugCheck: 0-1000, higher is better
            # Convert to 0-40 risk points, lower rugcheck = higher risk
            score += max(0, 40 - (rugcheck_score / 25))
        else:
            score += 20  # Unknown = moderate risk

        # Lock status (0-20 points)
        if not lock_info.is_locked:
            score += 15
        elif lock_info.lock_percentage < 80:
            score += 10
        elif lock_info.lock_percentage < 95:
            score += 5

        # Bundle risk (0-20 points)
        if bundle_analysis.is_bundled:
            score += 10
        if bundle_analysis.deployer_holdings_pct > 20:
            score += 5
        if bundle_analysis.top_10_holders_pct > 60:
            score += 5

        # Contract risks (0-20 points)
        if is_mintable:
            score += 8
        if is_freezable:
            score += 7
        if is_mutable:
            score += 5

        return min(100, int(score))

    def _get_risk_level(self, score: int) -> RiskLevel:
        """Convert risk score to risk level."""
        if score <= 25:
            return RiskLevel.LOW
        elif score <= 50:
            return RiskLevel.MEDIUM
        elif score <= 75:
            return RiskLevel.HIGH
        else:
            return RiskLevel.CRITICAL
