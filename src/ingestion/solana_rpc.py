"""Solana RPC client for on-chain data."""

import logging
from dataclasses import dataclass

import base58
from solana.rpc.async_api import AsyncClient
from solana.rpc.commitment import Commitment
from solders.pubkey import Pubkey

from src.config import SolanaRpcConfig
from src.utils.key_rotator import KeyRotator


logger = logging.getLogger(__name__)

TOKEN_PROGRAM_ID = "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"
TOKEN_2022_PROGRAM_ID = "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb"
BURN_ADDRESS = "1nc1nerator11111111111111111111111111111111"


@dataclass
class MintInfo:
    """Token mint information."""

    mint_authority: str | None
    freeze_authority: str | None
    decimals: int
    supply: int
    is_token_2022: bool = False

    @property
    def mint_authority_active(self) -> bool:
        """Check if mint authority is active (not null or burn address)."""
        return self.mint_authority is not None and self.mint_authority != BURN_ADDRESS

    @property
    def freeze_authority_active(self) -> bool:
        """Check if freeze authority is active."""
        return self.freeze_authority is not None and self.freeze_authority != BURN_ADDRESS


@dataclass
class HolderInfo:
    """Token holder information."""

    wallet: str
    balance: int

    def __repr__(self) -> str:
        return f"<Holder {self.wallet[:8]}... balance={self.balance}>"


def is_valid_address(address: str) -> bool:
    """Validate a Solana base58 address."""
    try:
        decoded = base58.b58decode(address)
        return len(decoded) == 32
    except Exception:
        return False


