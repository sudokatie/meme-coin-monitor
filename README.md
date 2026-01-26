# Meme Coin Monitor

A Python system for monitoring Solana meme coins, detecting fraud patterns, and identifying rug pulls before they happen.

## Philosophy

> "If you can first learn to watch for patterns and then never trade those if fraud is detected on a previous meme coin that looks just like it, then you can always avoid those coins and not lose your whole stack."

Defensive-first: avoid losses before seeking gains.

## Features

- Real-time monitoring of new token launches via pump.fun
- Contract analysis (mint/freeze authority detection)
- Holder distribution analysis (concentration, whale detection)
- Liquidity analysis (pool depth, slippage estimation)
- Trading pattern analysis (wash trading, pump detection)
- Pattern matching against known scams
- Risk scoring (0-100 with LOW/MEDIUM/HIGH/CRITICAL categories)
- Opportunity scoring for low-risk tokens
- Alert system with webhook delivery
- REST API for queries and management

## Project Structure

```
meme-coin-monitor/
├── pyproject.toml           # Project metadata and dependencies
├── requirements.txt         # Pinned dependencies
├── config/
│   └── default.yaml         # Configuration file
├── src/
│   ├── main.py              # Entry point
│   ├── config.py            # Config loading and validation
│   ├── storage/
│   │   ├── database.py      # Async SQLAlchemy setup
│   │   ├── models.py        # Token, Snapshot, Alert, Pattern, Wallet
│   │   └── repositories.py  # Data access layer
│   ├── ingestion/
│   │   ├── base.py          # Base ingester class
│   │   ├── dex_screener.py  # DEX Screener API client
│   │   ├── solana_rpc.py    # Solana RPC client
│   │   ├── pump_fun.py      # Pump.fun monitoring
│   │   └── scheduler.py     # Polling coordinator
│   ├── analysis/
│   │   ├── base.py          # Base analyzer, Signal, AnalysisResult
│   │   ├── contract_analyzer.py
│   │   ├── holder_analyzer.py
│   │   ├── liquidity_analyzer.py
│   │   ├── trading_analyzer.py
│   │   └── pattern_matcher.py
│   ├── scoring/
│   │   ├── risk_scorer.py       # Weighted risk scoring
│   │   └── opportunity_scorer.py
│   ├── alerts/
│   │   ├── alert_manager.py # Alert generation and throttling
│   │   └── webhook.py       # Webhook delivery
│   ├── api/
│   │   ├── server.py        # FastAPI setup
│   │   └── routes.py        # REST endpoints
│   └── utils/
│       ├── solana.py        # Address validation, conversions
│       └── formatting.py    # USD, percentage formatting
├── tests/
│   ├── conftest.py          # Pytest fixtures
│   └── test_scoring.py      # Scoring tests
├── data/                    # Runtime data (created automatically)
└── logs/                    # Log files (created automatically)
```

## Installation

```bash
# Clone or navigate to project
cd projects/meme-coin-monitor

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -e .

# Or use requirements.txt
pip install -r requirements.txt
```

## Usage

### Analyze a Single Token

```bash
python -m src.main --token <SOLANA_TOKEN_ADDRESS>

# Example
python -m src.main --token So11111111111111111111111111111111111111112
```

### Run the Monitor

```bash
# Start monitoring with API server
python -m src.main

# Without API server
python -m src.main --no-api

# With debug logging
python -m src.main --debug

# Custom config file
python -m src.main --config /path/to/config.yaml
```

### API Endpoints

When running, the API is available at `http://127.0.0.1:8080`:

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Health check |
| `/token/{address}` | GET | Full token analysis |
| `/token/{address}/score` | GET | Just risk/opportunity scores |
| `/tokens/risky` | GET | List high-risk tokens |
| `/tokens/opportunities` | GET | List opportunity tokens |
| `/alerts` | GET | Query alerts (filter by token, type) |
| `/watch/{address}` | POST | Add token to watchlist |
| `/watch/{address}` | DELETE | Remove from watchlist |

## Configuration

Edit `config/default.yaml` or set environment variables:

