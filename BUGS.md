# Meme Coin Monitor - Known Bugs & Research

## Active Issues

### BUG-001: Pump.fun API Blocked by Cloudflare
- **Status:** WORKAROUND (disabled)
- **Severity:** High
- **Description:** All requests to `frontend-api.pump.fun` return HTTP 530 (Cloudflare origin error)
- **Impact:** Cannot monitor new token launches from pump.fun
- **Workaround:** Disabled pump.fun polling in config. Using DEX Screener for discovery.
- **Date:** 2025-01-25

**Root Cause:**
Pump.fun uses Cloudflare protection that blocks non-browser requests. Even with browser-like headers, the API returns 530 errors. This is likely intentional to prevent scraping/bots.

**Potential Solutions:**

1. **Use pumpdotfun-sdk (On-Chain Approach)** - RECOMMENDED
   - GitHub: https://github.com/rckprtr/pumpdotfun-sdk
   - Reads directly from Solana blockchain via RPC
   - Bypasses API entirely - no Cloudflare issues
   - Can get bonding curve data, token info via on-chain accounts
   - Requires: Helius RPC (they recommend it in their docs)

2. **DEX Screener New Pairs API**
   - Already using DEX Screener for token data
   - Can poll for newly listed Solana pairs
   - May have slight delay vs pump.fun direct

3. **Birdeye New Listings API**
   - `GET /defi/token_new_listing` endpoint
   - Requires API key (free tier available)
   - Covers all Solana tokens, not just pump.fun

4. **Geyser/Yellowstone gRPC Streaming**
   - Real-time on-chain event streaming
   - Can subscribe to pump.fun program account changes
   - Requires paid RPC with gRPC support (Helius, Triton)

---

### BUG-002: Solana Public RPC Rate Limiting
- **Status:** OPEN
- **Severity:** Medium  
- **Description:** Public Solana RPC (`api.mainnet-beta.solana.com`) returns 429 Too Many Requests when fetching holder data
- **Impact:** Holder analysis incomplete - missing holder count and distribution
- **Workaround:** Analysis continues without holder data (reduced accuracy)
- **Date:** 2025-01-25

**Root Cause:**
The public Solana RPC has strict rate limits. `getTokenAccountsByOwner` and `getProgramAccounts` are heavy calls that quickly hit limits.

**RPC Provider Options (Researched):**

| Provider | Free Tier | Paid Plans | Notes |
|----------|-----------|------------|-------|
| **Helius** | 1M credits/mo, 10 RPS | $49-999/mo | Best for Solana, has DAS API |
| **QuickNode** | Limited | ~$50+/mo | Multi-chain |
| **Alchemy** | Yes | Varies | 20x faster archive, good uptime |
| **Ankr** | Yes (freemium) | Premium available | Simple setup |
| **Triton** | No free tier | $2900+/mo dedicated | Enterprise, used by Jupiter/Orca |
| **HelloMoon** | Has free tier | Paid tiers | Good for analytics |

**Recommended: Helius Free Tier**
- 1M credits/month (enough for monitoring)
- 10 RPS (sufficient for our polling intervals)
- DAS API for token metadata
- Good Solana-specific features
- Sign up: https://dashboard.helius.dev

**Implementation Notes:**
- Replace `api.mainnet-beta.solana.com` with Helius endpoint
- Add retry logic with exponential backoff for 429s
- Cache holder data (doesn't change frequently)
- Consider reducing poll frequency for holder data

---

## Resolved Issues

(none yet)

---

## Current Functionality Status

**Working:**
- DEX Screener token data (price, volume, liquidity)
- Contract analysis (mint/freeze authority via RPC)
- Pattern matching (name similarity, scammer wallet detection)
- Risk scoring
- Alert generation
- API server

**Degraded:**
- Holder analysis (missing due to RPC rate limits)

**Not Working:**
- New token discovery from pump.fun (API blocked)

---

## Recommended Next Steps

1. **Sign up for Helius free tier** - Fixes RPC rate limiting
2. **Implement pumpdotfun-sdk** - Read pump.fun data on-chain
3. **Add DEX Screener new pairs polling** - Alternative token discovery
4. **Implement request throttling** - Prevent rate limit issues

---

## Resources

- Helius Docs: https://www.helius.dev/docs
- Helius Pricing: https://www.helius.dev/pricing
- PumpDotFun SDK: https://github.com/rckprtr/pumpdotfun-sdk
- Triton (Enterprise): https://triton.one/
- DEX Screener API: https://docs.dexscreener.com/
