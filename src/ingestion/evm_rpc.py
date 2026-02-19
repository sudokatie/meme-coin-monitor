"""EVM RPC client for Base and Arbitrum chains."""

import logging
from abc import ABC
from dataclasses import dataclass
from typing import Any

import httpx


logger = logging.getLogger(__name__)


# ERC-20 ABI fragments for token info
ERC20_NAME_SIG = "0x06fdde03"
ERC20_SYMBOL_SIG = "0x95d89b41"
ERC20_DECIMALS_SIG = "0x313ce567"
ERC20_TOTAL_SUPPLY_SIG = "0x18160ddd"
ERC20_BALANCE_OF_SIG = "0x70a08231"


@dataclass
class EvmTokenInfo:
    """EVM token information."""

    name: str
    symbol: str
    decimals: int
    total_supply: int
    owner: str | None = None

    def __repr__(self) -> str:
        return f"<EvmToken {self.symbol} decimals={self.decimals}>"


@dataclass
class EvmHolderInfo:
    """EVM token holder information."""

    wallet: str
    balance: int

    def __repr__(self) -> str:
        return f"<Holder {self.wallet[:10]}... balance={self.balance}>"


def is_valid_evm_address(address: str) -> bool:
    """Validate an EVM hex address."""
    if not address.startswith("0x"):
        return False
    try:
        int(address, 16)
        return len(address) == 42
    except ValueError:
        return False


def decode_string_response(hex_data: str) -> str:
    """Decode a string from EVM call response."""
    if hex_data == "0x" or len(hex_data) < 66:
        return ""
    
    # Remove 0x prefix
    data = hex_data[2:]
    
    # Skip offset (32 bytes) and get length (32 bytes)
    if len(data) < 128:
        return ""
    
    length = int(data[64:128], 16)
    
    # Get string data
    string_data = data[128:128 + length * 2]
    
    try:
        return bytes.fromhex(string_data).decode("utf-8").strip("\x00")
    except Exception:
        return ""


def decode_uint256_response(hex_data: str) -> int:
    """Decode a uint256 from EVM call response."""
    if hex_data == "0x" or len(hex_data) < 3:
        return 0
    return int(hex_data, 16)


class EvmRpcClient(ABC):
    """Base client for EVM-compatible chain RPC calls."""

    CHAIN_NAME: str = "evm"
    BASE_REQUEST_INTERVAL: float = 0.2  # 200ms between requests

    def __init__(self, endpoint: str, timeout: float = 30.0) -> None:
        """
        Initialize EVM RPC client.

        Args:
            endpoint: RPC endpoint URL
            timeout: Request timeout in seconds
        """
        self._endpoint = endpoint
        self._timeout = timeout
        self._client: httpx.AsyncClient | None = None
        self._last_request_time: float = 0
        self._request_id: int = 0

    async def _rate_limit(self) -> None:
        """Enforce minimum delay between requests."""
        import asyncio
        import time
        
        now = time.time()
        elapsed = now - self._last_request_time
        if elapsed < self.BASE_REQUEST_INTERVAL:
            await asyncio.sleep(self.BASE_REQUEST_INTERVAL - elapsed)
        self._last_request_time = time.time()

    async def _get_client(self) -> httpx.AsyncClient:
        """Get HTTP client."""
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self._timeout)
        return self._client

    async def close(self) -> None:
        """Close HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None

    async def _call(self, method: str, params: list[Any]) -> Any:
        """Make JSON-RPC call."""
        await self._rate_limit()
        client = await self._get_client()
        
        self._request_id += 1
        payload = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params,
            "id": self._request_id,
        }
        
        try:
            response = await client.post(self._endpoint, json=payload)
            response.raise_for_status()
            result = response.json()
            
            if "error" in result:
                logger.error(f"RPC error: {result['error']}")
                return None
            
            return result.get("result")
        except Exception as e:
            logger.error(f"RPC call failed: {e}")
            return None

    async def eth_call(self, to: str, data: str, block: str = "latest") -> str | None:
        """Make eth_call."""
        result = await self._call("eth_call", [{"to": to, "data": data}, block])
        return result

    async def get_token_info(self, token_address: str) -> EvmTokenInfo | None:
        """
        Get ERC-20 token information.

        Args:
            token_address: Token contract address

        Returns:
            EvmTokenInfo or None if not found
        """
        if not is_valid_evm_address(token_address):
            logger.warning(f"Invalid EVM address: {token_address}")
            return None

        try:
            # Get name
            name_result = await self.eth_call(token_address, ERC20_NAME_SIG)
            name = decode_string_response(name_result or "0x") if name_result else "Unknown"

            # Get symbol
            symbol_result = await self.eth_call(token_address, ERC20_SYMBOL_SIG)
            symbol = decode_string_response(symbol_result or "0x") if symbol_result else "???"

            # Get decimals
            decimals_result = await self.eth_call(token_address, ERC20_DECIMALS_SIG)
            decimals = decode_uint256_response(decimals_result or "0x") if decimals_result else 18

            # Get total supply
            supply_result = await self.eth_call(token_address, ERC20_TOTAL_SUPPLY_SIG)
            total_supply = decode_uint256_response(supply_result or "0x") if supply_result else 0

            return EvmTokenInfo(
                name=name,
                symbol=symbol,
                decimals=decimals,
                total_supply=total_supply,
            )
        except Exception as e:
            logger.error(f"Failed to get token info for {token_address}: {e}")
            return None

    async def get_balance(self, token_address: str, wallet: str) -> int:
        """
        Get token balance for a wallet.

        Args:
            token_address: Token contract address
            wallet: Wallet address

        Returns:
            Balance as raw integer
        """
        if not is_valid_evm_address(token_address) or not is_valid_evm_address(wallet):
            return 0

        # balanceOf(address) call data
        padded_wallet = wallet[2:].lower().zfill(64)
        data = f"{ERC20_BALANCE_OF_SIG}{padded_wallet}"

        result = await self.eth_call(token_address, data)
        return decode_uint256_response(result or "0x") if result else 0

    async def get_block_number(self) -> int | None:
        """Get current block number."""
        result = await self._call("eth_blockNumber", [])
        return int(result, 16) if result else None


class BaseChainRpcClient(EvmRpcClient):
    """RPC client for Base chain (Coinbase L2)."""

    CHAIN_NAME = "base"
    # Base mainnet default RPC
    DEFAULT_ENDPOINT = "https://mainnet.base.org"

    def __init__(
        self,
        endpoint: str | None = None,
        timeout: float = 30.0,
    ) -> None:
        super().__init__(endpoint or self.DEFAULT_ENDPOINT, timeout)


class ArbitrumRpcClient(EvmRpcClient):
    """RPC client for Arbitrum One chain."""

    CHAIN_NAME = "arbitrum"
    # Arbitrum One default RPC
    DEFAULT_ENDPOINT = "https://arb1.arbitrum.io/rpc"

    def __init__(
        self,
        endpoint: str | None = None,
        timeout: float = 30.0,
    ) -> None:
        super().__init__(endpoint or self.DEFAULT_ENDPOINT, timeout)
