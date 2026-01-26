"""DEX Screener API client."""

import asyncio
import logging
import time
from typing import Any

import httpx

from src.config import DexScreenerConfig
from src.ingestion.base import BaseIngester, TokenData


logger = logging.getLogger(__name__)


class RateLimiter:
    """Rate limiter for API requests using semaphore and sliding window."""

    def __init__(self, requests_per_minute: int, max_concurrent: int = 5) -> None:
        self._requests_per_minute = requests_per_minute
        self._request_times: list[float] = []
        self._lock = asyncio.Lock()
        self._semaphore = asyncio.Semaphore(max_concurrent)

    async def acquire(self) -> None:
        """Wait until a request can be made within rate limits."""
        await self._semaphore.acquire()
        try:
            async with self._lock:
                now = time.time()
                window_start = now - 60

                self._request_times = [t for t in self._request_times if t > window_start]

                if len(self._request_times) >= self._requests_per_minute:
                    oldest = self._request_times[0]
                    wait_time = (oldest + 60) - now
                    if wait_time > 0:
                        logger.debug(f"Rate limit reached, waiting {wait_time:.2f}s")
                        await asyncio.sleep(wait_time)

                self._request_times.append(time.time())
        finally:
            self._semaphore.release()


class DexScreenerClient(BaseIngester):
    """Client for DEX Screener API."""

    DEFAULT_CHAIN = "solana"

    def __init__(self, config: DexScreenerConfig) -> None:
        """
        Initialize DEX Screener client.

        Args:
            config: DEX Screener configuration
        """
        self._config = config
        self._base_url = config.base_url.rstrip("/")
        self._rate_limiter = RateLimiter(config.rate_limit_per_minute)
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(10.0),
                limits=httpx.Limits(max_connections=10, max_keepalive_connections=5),
            )
        return self._client

    async def close(self) -> None:
        """Close HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None

    async def _request(self, endpoint: str) -> dict[str, Any] | None:
        """
        Make a rate-limited API request.

        Args:
            endpoint: API endpoint path

        Returns:
            JSON response or None on error
        """
        await self._rate_limiter.acquire()

        client = await self._get_client()
        url = f"{self._base_url}{endpoint}"

        try:
            response = await client.get(url)

            if response.status_code == 429:
                retry_after = int(response.headers.get("Retry-After", "60"))
                logger.warning(f"Rate limited by DEX Screener, waiting {retry_after}s")
                await asyncio.sleep(retry_after)
                return await self._request(endpoint)

            if response.status_code != 200:
                logger.warning(f"DEX Screener API error: {response.status_code}")
                return None

            return response.json()

        except httpx.TimeoutException:
            logger.warning(f"DEX Screener request timeout: {endpoint}")
            return None
        except httpx.RequestError as e:
            logger.warning(f"DEX Screener request error: {e}")
            return None

    def _parse_token_data(self, data: dict[str, Any]) -> TokenData | None:
        """Parse API response into TokenData."""
        if not data:
            return None

        try:
            base_token = data.get("baseToken", {})
            return TokenData(
                address=base_token.get("address", data.get("tokenAddress", "")),
                name=base_token.get("name", "Unknown"),
                symbol=base_token.get("symbol", "???"),
                price_usd=data.get("priceUsd"),
                market_cap=str(data.get("marketCap")) if data.get("marketCap") else None,
                volume_24h=str(data.get("volume", {}).get("h24")) if data.get("volume") else None,
                liquidity_usd=str(data.get("liquidity", {}).get("usd")) if data.get("liquidity") else None,
                pair_address=data.get("pairAddress"),
                dex=data.get("dexId"),
                raw_data=data,
            )
        except Exception as e:
            logger.warning(f"Failed to parse token data: {e}")
            return None

    async def fetch(self, address: str, chain: str | None = None) -> TokenData | None:
        """
        Fetch token data by address.

        Args:
            address: Token contract address
            chain: Blockchain (default: solana)

        Returns:
            TokenData if found, None otherwise
        """
        chain = chain or self.DEFAULT_CHAIN
        endpoint = f"/tokens/v1/{chain}/{address}"
        data = await self._request(endpoint)

        if not data:
            return None

        pairs = data if isinstance(data, list) else data.get("pairs", [])
        if not pairs:
            return None

        return self._parse_token_data(pairs[0])

    async def fetch_batch(
        self, addresses: list[str], chain: str | None = None
    ) -> list[TokenData]:
        """
        Fetch multiple tokens in one request.

        Args:
            addresses: List of token addresses (max 30)
            chain: Blockchain (default: solana)

        Returns:
            List of TokenData for found tokens
        """
        if not addresses:
            return []

        if len(addresses) > 30:
            logger.warning("Batch fetch limited to 30 addresses, truncating")
            addresses = addresses[:30]

        chain = chain or self.DEFAULT_CHAIN
        addresses_str = ",".join(addresses)
        endpoint = f"/tokens/v1/{chain}/{addresses_str}"
        data = await self._request(endpoint)

        if not data:
            return []

        results: list[TokenData] = []
        pairs = data if isinstance(data, list) else data.get("pairs", [])

        seen_addresses: set[str] = set()
        for pair in pairs:
            token_data = self._parse_token_data(pair)
            if token_data and token_data.address not in seen_addresses:
                results.append(token_data)
                seen_addresses.add(token_data.address)

        return results

    async def search(self, query: str) -> list[TokenData]:
        """
        Search for tokens by name or symbol.

        Args:
            query: Search query

        Returns:
            List of matching TokenData
        """
        endpoint = f"/latest/dex/search?q={query}"
        data = await self._request(endpoint)

        if not data:
            return []

        results: list[TokenData] = []
        pairs = data.get("pairs", [])

        for pair in pairs[:20]:
            token_data = self._parse_token_data(pair)
            if token_data:
                results.append(token_data)

        return results

    async def get_token_pairs(
        self, address: str, chain: str | None = None
    ) -> list[dict[str, Any]]:
        """
        Get all trading pairs for a token.

        Args:
            address: Token address
            chain: Blockchain (default: solana)

        Returns:
            List of pair data dicts
        """
        chain = chain or self.DEFAULT_CHAIN
        endpoint = f"/token-pairs/v1/{chain}/{address}"
        data = await self._request(endpoint)

        if not data:
            return []

        return data if isinstance(data, list) else data.get("pairs", [])
