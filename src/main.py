"""Main entry point for Meme Coin Monitor."""

import argparse
import asyncio
import logging
import signal
import sys
from datetime import datetime, timezone
from pathlib import Path

import uvicorn

from src.config import Config, load_config, setup_logging
from src.storage.database import Database
from src.storage.models import Snapshot, Token
from src.ingestion.dex_screener import DexScreenerClient
from src.ingestion.pump_fun import PumpFunClient
from src.ingestion.solana_rpc import SolanaRpcClient
from src.ingestion.scheduler import IngestionScheduler
from src.ingestion.base import TokenData
from src.analysis.contract_analyzer import ContractAnalyzer
from src.analysis.holder_analyzer import HolderAnalyzer
from src.analysis.liquidity_analyzer import LiquidityAnalyzer
from src.analysis.trading_analyzer import TradingAnalyzer
from src.analysis.pattern_matcher import PatternMatcher
from src.scoring.risk_scorer import RiskScorer
from src.scoring.opportunity_scorer import OpportunityScorer
from src.alerts.alert_manager import AlertManager
from src.alerts.telegram import TelegramChannel
from src.alerts.webhook import WebhookChannel
from src.analysis.opportunity_tracker import OpportunityTracker
from src.api.server import create_app, set_app_state


logger = logging.getLogger(__name__)

_shutdown_event: asyncio.Event | None = None


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Monitor Solana meme coins for fraud patterns and rug pulls"
    )
    parser.add_argument(
        "--config", "-c",
        type=Path,
        default=None,
        help="Path to config file (default: config/default.yaml)",
    )
    parser.add_argument(
        "--token", "-t",
        type=str,
        default=None,
        help="Analyze a single token and exit",
    )
    parser.add_argument(
        "--no-api",
        action="store_true",
        help="Disable API server",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug logging",
    )
    return parser.parse_args()


def setup_signal_handlers(loop: asyncio.AbstractEventLoop) -> None:
    """Set up signal handlers for graceful shutdown."""
    global _shutdown_event
    _shutdown_event = asyncio.Event()

    def handle_signal(sig: signal.Signals) -> None:
        logger.info(f"Received signal {sig.name}, initiating shutdown")
        if _shutdown_event:
            _shutdown_event.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, handle_signal, sig)


