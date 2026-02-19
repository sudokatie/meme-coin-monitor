"""Ingestion scheduler for coordinating data fetching."""

import asyncio
import logging
from datetime import datetime
from typing import Awaitable, Callable

from src.config import IngestionConfig
from src.ingestion.base import TokenData
from src.ingestion.dex_screener import DexScreenerClient
from src.ingestion.evm_rpc import ArbitrumRpcClient, BaseChainRpcClient
from src.ingestion.pump_fun import PumpFunClient


logger = logging.getLogger(__name__)

AnalysisCallback = Callable[[str, TokenData], Awaitable[None]]

# DexScreener chain identifiers
CHAIN_IDS = {
    "solana": "solana",
    "base": "base",
    "arbitrum": "arbitrum",
}


class IngestionScheduler:
    """Coordinates data fetching from multiple sources."""

    def __init__(
        self,
        config: IngestionConfig,
        dex_client: DexScreenerClient,
        pump_client: PumpFunClient,
        base_client: BaseChainRpcClient | None = None,
        arbitrum_client: ArbitrumRpcClient | None = None,
        on_token_data: AnalysisCallback | None = None,
    ) -> None:
        """
        Initialize scheduler.

        Args:
            config: Ingestion configuration
            dex_client: DEX Screener client
            pump_client: Pump.fun client
            base_client: Base chain RPC client (optional)
            arbitrum_client: Arbitrum RPC client (optional)
            on_token_data: Callback when new token data is received
        """
        self._config = config
        self._dex_client = dex_client
        self._pump_client = pump_client
        self._base_client = base_client
        self._arbitrum_client = arbitrum_client
        self._on_token_data = on_token_data

        self._watchlist: set[str] = set()
        self._seen_tokens: set[str] = set()
        # Track seen tokens per chain
        self._seen_tokens_by_chain: dict[str, set[str]] = {
            "solana": set(),
            "base": set(),
            "arbitrum": set(),
        }
        self._running = False
        self._tasks: list[asyncio.Task[None]] = []

    @property
    def watchlist(self) -> set[str]:
        """Get current watchlist."""
        return self._watchlist.copy()

    def add_to_watchlist(self, address: str) -> None:
        """Add a token to the watchlist."""
        self._watchlist.add(address)
        logger.info(f"Added {address[:8]}... to watchlist")

    def remove_from_watchlist(self, address: str) -> None:
        """Remove a token from the watchlist."""
        self._watchlist.discard(address)
        logger.info(f"Removed {address[:8]}... from watchlist")

    async def _notify(self, token_address: str, data: TokenData) -> None:
        """Notify callback of new token data."""
        if self._on_token_data:
            try:
                await self._on_token_data(token_address, data)
            except Exception as e:
                logger.error(f"Analysis callback error for {token_address}: {e}")

    async def _poll_watchlist(self) -> None:
        """Poll DEX Screener for watched tokens."""
        logger.info("Starting watchlist polling loop")

        while self._running:
            try:
                if self._watchlist:
                    addresses = list(self._watchlist)
                    logger.debug(f"Polling {len(addresses)} watched tokens")

                    for i in range(0, len(addresses), 30):
                        batch = addresses[i:i + 30]
                        tokens = await self._dex_client.fetch_batch(batch)

                        for token in tokens:
                            await self._notify(token.address, token)

                await asyncio.sleep(self._config.dex_screener.poll_interval_seconds)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Watchlist poll error: {e}")
                await asyncio.sleep(5)

        logger.info("Watchlist polling loop stopped")

    async def _poll_new_launches(self) -> None:
        """Poll pump.fun for new token launches."""
        if not self._config.pump_fun.enabled:
            logger.info("Pump.fun polling disabled")
            return

        logger.info("Starting pump.fun polling loop")

        while self._running:
            try:
                launches = await self._pump_client.get_recent_launches(limit=50)

                for launch in launches:
                    if launch.address not in self._seen_tokens:
                        self._seen_tokens.add(launch.address)
                        logger.info(f"New token detected: {launch.symbol} ({launch.address[:8]}...)")

                        token_data = await self._dex_client.fetch(launch.address)
                        if token_data:
                            await self._notify(launch.address, token_data)

                if len(self._seen_tokens) > 10000:
                    self._seen_tokens = set(list(self._seen_tokens)[-5000:])

                await asyncio.sleep(self._config.pump_fun.poll_interval_seconds)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Pump.fun poll error: {e}")
                await asyncio.sleep(10)

        logger.info("Pump.fun polling loop stopped")

    async def _poll_dex_discovery(self) -> None:
        """Poll DexScreener for new token discovery via boosts and profiles."""
        if not self._config.dex_screener.enabled:
            logger.info("DexScreener discovery disabled")
            return

        logger.info("Starting DexScreener discovery loop")
        poll_interval = self._config.dex_screener.poll_interval_seconds

        # Rate limiting: max tokens per cycle and delay between each
        # These can be increased via config when using multiple API keys
        max_tokens_per_cycle = self._config.max_tokens_per_cycle
        delay_between_tokens = self._config.token_processing_delay
        
        logger.info(f"Discovery settings: max_tokens={max_tokens_per_cycle}, delay={delay_between_tokens}s")

        while self._running:
            try:
                # Get trending tokens from boosts
                boost_addresses = await self._dex_client.get_latest_boosts()
                # Get newly profiled tokens
                profile_addresses = await self._dex_client.get_latest_profiles()

                # Combine and dedupe
                all_addresses = set(boost_addresses + profile_addresses)
                new_addresses = [a for a in all_addresses if a not in self._seen_tokens]

                if new_addresses:
                    # Limit how many we process per cycle to avoid rate limiting
                    to_process = new_addresses[:max_tokens_per_cycle]
                    logger.info(f"Discovered {len(new_addresses)} new tokens, processing {len(to_process)}")

                    # Mark all as seen to avoid reprocessing next cycle
                    for addr in new_addresses:
                        self._seen_tokens.add(addr)

                    # Fetch and analyze with delays
                    tokens = await self._dex_client.fetch_batch(to_process)

                    for token in tokens:
                        logger.info(f"New token: {token.symbol} ({token.address[:8]}...)")
                        await self._notify(token.address, token)
                        # Delay between tokens to avoid Helius rate limiting
                        await asyncio.sleep(delay_between_tokens)

                # Cap seen tokens to prevent memory bloat
                if len(self._seen_tokens) > 10000:
                    self._seen_tokens = set(list(self._seen_tokens)[-5000:])

                await asyncio.sleep(poll_interval)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"DexScreener discovery error: {e}")
                await asyncio.sleep(10)

        logger.info("DexScreener discovery loop stopped")

    async def _poll_evm_chain_discovery(self, chain: str) -> None:
        """
        Poll DexScreener for new tokens on an EVM chain.

        Args:
            chain: Chain identifier (base, arbitrum)
        """
        if chain not in CHAIN_IDS:
            logger.error(f"Unknown chain: {chain}")
            return

        logger.info(f"Starting {chain} discovery loop")
        poll_interval = self._config.dex_screener.poll_interval_seconds * 2  # Less aggressive for EVM
        max_tokens_per_cycle = self._config.max_tokens_per_cycle // 2  # Fewer tokens for EVM
        delay_between_tokens = self._config.token_processing_delay

        while self._running:
            try:
                # Use DexScreener search for trending tokens on this chain
                # Note: boosts/profiles are Solana-focused, so we use search
                search_terms = ["meme", "pepe", "doge", "shib", "moon", "inu"]
                all_addresses: set[str] = set()

                for term in search_terms[:2]:  # Limit searches per cycle
                    results = await self._dex_client.search(term)
                    for token in results:
                        if token.chain == chain:
                            all_addresses.add(token.address)

                # Filter to new tokens
                seen = self._seen_tokens_by_chain.get(chain, set())
                new_addresses = [a for a in all_addresses if a not in seen]

                if new_addresses:
                    to_process = new_addresses[:max_tokens_per_cycle]
                    logger.info(f"[{chain}] Discovered {len(new_addresses)} tokens, processing {len(to_process)}")

                    # Mark as seen
                    for addr in new_addresses:
                        self._seen_tokens_by_chain[chain].add(addr)

                    # Fetch and analyze
                    tokens = await self._dex_client.fetch_batch(to_process, chain=chain)

                    for token in tokens:
                        logger.info(f"[{chain}] New token: {token.symbol} ({token.address[:10]}...)")
                        await self._notify(token.address, token)
                        await asyncio.sleep(delay_between_tokens)

                # Cap seen tokens
                if len(self._seen_tokens_by_chain[chain]) > 5000:
                    self._seen_tokens_by_chain[chain] = set(
                        list(self._seen_tokens_by_chain[chain])[-2500:]
                    )

                await asyncio.sleep(poll_interval)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"[{chain}] Discovery error: {e}")
                await asyncio.sleep(10)

        logger.info(f"{chain} discovery loop stopped")

    async def start(self) -> None:
        """Start the scheduler."""
        if self._running:
            logger.warning("Scheduler already running")
            return

        logger.info("Starting ingestion scheduler")
        self._running = True

        if self._config.dex_screener.enabled:
            # Watchlist polling for manually added tokens
            task = asyncio.create_task(self._poll_watchlist())
            self._tasks.append(task)
            # Auto-discovery via DexScreener boosts/profiles (Solana)
            task = asyncio.create_task(self._poll_dex_discovery())
            self._tasks.append(task)

        if self._config.pump_fun.enabled:
            task = asyncio.create_task(self._poll_new_launches())
            self._tasks.append(task)

        # Start EVM chain discovery if enabled
        if self._config.base_chain.enabled:
            logger.info("Base chain monitoring enabled")
            task = asyncio.create_task(self._poll_evm_chain_discovery("base"))
            self._tasks.append(task)

        if self._config.arbitrum_chain.enabled:
            logger.info("Arbitrum chain monitoring enabled")
            task = asyncio.create_task(self._poll_evm_chain_discovery("arbitrum"))
            self._tasks.append(task)

        logger.info(f"Scheduler started with {len(self._tasks)} polling tasks")

    async def stop(self) -> None:
        """Stop the scheduler gracefully."""
        if not self._running:
            return

        logger.info("Stopping ingestion scheduler")
        self._running = False

        for task in self._tasks:
            task.cancel()

        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)

        self._tasks.clear()
        logger.info("Scheduler stopped")

    async def fetch_single(self, address: str) -> TokenData | None:
        """
        Fetch data for a single token on-demand.

        Args:
            address: Token address

        Returns:
            TokenData or None
        """
        return await self._dex_client.fetch(address)