class SolanaRpcClient:
    """Client for Solana RPC calls with optional key rotation."""

    # Base delay between RPC calls (adjusted based on key count)
    BASE_REQUEST_INTERVAL = 0.5  # 500ms for single key

    def __init__(self, config: SolanaRpcConfig) -> None:
        """
        Initialize Solana RPC client.

        Args:
            config: Solana RPC configuration
        """
        self._config = config
        self._client: AsyncClient | None = None
        self._last_request_time: float = 0
        
        # Initialize key rotator if multiple keys provided
        self._key_rotator: KeyRotator | None = None
        if config.helius_api_keys:
            self._key_rotator = KeyRotator(config.helius_api_keys)
            logger.info(
                f"Key rotation enabled with {self._key_rotator.key_count} keys "
                f"(effective rate: {self._key_rotator.key_count * 120}/min)"
            )

    @property
    def _request_interval(self) -> float:
        """Calculate request interval based on number of keys."""
        if self._key_rotator and self._key_rotator.key_count > 1:
            # Divide base interval by number of keys
            # With 7 keys: 500ms / 7 = ~71ms between requests
            return self.BASE_REQUEST_INTERVAL / self._key_rotator.key_count
        return self.BASE_REQUEST_INTERVAL

    async def _rate_limit(self) -> None:
        """Enforce minimum delay between requests."""
        import asyncio
        import time
        now = time.time()
        elapsed = now - self._last_request_time
        interval = self._request_interval
        if elapsed < interval:
            await asyncio.sleep(interval - elapsed)
        self._last_request_time = time.time()

    def _get_endpoint(self) -> str:
        """Get the next endpoint URL (with key rotation if enabled)."""
        if self._key_rotator:
            return self._key_rotator.get_endpoint(self._config.helius_base_url)
        return self._config.endpoint

    async def _get_client(self) -> AsyncClient:
        """Get RPC client with rotated endpoint."""
        # When using key rotation, always create a fresh client with the next key
        if self._key_rotator:
            endpoint = self._get_endpoint()
            return AsyncClient(
                endpoint,
                timeout=self._config.timeout_seconds,
            )
        
        # For single endpoint, reuse the client
        if self._client is None:
            self._client = AsyncClient(
                self._config.endpoint,
                timeout=self._config.timeout_seconds,
            )
        return self._client

    async def _close_client(self, client: AsyncClient) -> None:
        """Close a client if using rotation (fresh clients per request)."""
        if self._key_rotator:
            await client.close()

    async def close(self) -> None:
        """Close RPC client."""
        if self._client:
            await self._client.close()
            self._client = None

    async def get_mint_info(self, mint_address: str) -> MintInfo | None:
        """
        Get token mint information.

        Args:
            mint_address: Token mint address

        Returns:
            MintInfo or None if not found
        """
        if not is_valid_address(mint_address):
            logger.warning(f"Invalid mint address: {mint_address}")
            return None

        await self._rate_limit()
        client = await self._get_client()

        try:
            pubkey = Pubkey.from_string(mint_address)
            response = await client.get_account_info(
                pubkey,
                commitment=Commitment("confirmed"),
            )

            if not response.value:
                logger.debug(f"Mint account not found: {mint_address}")
                return None

            data = response.value.data
            owner = str(response.value.owner)

            is_token_2022 = owner == TOKEN_2022_PROGRAM_ID

            if isinstance(data, bytes) and len(data) >= 82:
                mint_authority_opt = data[0:4]
                has_mint_authority = mint_authority_opt[0] == 1

                mint_authority = None
                if has_mint_authority:
                    mint_authority = base58.b58encode(data[4:36]).decode()

                supply = int.from_bytes(data[36:44], "little")
                decimals = data[44]

                freeze_authority_opt = data[45:49]
                has_freeze_authority = freeze_authority_opt[0] == 1

                freeze_authority = None
                if has_freeze_authority:
                    freeze_authority = base58.b58encode(data[49:81]).decode()

                return MintInfo(
                    mint_authority=mint_authority,
                    freeze_authority=freeze_authority,
                    decimals=decimals,
                    supply=supply,
                    is_token_2022=is_token_2022,
                )

            logger.warning(f"Unexpected mint data format for {mint_address}")
            return None

        except Exception as e:
            logger.error(f"Failed to get mint info for {mint_address}: {e}")
            return None
        finally:
            await self._close_client(client)

    async def get_token_supply(self, mint_address: str) -> int | None:
        """
        Get total token supply.

        Args:
            mint_address: Token mint address

        Returns:
            Supply as raw integer or None
        """
        if not is_valid_address(mint_address):
            return None

        await self._rate_limit()
        client = await self._get_client()

        try:
            pubkey = Pubkey.from_string(mint_address)
            response = await client.get_token_supply(
                pubkey,
                commitment=Commitment("confirmed"),
            )

            if response.value:
                return int(response.value.amount)
            return None

        except Exception as e:
            logger.warning(f"Failed to get token supply for {mint_address}: {e}")
            mint_info = await self.get_mint_info(mint_address)
            return mint_info.supply if mint_info else None
        finally:
            await self._close_client(client)

    async def get_token_holders(
        self, mint_address: str, limit: int = 1000
    ) -> list[HolderInfo]:
        """
        Get token holders sorted by balance.

        Args:
            mint_address: Token mint address
            limit: Maximum number of holders to return

        Returns:
            List of HolderInfo sorted by balance descending
        """
        if not is_valid_address(mint_address):
            logger.warning(f"Invalid mint address: {mint_address}")
            return []

        await self._rate_limit()
        client = await self._get_client()

        try:
            pubkey = Pubkey.from_string(mint_address)
            response = await client.get_token_largest_accounts(
                pubkey,
                commitment=Commitment("confirmed"),
            )
        except Exception as e:
            logger.error(f"Failed to get largest accounts for {mint_address}: {e}")
            return []
        finally:
            await self._close_client(client)

        if not response.value:
            return []

        holders: list[HolderInfo] = []
        for account in response.value[:limit]:
            if account.amount and int(account.amount.amount) > 0:
                try:
                    # Get fresh client for each holder lookup (rotates keys)
                    await self._rate_limit()
                    holder_client = await self._get_client()
                    
                    try:
                        account_pubkey = Pubkey.from_string(str(account.address))
                        holder_response = await holder_client.get_account_info(
                            account_pubkey,
                            commitment=Commitment("confirmed"),
                        )

                        wallet = str(account.address)
                        if holder_response.value and holder_response.value.data:
                            data = holder_response.value.data
                            if isinstance(data, bytes) and len(data) >= 32:
                                wallet = base58.b58encode(data[32:64]).decode()

                        holders.append(
                            HolderInfo(
                                wallet=wallet,
                                balance=int(account.amount.amount),
                            )
                        )
                    finally:
                        await self._close_client(holder_client)
                except Exception as e:
                    logger.debug(f"Failed to get holder info for {account.address}: {e}")
                    # Still add the holder with token account address
                    holders.append(
                        HolderInfo(
                            wallet=str(account.address),
                            balance=int(account.amount.amount),
                        )
                    )

        holders.sort(key=lambda h: h.balance, reverse=True)
        return holders[:limit]

    async def get_recent_signatures(
        self, address: str, limit: int = 100
    ) -> list[str]:
        """
        Get recent transaction signatures for an address.

        Args:
            address: Account address
            limit: Maximum signatures to return

        Returns:
            List of transaction signatures
        """
        if not is_valid_address(address):
            return []

        await self._rate_limit()
        client = await self._get_client()

        try:
            response = await client.get_signatures_for_address(
                address,
                limit=limit,
                commitment=Commitment("confirmed"),
            )

            if not response.value:
                return []

            return [str(sig.signature) for sig in response.value]

        except Exception as e:
            logger.error(f"Failed to get signatures for {address}: {e}")
            return []
        finally:
            await self._close_client(client)