class MonitorApp:
    """Main application class."""

    def __init__(self, config: Config) -> None:
        self.config = config
        self.database: Database | None = None
        self.dex_client: DexScreenerClient | None = None
        self.rpc_client: SolanaRpcClient | None = None
        self.pump_client: PumpFunClient | None = None
        self.scheduler: IngestionScheduler | None = None
        self.contract_analyzer: ContractAnalyzer | None = None
        self.holder_analyzer: HolderAnalyzer | None = None
        self.liquidity_analyzer: LiquidityAnalyzer | None = None
        self.trading_analyzer: TradingAnalyzer | None = None
        self.pattern_matcher: PatternMatcher | None = None
        self.risk_scorer: RiskScorer | None = None
        self.opportunity_scorer: OpportunityScorer | None = None
        self.alert_manager: AlertManager | None = None
        self.opportunity_tracker: OpportunityTracker | None = None

    async def init(self) -> None:
        """Initialize all components."""
        logger.info("Initializing components")

        Path("data").mkdir(exist_ok=True)
        Path("data/patterns").mkdir(exist_ok=True)
        Path("data/history").mkdir(exist_ok=True)

        self.database = Database(self.config.database)
        await self.database.init()

        self.dex_client = DexScreenerClient(self.config.ingestion.dex_screener)
        self.rpc_client = SolanaRpcClient(self.config.ingestion.solana_rpc)
        self.pump_client = PumpFunClient()

        self.contract_analyzer = ContractAnalyzer(self.rpc_client)
        self.holder_analyzer = HolderAnalyzer(
            self.rpc_client,
            config=self.config.analysis,
            thresholds=self.config.scoring.thresholds,
        )
        self.liquidity_analyzer = LiquidityAnalyzer(
            self.dex_client,
            thresholds=self.config.scoring.thresholds,
        )
        self.trading_analyzer = TradingAnalyzer(self.dex_client)
        self.pattern_matcher = PatternMatcher()

        self.risk_scorer = RiskScorer(
            weights=self.config.scoring.risk_weights,
            thresholds=self.config.scoring.thresholds,
        )
        self.opportunity_scorer = OpportunityScorer()

        self.alert_manager = AlertManager(self.config.alerts)
        if self.config.alerts.webhook_url:
            self.alert_manager.add_channel(
                WebhookChannel(self.config.alerts.webhook_url)
            )
        if self.config.alerts.telegram_bot_token and self.config.alerts.telegram_chat_id:
            self.alert_manager.add_channel(
                TelegramChannel(
                    self.config.alerts.telegram_bot_token,
                    self.config.alerts.telegram_chat_id,
                )
            )
            logger.info("Telegram alert channel configured")

        self.scheduler = IngestionScheduler(
            self.config.ingestion,
            self.dex_client,
            self.pump_client,
            on_token_data=self._on_token_data,
        )

        # Opportunity tracker for ML training data
        self.opportunity_tracker = OpportunityTracker(
            self.database,
            self.dex_client,
            self.config.ingestion,
        )

        set_app_state("database", self.database)
        set_app_state("scheduler", self.scheduler)
        set_app_state("opportunity_tracker", self.opportunity_tracker)

        logger.info("All components initialized")

    async def close(self) -> None:
        """Close all components."""
        logger.info("Closing components")

        if self.opportunity_tracker:
            await self.opportunity_tracker.stop()

        if self.scheduler:
            await self.scheduler.stop()

        if self.dex_client:
            await self.dex_client.close()
        if self.rpc_client:
            await self.rpc_client.close()
        if self.pump_client:
            await self.pump_client.close()

        if self.database:
            await self.database.close()

        logger.info("All components closed")

    async def _on_token_data(self, token_address: str, data: TokenData) -> None:
        """Handle new token data from ingestion."""
        try:
            await self.analyze_token(token_address, data)
        except Exception as e:
            logger.error(f"Error analyzing token {token_address}: {e}")

    async def analyze_token(self, token_address: str, data: TokenData) -> dict:
        """
        Run full analysis on a token.

        Args:
            token_address: Token mint address
            data: Token data from ingestion

        Returns:
            Analysis results dict
        """
        logger.info(f"Analyzing token: {data.symbol} ({token_address[:8]}...)")

        analysis_data = {
            "supply": 0,
            "market_cap": data.market_cap,
            "volume_24h": data.volume_24h,
            "name": data.name,
            "symbol": data.symbol,
            "deployer": "",
        }

        analyses = {}

        if self.contract_analyzer:
            analyses["contract"] = await self.contract_analyzer.analyze(
                token_address, analysis_data
            )
            if hasattr(analyses["contract"], "supply"):
                analysis_data["supply"] = analyses["contract"].supply

        if self.holder_analyzer:
            analyses["holder"] = await self.holder_analyzer.analyze(
                token_address, analysis_data
            )

        if self.liquidity_analyzer:
            analyses["liquidity"] = await self.liquidity_analyzer.analyze(
                token_address, analysis_data
            )

        if self.trading_analyzer:
            analyses["trading"] = await self.trading_analyzer.analyze(
                token_address, analysis_data
            )

        if self.pattern_matcher:
            analyses["pattern"] = await self.pattern_matcher.analyze(
                token_address, analysis_data
            )

        risk_score = self.risk_scorer.score(analyses) if self.risk_scorer else None
        opportunity_score = None
        if self.opportunity_scorer and risk_score:
            opportunity_score = self.opportunity_scorer.score(analyses, risk_score)

        if risk_score:
            logger.info(
                f"Token {data.symbol}: risk={risk_score.score} [{risk_score.category.value}]"
            )

        if self.database:
            async with self.database.session() as session:
                from src.storage.repositories import TokenRepository, SnapshotRepository

                token_repo = TokenRepository(session)
                snapshot_repo = SnapshotRepository(session)

                token = Token(
                    address=token_address,
                    name=data.name,
                    symbol=data.symbol,
                    decimals=9,
                    first_seen=datetime.now(timezone.utc),
                    deployer=analysis_data.get("deployer", ""),
                )
                await token_repo.upsert(token)

                holder_count = None
                top_10_pct = None
                if "holder" in analyses:
                    holder_count = analyses["holder"].total_holders
                    top_10_pct = str(analyses["holder"].top_10_percentage)

                snapshot = Snapshot(
                    token_address=token_address,
                    timestamp=datetime.now(timezone.utc),
                    price_usd=data.price_usd,
                    market_cap=data.market_cap,
                    volume_24h=data.volume_24h,
                    liquidity_usd=data.liquidity_usd,
                    holder_count=holder_count,
                    top_10_pct=top_10_pct,
                    risk_score=risk_score.score if risk_score else None,
                    opportunity_score=opportunity_score.score if opportunity_score else None,
                    confidence=risk_score.confidence if risk_score else None,
                )
                await snapshot_repo.create(snapshot)

        if self.alert_manager and risk_score:
            alert = await self.alert_manager.process(
                token_address,
                data.name,
                data.symbol,
                risk_score,
                opportunity_score,
            )

            # Persist alert to database if one was generated
            if alert and self.database:
                async with self.database.session() as session:
                    from src.storage.repositories import AlertRepository
                    alert_repo = AlertRepository(session)
                    await alert_repo.create(alert)
                    await session.commit()

                # Create opportunity review for ML tracking if this is an OPPORTUNITY alert
                if alert.alert_type == "OPPORTUNITY" and self.opportunity_tracker:
                    snapshot_data = {
                        "price_usd": data.price_usd,
                        "market_cap": data.market_cap,
                        "liquidity_usd": data.liquidity_usd,
                        "holder_count": holder_count if "holder" in analyses else None,
                        "risk_score": risk_score.score if risk_score else None,
                        "opportunity_score": opportunity_score.score if opportunity_score else None,
                    }
                    await self.opportunity_tracker.create_review(
                        token_address,
                        alert.id,
                        snapshot_data,
                    )

        return {
            "token": data,
            "analyses": analyses,
            "risk_score": risk_score,
            "opportunity_score": opportunity_score,
        }


