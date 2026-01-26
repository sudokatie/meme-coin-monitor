"""Base classes for data ingestion."""

import asyncio
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


logger = logging.getLogger(__name__)


@dataclass
class TokenData:
    """Normalized token data from any source."""

    address: str
    name: str
    symbol: str
    price_usd: str | None = None
    market_cap: str | None = None
    volume_24h: str | None = None
    liquidity_usd: str | None = None
    holder_count: int | None = None
    pair_address: str | None = None
    dex: str | None = None
    created_at: datetime | None = None
    raw_data: dict[str, Any] = field(default_factory=dict)

    def __repr__(self) -> str:
        return f"<TokenData {self.symbol} ({self.address[:8]}...) ${self.price_usd}>"


class BaseIngester(ABC):
    """Abstract base class for data ingesters."""

    MAX_RETRIES: int = 3
    RETRY_DELAY_SECONDS: float = 1.0

    @abstractmethod
    async def fetch(self, address: str) -> TokenData | None:
        """
        Fetch token data by address.

        Args:
            address: Token contract address

        Returns:
            TokenData if found, None otherwise
        """
        pass

    async def fetch_with_retry(self, address: str) -> TokenData | None:
        """
        Fetch with automatic retry on failure.

        Args:
            address: Token contract address

        Returns:
            TokenData if found, None otherwise
        """
        last_error: Exception | None = None

        for attempt in range(self.MAX_RETRIES):
            try:
                return await self.fetch(address)
            except Exception as e:
                last_error = e
                delay = self.RETRY_DELAY_SECONDS * (2 ** attempt)
                logger.warning(
                    f"Fetch attempt {attempt + 1}/{self.MAX_RETRIES} failed: {e}. "
                    f"Retrying in {delay}s"
                )
                await asyncio.sleep(delay)

        logger.error(f"All fetch attempts failed for {address}: {last_error}")
        return None
