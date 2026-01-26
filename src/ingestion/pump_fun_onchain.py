"""
Pump.fun on-chain data reader.

Reads token data directly from Solana blockchain instead of pump.fun API.
This bypasses Cloudflare blocking issues.

Based on pump.fun program structure from pumpdotfun-sdk.
"""

import asyncio
import base64
import logging
import struct
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import httpx
from solders.pubkey import Pubkey

logger = logging.getLogger(__name__)

# Pump.fun program ID
PUMP_FUN_PROGRAM = Pubkey.from_string("6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P")

# Global state PDA seed
GLOBAL_SEED = b"global"

# Bonding curve PDA seed  
BONDING_CURVE_SEED = b"bonding-curve"


@dataclass
class PumpTokenOnChain:
    """Token data from on-chain accounts."""
    
    address: str
    bonding_curve: str
    creator: str
    virtual_token_reserves: int
    virtual_sol_reserves: int
    real_token_reserves: int
    real_sol_reserves: int
    token_total_supply: int
    complete: bool  # graduated to Raydium
    
    @property
    def market_cap_sol(self) -> float:
        """Estimate market cap in SOL."""
        if self.virtual_token_reserves == 0:
            return 0.0
        price_per_token = self.virtual_sol_reserves / self.virtual_token_reserves
        return price_per_token * self.token_total_supply / 1e9  # lamports to SOL
    
    def __repr__(self) -> str:
        status = "graduated" if self.complete else "active"
        return f"<PumpTokenOnChain {self.address[:8]}... {status}>"


