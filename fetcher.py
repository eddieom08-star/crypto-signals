"""DEXScreener API client for fetching token data."""

import logging
from dataclasses import dataclass
from typing import Optional
import httpx

from config import Config, TokenConfig

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class TokenData:
    """Token market data from DEXScreener."""
    symbol: str
    address: str
    price_usd: float
    price_change_5m: float
    price_change_1h: float
    price_change_6h: float
    price_change_24h: float
    volume_5m: float
    volume_1h: float
    volume_6h: float
    volume_24h: float
    liquidity_usd: float
    txns_buys_5m: int
    txns_sells_5m: int
    txns_buys_1h: int
    txns_sells_1h: int
    txns_buys_24h: int
    txns_sells_24h: int
    fdv: float
    pair_address: str
    dex_id: str


class DEXScreenerClient:
    """Client for DEXScreener API."""

    def __init__(self, config: Config) -> None:
        self._base_url = config.dexscreener_base_url
        self._timeout = config.request_timeout

    async def fetch_token_data(self, token: TokenConfig) -> Optional[TokenData]:
        """Fetch token data from DEXScreener API."""
        url = f"{self._base_url}/tokens/{token.address}"

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.get(url)
                response.raise_for_status()
                data = response.json()

                if not data.get("pairs"):
                    logger.warning(f"No pairs found for {token.symbol}")
                    return None

                # Get the pair with highest liquidity
                pairs = data["pairs"]
                best_pair = max(pairs, key=lambda p: p.get("liquidity", {}).get("usd", 0))

                return self._parse_pair_data(token, best_pair)

        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error fetching {token.symbol}: {e.response.status_code}")
            return None
        except httpx.RequestError as e:
            logger.error(f"Request error fetching {token.symbol}: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error fetching {token.symbol}: {e}")
            return None

    def _parse_pair_data(self, token: TokenConfig, pair: dict) -> TokenData:
        """Parse DEXScreener pair data into TokenData."""
        price_change = pair.get("priceChange", {})
        volume = pair.get("volume", {})
        txns = pair.get("txns", {})
        liquidity = pair.get("liquidity", {})

        return TokenData(
            symbol=token.symbol,
            address=token.address,
            price_usd=float(pair.get("priceUsd", 0)),
            price_change_5m=float(price_change.get("m5", 0)),
            price_change_1h=float(price_change.get("h1", 0)),
            price_change_6h=float(price_change.get("h6", 0)),
            price_change_24h=float(price_change.get("h24", 0)),
            volume_5m=float(volume.get("m5", 0)),
            volume_1h=float(volume.get("h1", 0)),
            volume_6h=float(volume.get("h6", 0)),
            volume_24h=float(volume.get("h24", 0)),
            liquidity_usd=float(liquidity.get("usd", 0)),
            txns_buys_5m=int(txns.get("m5", {}).get("buys", 0)),
            txns_sells_5m=int(txns.get("m5", {}).get("sells", 0)),
            txns_buys_1h=int(txns.get("h1", {}).get("buys", 0)),
            txns_sells_1h=int(txns.get("h1", {}).get("sells", 0)),
            txns_buys_24h=int(txns.get("h24", {}).get("buys", 0)),
            txns_sells_24h=int(txns.get("h24", {}).get("sells", 0)),
            fdv=float(pair.get("fdv", 0)),
            pair_address=pair.get("pairAddress", ""),
            dex_id=pair.get("dexId", ""),
        )
