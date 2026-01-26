"""Pump.fun monitoring client."""

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import httpx


logger = logging.getLogger(__name__)


@dataclass
class PumpToken:
    """Token data from pump.fun."""

    address: str
    name: str
    symbol: str
    creator: str
    created_at: datetime
    market_cap: str | None = None
    graduated: bool = False
    image_uri: str | None = None
    description: str | None = None

    def __repr__(self) -> str:
        status = "graduated" if self.graduated else "active"
        return f"<PumpToken {self.symbol} ({self.address[:8]}...) {status}>"


class PumpFunClient:
    """
    Client for pump.fun data.

    Note: pump.fun may not have a public API. This implementation
    is a placeholder that can be updated when their API is available
    or replaced with web scraping if necessary.
    """

    BASE_URL = "https://frontend-api.pump.fun"

    def __init__(self) -> None:
        """Initialize pump.fun client."""
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(10.0),
                headers={
                    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                    "Accept": "application/json, text/plain, */*",
                    "Accept-Language": "en-US,en;q=0.9",
                    "Accept-Encoding": "gzip, deflate, br",
                    "Origin": "https://pump.fun",
                    "Referer": "https://pump.fun/",
                    "Sec-Ch-Ua": '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
                    "Sec-Ch-Ua-Mobile": "?0",
                    "Sec-Ch-Ua-Platform": '"macOS"',
                    "Sec-Fetch-Dest": "empty",
                    "Sec-Fetch-Mode": "cors",
                    "Sec-Fetch-Site": "same-site",
                },
            )
        return self._client

    async def close(self) -> None:
        """Close HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None

    async def _request(self, endpoint: str) -> dict[str, Any] | list[Any] | None:
        """Make an API request."""
        client = await self._get_client()
        url = f"{self.BASE_URL}{endpoint}"

        try:
            response = await client.get(url)

            if response.status_code != 200:
                logger.debug(f"Pump.fun API returned {response.status_code}")
                return None

            return response.json()

        except httpx.TimeoutException:
            logger.warning("Pump.fun request timeout")
            return None
        except httpx.RequestError as e:
            logger.warning(f"Pump.fun request error: {e}")
            return None
        except Exception as e:
            logger.warning(f"Pump.fun parse error: {e}")
            return None

    def _parse_token(self, data: dict[str, Any]) -> PumpToken | None:
        """Parse API response into PumpToken."""
        try:
            created_timestamp = data.get("created_timestamp", 0)
            if created_timestamp:
                created_at = datetime.fromtimestamp(created_timestamp / 1000)
            else:
                created_at = datetime.utcnow()

            return PumpToken(
                address=data.get("mint", data.get("address", "")),
                name=data.get("name", "Unknown"),
                symbol=data.get("symbol", "???"),
                creator=data.get("creator", ""),
                created_at=created_at,
                market_cap=str(data.get("usd_market_cap")) if data.get("usd_market_cap") else None,
                graduated=data.get("complete", False) or data.get("graduated", False),
                image_uri=data.get("image_uri"),
                description=data.get("description"),
            )
        except Exception as e:
            logger.warning(f"Failed to parse pump.fun token: {e}")
            return None

    async def get_recent_launches(self, limit: int = 50) -> list[PumpToken]:
        """
        Get recently launched tokens.

        Args:
            limit: Maximum tokens to return

        Returns:
            List of PumpToken
        """
        data = await self._request(f"/coins?offset=0&limit={limit}&sort=created_timestamp&order=DESC")

        if not data or not isinstance(data, list):
            logger.debug("No recent launches from pump.fun")
            return []

        tokens: list[PumpToken] = []
        for item in data:
            token = self._parse_token(item)
            if token:
                tokens.append(token)

        return tokens

    async def get_token_info(self, address: str) -> PumpToken | None:
        """
        Get info for a specific token.

        Args:
            address: Token mint address

        Returns:
            PumpToken or None
        """
        data = await self._request(f"/coins/{address}")

        if not data or not isinstance(data, dict):
            return None

        return self._parse_token(data)

    async def get_graduated(self, limit: int = 20) -> list[str]:
        """
        Get recently graduated token addresses.

        Args:
            limit: Maximum addresses to return

        Returns:
            List of token addresses that recently graduated
        """
        data = await self._request(f"/coins?offset=0&limit={limit}&sort=last_trade_timestamp&order=DESC&complete=true")

        if not data or not isinstance(data, list):
            return []

        return [item.get("mint", "") for item in data if item.get("mint")]

    async def get_king_of_the_hill(self) -> PumpToken | None:
        """
        Get the current "King of the Hill" token.

        Returns:
            Current top token or None
        """
        data = await self._request("/coins/king-of-the-hill")

        if not data or not isinstance(data, dict):
            return None

        return self._parse_token(data)