async def analyze_single_token(config: Config, token_address: str) -> int:
    """
    Analyze a single token and print results.

    Args:
        config: Application configuration
        token_address: Solana token address to analyze

    Returns:
        Exit code (0 for success, 1 for error)
    """
    app = MonitorApp(config)

    try:
        await app.init()

        token_data = await app.scheduler.fetch_single(token_address)
        if not token_data:
            print(f"Error: Could not fetch data for token {token_address}")
            return 1

        results = await app.analyze_token(token_address, token_data)

        print(f"\n{'=' * 60}")
        print(f"TOKEN ANALYSIS: {token_data.symbol}")
        print(f"{'=' * 60}")
        print(f"Address: {token_address}")
        print(f"Name: {token_data.name}")
        print(f"Price: ${token_data.price_usd or 'N/A'}")
        print(f"Market Cap: ${token_data.market_cap or 'N/A'}")
        print(f"Liquidity: ${token_data.liquidity_usd or 'N/A'}")

        risk = results.get("risk_score")
        if risk:
            print(f"\nRISK SCORE: {risk.score}/100 [{risk.category.value}]")
            print("Signals:")
            for sig in risk.signals[:5]:
                print(f"  - {sig.name}: +{sig.contribution} points")

        opp = results.get("opportunity_score")
        if opp:
            print(f"\nOPPORTUNITY SCORE: {opp.score}/100 [{opp.category.value}]")

        print(f"{'=' * 60}\n")

        return 0

    finally:
        await app.close()


async def run_monitor(config: Config, enable_api: bool) -> None:
    """
    Run the monitoring system.

    Args:
        config: Application configuration
        enable_api: Whether to start the API server
    """
    global _shutdown_event

    app = MonitorApp(config)

    try:
        await app.init()
        await app.scheduler.start()
        await app.opportunity_tracker.start()

        api_server = None
        if enable_api and config.api.enabled:
            fastapi_app = create_app(config.api)
            api_config = uvicorn.Config(
                fastapi_app,
                host=config.api.host,
                port=config.api.port,
                log_level="warning",
            )
            api_server = uvicorn.Server(api_config)
            asyncio.create_task(api_server.serve())
            logger.info(f"API server started on {config.api.host}:{config.api.port}")

        logger.info("Monitor running - press Ctrl+C to stop")

        if _shutdown_event:
            await _shutdown_event.wait()

    finally:
        await app.close()


async def async_main(args: argparse.Namespace) -> int:
    """
    Async main function.

    Args:
        args: Parsed command line arguments

    Returns:
        Exit code
    """
    try:
        config = load_config(args.config)
    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    except ValueError as e:
        print(f"Configuration error: {e}", file=sys.stderr)
        return 1

    if args.debug:
        config.logging.level = "DEBUG"

    setup_logging(config.logging)
    logger.info("Meme Coin Monitor starting")

    if args.token:
        return await analyze_single_token(config, args.token)

    loop = asyncio.get_event_loop()
    setup_signal_handlers(loop)

    enable_api = config.api.enabled and not args.no_api
    await run_monitor(config, enable_api)

    logger.info("Meme Coin Monitor stopped")
    return 0


def main() -> None:
    """Main entry point."""
    args = parse_args()

    try:
        exit_code = asyncio.run(async_main(args))
    except KeyboardInterrupt:
        print("\nInterrupted")
        exit_code = 130

    sys.exit(exit_code)


if __name__ == "__main__":
    main()
