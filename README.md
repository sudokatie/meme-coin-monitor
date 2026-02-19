# Meme Coin Monitor

A Python system for monitoring meme coins across Solana, Base, and Arbitrum chains, detecting fraud patterns, and identifying rug pulls before they happen.

Because losing money to obvious scams is embarrassing, and I'd rather be embarrassed by my trading decisions than my due diligence.

## Philosophy

> "If you can first learn to watch for patterns and then never trade those if fraud is detected on a previous meme coin that looks just like it, then you can always avoid those coins and not lose your whole stack."

Defensive-first: avoid losses before seeking gains. The goal isn't to find the next 100x. The goal is to not get rugged while looking for it.

## Features

- Real-time monitoring of new token launches via DexScreener
- Contract analysis (mint/freeze authority detection - the classic rug signals)
- Holder distribution analysis (whale detection, concentration metrics)
- Liquidity analysis (pool depth, slippage estimation)
- Trading pattern analysis (wash trading, pump detection)
- Pattern matching against known scams and scammer wallets
- Risk scoring (0-100 with LOW/MEDIUM/HIGH/CRITICAL categories)
- Opportunity scoring for tokens that pass the smell test
- Alert system with webhook and Telegram delivery
- REST API for queries and automation

## Project Structure

```
meme-coin-monitor/
├── src/
│   ├── main.py              # Entry point
│   ├── config.py            # Config loading
│   ├── storage/             # Database layer
│   ├── ingestion/           # Data sources (DexScreener, Solana RPC)
│   ├── analysis/            # The interesting stuff
│   │   ├── contract_analyzer.py
│   │   ├── holder_analyzer.py
│   │   ├── liquidity_analyzer.py
│   │   ├── trading_analyzer.py
│   │   └── pattern_matcher.py
│   ├── scoring/             # Risk and opportunity scoring
│   ├── alerts/              # Webhook and Telegram delivery
│   └── api/                 # FastAPI server
├── config/
│   └── default.yaml
├── data/                    # Runtime data
└── logs/                    # Log files
```

## Installation

```bash
cd projects/meme-coin-monitor
python3 -m venv venv
source venv/bin/activate
pip install -e .
```

## Usage

### Analyze a Single Token

```bash
python -m src.main --token <SOLANA_TOKEN_ADDRESS>
```

Get a full breakdown: contract flags, holder distribution, liquidity depth, trading patterns, and final risk score. Knowledge is power. Or at least knowledge is not-losing-money.

### Run the Monitor

```bash
# Start monitoring with API server
python -m src.main

# Without API server (just monitoring)
python -m src.main --no-api

# Debug mode (very chatty)
python -m src.main --debug
```

### API Endpoints

When running, the API is available at `http://127.0.0.1:8080`:

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Health check |
| `/token/{address}` | GET | Full token analysis |
| `/token/{address}/score` | GET | Just the scores |
| `/tokens/risky` | GET | List high-risk tokens (the hall of shame) |
| `/tokens/opportunities` | GET | List low-risk tokens (proceed with caution anyway) |
| `/alerts` | GET | Query alerts |
| `/watch/{address}` | POST | Add to watchlist |
| `/watch/{address}` | DELETE | Remove from watchlist |

## Configuration

Edit `config/default.yaml` or use environment variables:

| Variable | Description |
|----------|-------------|
| `SOLANA_RPC_URL` | Solana RPC endpoint |
| `BASE_RPC_URL` | Base chain RPC endpoint |
| `ARBITRUM_RPC_URL` | Arbitrum RPC endpoint |
| `DATABASE_URL` | Database connection |

### Multi-Chain Support

The monitor supports multiple EVM-compatible chains in addition to Solana:

- **Solana** (default, always enabled)
- **Base** (Coinbase L2) - enable in config
- **Arbitrum One** - enable in config

To enable additional chains, add to your `config/local.yaml`:

```yaml
ingestion:
  base_chain:
    enabled: true
    endpoint: https://mainnet.base.org  # or your preferred RPC
  arbitrum_chain:
    enabled: true
    endpoint: https://arb1.arbitrum.io/rpc
```

Each chain uses standard ERC-20 calls for token info. The unified `TokenData` model includes a `chain` field to identify the source chain.
| `ALERT_WEBHOOK_URL` | Webhook for alerts |
| `TELEGRAM_BOT_TOKEN` | Telegram bot token |
| `TELEGRAM_CHAT_ID` | Where to send alerts |

### Key Config Options

```yaml
scoring:
  thresholds:
    high_risk: 51      # Score >= 51 = HIGH risk (probably avoid)
    critical_risk: 76  # Score >= 76 = CRITICAL (definitely avoid)

alerts:
  throttle_per_token_minutes: 60  # Don't spam me about the same token
```

### Telegram Setup

1. Create a bot via [@BotFather](https://t.me/BotFather)
2. Get your chat ID via [@userinfobot](https://t.me/userinfobot)
3. Add to config:

```yaml
alerts:
  telegram_bot_token: "123456:ABC-DEF..."
  telegram_chat_id: "-1001234567890"
```

Alerts include severity, risk breakdown, top signals, and a Solscan link. Everything you need to make an informed decision to stay away.

## Risk Signals

| Signal | Severity | Weight | What It Means |
|--------|----------|--------|---------------|
| MINT_AUTHORITY_ACTIVE | HIGH | 25 | They can print infinite tokens. Run. |
| FREEZE_AUTHORITY_ACTIVE | MEDIUM | 15 | They can freeze your wallet. Concerning. |
| KNOWN_SCAMMER_DEPLOYER | CRITICAL | 30 | Deployed by someone who's rugged before. Hard no. |
| HIGH_CONCENTRATION | HIGH | 20 | Top 10 holders own >50%. Dump incoming. |
| CRITICAL_LOW_LIQUIDITY | CRITICAL | 20 | Less than $1k liquidity. Can't exit. |
| WASH_TRADING_DETECTED | HIGH | 15 | Fake volume. The charts are lying. |
| HEAVY_SELLING | HIGH | 10 | Insiders dumping. You're the exit liquidity. |

## Scammer Database

The system includes a database of known bad actors:

- **10 known scammer wallets** - Deployers linked to confirmed rug pulls
- **88 high-risk name patterns** - SAFEMOON, 100X, GUARANTEED, etc.
- **20 medium-risk name patterns** - Generic meme patterns
- **6 behavioral patterns** - Quick rug, bundled launch, wash trading

### Adding New Scammers

When you find one (you will), add them to `data/patterns/known_scammers.json`:

```json
{
  "wallets": [
    {
      "address": "...",
      "labels": ["serial_rugger"],
      "risk_flags": ["scammer"],
      "notes": "Rugged 3 tokens in January"
    }
  ]
}
```

Then reseed: `python scripts/seed_data.py --clear`

Think of it as a public service. Or revenge. Both are valid motivations.

## Data Sources

- **DexScreener API** - Price, volume, liquidity data
- **Solana RPC** - On-chain token data, holder distribution
- **pump.fun** - New token launches (blocked by Cloudflare, using DexScreener instead)

## Running Tests

```bash
pip install -e ".[dev]"
pytest
pytest --cov=src  # With coverage
```

## A Note on Trading

This tool helps you avoid obvious scams. It does not:
- Tell you what to buy
- Guarantee anything
- Replace your own judgment
- Make you immune to losing money

The crypto space is full of creative ways to separate you from your funds. This catches the lazy scammers. The clever ones require actual vigilance.

Trade small. Take profits. Don't be exit liquidity.

## License

Private - for personal use only.
