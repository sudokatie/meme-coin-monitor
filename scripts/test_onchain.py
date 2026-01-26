#!/usr/bin/env python3
"""Test the on-chain pump.fun client."""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.ingestion.pump_fun_onchain import PumpFunOnChainClient


async def main():
    """Test on-chain client functionality."""
    print("Testing pump.fun on-chain client...")
    print("=" * 50)
    
    # Use public RPC by default, or Helius if available
    import os
    rpc_url = os.environ.get("HELIUS_RPC_URL", "https://api.mainnet-beta.solana.com")
    print(f"Using RPC: {rpc_url[:50]}...")
    
    client = PumpFunOnChainClient(rpc_url)
    
    # Test 1: Check non-pump.fun token
    print("\n1. Testing non-pump.fun token (BONK)...")
    bonk = "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263"
    is_pumpfun = await client.is_pump_fun_token(bonk)
    print(f"   BONK is pump.fun: {is_pumpfun} (expected: False)")
    
    # Test 2: Check WIF (also not pump.fun)
    print("\n2. Testing non-pump.fun token (WIF)...")
    wif = "EKpQGSJtjMFqKZ9KQanSqYXRcF8fBopzLHYxdM65zcjm"
    is_pumpfun = await client.is_pump_fun_token(wif)
    print(f"   WIF is pump.fun: {is_pumpfun} (expected: False)")
    
    # Test 3: Try to get recent tokens (this may hit rate limits on public RPC)
    print("\n3. Testing recent token scan (may be slow/rate limited)...")
    try:
        tokens = await client.get_recent_tokens(limit=3)
        print(f"   Found {len(tokens)} tokens")
        for token in tokens:
            print(f"   - {token.address[:16]}... (graduated: {token.complete})")
    except Exception as e:
        print(f"   Rate limited or error: {e}")
    
    await client.close()
    print("\n" + "=" * 50)
    print("Test complete!")


if __name__ == "__main__":
    asyncio.run(main())