| Environment Variable | Description |
|---------------------|-------------|
| `SOLANA_RPC_URL` | Solana RPC endpoint |
| `DATABASE_URL` | Database connection string |
| `ALERT_WEBHOOK_URL` | Webhook URL for alerts |
| `TELEGRAM_BOT_TOKEN` | Telegram bot token from @BotFather |
| `TELEGRAM_CHAT_ID` | Telegram chat/channel ID for alerts |
| `LOG_LEVEL` | Logging level (DEBUG/INFO/WARNING/ERROR) |
| `API_HOST` | API server host |
| `API_PORT` | API server port |

### Key Config Options

```yaml
database:
  type: sqlite                    # or postgresql
  path: data/meme_monitor.db

ingestion:
  dex_screener:
    poll_interval_seconds: 30
  pump_fun:
    poll_interval_seconds: 10

scoring:
  thresholds:
    high_risk: 51                 # Score >= 51 = HIGH risk
    critical_risk: 76             # Score >= 76 = CRITICAL risk

alerts:
  webhook_url: null               # Set to receive alerts via webhook
  telegram_bot_token: null        # Telegram bot token from @BotFather
  telegram_chat_id: null          # Target chat/channel ID
  throttle_per_token_minutes: 60  # Max 1 alert per token per hour
```

### Telegram Setup

1. Create a bot via [@BotFather](https://t.me/BotFather) on Telegram
2. Copy the bot token
3. Start a chat with your bot or add it to a channel
4. Get your chat ID (use [@userinfobot](https://t.me/userinfobot) or the Telegram API)
5. Add to `config/default.yaml`:

```yaml
alerts:
  telegram_bot_token: "123456:ABC-DEF..."
  telegram_chat_id: "-1001234567890"  # Negative for groups/channels
```

Alerts include:
- Severity prefix ([!!!] CRITICAL, [!] HIGH, etc.)
- Token name, symbol, and address
- Risk/opportunity scores with breakdown
- Top contributing signals
- Direct link to Solscan

## Risk Signals

| Signal | Severity | Weight | Description |
|--------|----------|--------|-------------|
| MINT_AUTHORITY_ACTIVE | HIGH | 25 | Can mint unlimited tokens |
| FREEZE_AUTHORITY_ACTIVE | MEDIUM | 15 | Can freeze transfers |
| KNOWN_SCAMMER_DEPLOYER | CRITICAL | 30 | Deployed by known scammer |
| HIGH_CONCENTRATION | HIGH | 20 | Top 10 holders > 50% |
| CRITICAL_LOW_LIQUIDITY | CRITICAL | 20 | Liquidity < $1,000 |
| WASH_TRADING_DETECTED | HIGH | 15 | Suspicious trading patterns |
| HEAVY_SELLING | HIGH | 10 | Buy/sell ratio < 0.2 |

## Scammer Database

The system includes a scammer pattern database at `data/patterns/known_scammers.json`:

- **10 known scammer wallets** - Deployers linked to confirmed rug pulls
- **88 high-risk name patterns** - Names commonly used in scams (SAFEMOON, 100X, etc.)
- **20 medium-risk name patterns** - Generic meme coin patterns
- **6 behavioral patterns** - Quick rug, bundled launch, wash trading, etc.

### Seeding the Database

```bash
# Initial seed
python scripts/seed_data.py

# Clear and reseed
python scripts/seed_data.py --clear
```

### Adding New Scammers

Edit `data/patterns/known_scammers.json` to add new entries:

```json
{
  "wallets": [
    {
      "address": "...",
      "labels": ["serial_rugger"],
      "risk_flags": ["scammer"],
      "notes": "Description of confirmed rugs"
    }
  ]
}
```

Then reseed: `python scripts/seed_data.py --clear`

## Running Tests

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Run tests
pytest

# With coverage
pytest --cov=src
```

## Data Sources

- DEX Screener API - Price, volume, liquidity data
- Solana RPC - On-chain token data, holder distribution
- Pump.fun - New token launches, graduations

## License

Private - for personal use only.