class PumpFunOnChainClient:
    """
    Client for reading pump.fun data directly from Solana blockchain.
    
    This bypasses the pump.fun API which is blocked by Cloudflare.
    """
    
    def __init__(self, rpc_endpoint: str = "https://api.mainnet-beta.solana.com") -> None:
        """
        Initialize on-chain client.
        
        Args:
            rpc_endpoint: Solana RPC endpoint URL
        """
        self._rpc_endpoint = rpc_endpoint
        self._client: httpx.AsyncClient | None = None
    
    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(30.0),
                headers={"Content-Type": "application/json"},
            )
        return self._client
    
    async def close(self) -> None:
        """Close HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None
    
    async def _rpc_call(self, method: str, params: list[Any]) -> Any:
        """Make an RPC call to Solana."""
        client = await self._get_client()
        
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": method,
            "params": params,
        }
        
        try:
            response = await client.post(self._rpc_endpoint, json=payload)
            data = response.json()
            
            if "error" in data:
                logger.warning(f"RPC error: {data['error']}")
                return None
            
            return data.get("result")
            
        except Exception as e:
            logger.error(f"RPC call failed: {e}")
            return None
    
    def _get_bonding_curve_pda(self, mint: str) -> str:
        """
        Derive the bonding curve PDA for a token mint.
        
        Args:
            mint: Token mint address
            
        Returns:
            Bonding curve PDA address
        """
        mint_pubkey = Pubkey.from_string(mint)
        
        # PDA: ["bonding-curve", mint]
        pda, _ = Pubkey.find_program_address(
            [BONDING_CURVE_SEED, bytes(mint_pubkey)],
            PUMP_FUN_PROGRAM,
        )
        
        return str(pda)
    
    def _parse_bonding_curve_account(self, data: bytes, mint: str) -> PumpTokenOnChain | None:
        """
        Parse bonding curve account data.
        
        Account layout (from pumpdotfun-sdk):
        - 8 bytes: discriminator
        - 8 bytes: virtual_token_reserves (u64)
        - 8 bytes: virtual_sol_reserves (u64)
        - 8 bytes: real_token_reserves (u64)
        - 8 bytes: real_sol_reserves (u64)
        - 8 bytes: token_total_supply (u64)
        - 1 byte: complete (bool)
        - 32 bytes: creator (Pubkey)
        """
        try:
            if len(data) < 81:  # Minimum expected size
                logger.warning(f"Bonding curve data too short: {len(data)} bytes")
                return None
            
            # Skip 8-byte discriminator
            offset = 8
            
            virtual_token_reserves = struct.unpack_from("<Q", data, offset)[0]
            offset += 8
            
            virtual_sol_reserves = struct.unpack_from("<Q", data, offset)[0]
            offset += 8
            
            real_token_reserves = struct.unpack_from("<Q", data, offset)[0]
            offset += 8
            
            real_sol_reserves = struct.unpack_from("<Q", data, offset)[0]
            offset += 8
            
            token_total_supply = struct.unpack_from("<Q", data, offset)[0]
            offset += 8
            
            complete = data[offset] == 1
            offset += 1
            
            creator_bytes = data[offset:offset + 32]
            creator = str(Pubkey.from_bytes(creator_bytes))
            
            bonding_curve = self._get_bonding_curve_pda(mint)
            
            return PumpTokenOnChain(
                address=mint,
                bonding_curve=bonding_curve,
                creator=creator,
                virtual_token_reserves=virtual_token_reserves,
                virtual_sol_reserves=virtual_sol_reserves,
                real_token_reserves=real_token_reserves,
                real_sol_reserves=real_sol_reserves,
                token_total_supply=token_total_supply,
                complete=complete,
            )
            
        except Exception as e:
            logger.error(f"Failed to parse bonding curve: {e}")
            return None
    
    async def get_token_info(self, mint: str) -> PumpTokenOnChain | None:
        """
        Get token info from on-chain bonding curve account.
        
        Args:
            mint: Token mint address
            
        Returns:
            PumpTokenOnChain or None if not found
        """
        bonding_curve_pda = self._get_bonding_curve_pda(mint)
        
        result = await self._rpc_call(
            "getAccountInfo",
            [bonding_curve_pda, {"encoding": "base64"}],
        )
        
        if not result or not result.get("value"):
            return None
        
        data_b64 = result["value"]["data"][0]
        data = base64.b64decode(data_b64)
        
        return self._parse_bonding_curve_account(data, mint)
    
    async def get_recent_tokens(self, limit: int = 50) -> list[PumpTokenOnChain]:
        """
        Get recently created pump.fun tokens by scanning program accounts.
        
        Note: This is expensive on public RPC. Use sparingly or with paid RPC.
        
        Args:
            limit: Maximum tokens to return
            
        Returns:
            List of PumpTokenOnChain
        """
        # Get recent signatures for the pump.fun program
        result = await self._rpc_call(
            "getSignaturesForAddress",
            [str(PUMP_FUN_PROGRAM), {"limit": limit * 2}],  # Get more to filter
        )
        
        if not result:
            return []
        
        tokens: list[PumpTokenOnChain] = []
        seen_mints: set[str] = set()
        
        for sig_info in result:
            if len(tokens) >= limit:
                break
                
            signature = sig_info.get("signature")
            if not signature:
                continue
            
            # Get transaction details
            tx_result = await self._rpc_call(
                "getTransaction",
                [signature, {"encoding": "jsonParsed", "maxSupportedTransactionVersion": 0}],
            )
            
            if not tx_result:
                continue
            
            # Look for token mint in the transaction
            try:
                meta = tx_result.get("meta", {})
                post_token_balances = meta.get("postTokenBalances", [])
                
                for balance in post_token_balances:
                    mint = balance.get("mint")
                    if mint and mint not in seen_mints:
                        seen_mints.add(mint)
                        
                        # Get bonding curve info
                        token_info = await self.get_token_info(mint)
                        if token_info:
                            tokens.append(token_info)
                            logger.debug(f"Found pump.fun token: {mint[:8]}...")
                            
                            if len(tokens) >= limit:
                                break
                                
            except Exception as e:
                logger.debug(f"Error parsing transaction {signature[:8]}: {e}")
                continue
            
            # Small delay to avoid rate limits
            await asyncio.sleep(0.1)
        
        return tokens
    
    async def is_pump_fun_token(self, mint: str) -> bool:
        """
        Check if a token is a pump.fun token by looking for bonding curve.
        
        Args:
            mint: Token mint address
            
        Returns:
            True if pump.fun token
        """
        token_info = await self.get_token_info(mint)
        return token_info is not None
