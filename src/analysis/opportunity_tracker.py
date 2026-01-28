"""Opportunity tracker - follows up on opportunity tokens to track outcomes for ML."""

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from src.config import IngestionConfig
from src.ingestion.dex_screener import DexScreenerClient
from src.storage.database import Database
from src.storage.models import OpportunityReview
from src.storage.repositories import OpportunityReviewRepository, SnapshotRepository


logger = logging.getLogger(__name__)


# Rug detection thresholds
RUG_PRICE_DROP_PCT = -90.0  # Price dropped 90%+
RUG_LIQUIDITY_DROP_PCT = -95.0  # Liquidity dropped 95%+
DEAD_PRICE_DROP_PCT = -99.0  # Effectively dead
MOON_PRICE_INCREASE_PCT = 500.0  # 5x or more


def calculate_price_change(initial: str | None, current: str | None) -> float | None:
    """Calculate percentage change between two price strings."""
    if not initial or not current:
        return None
    try:
        initial_f = float(initial)
        current_f = float(current)
        if initial_f == 0:
            return None
        return ((current_f - initial_f) / initial_f) * 100
    except (ValueError, TypeError):
        return None


def detect_rug(
    initial_price: str | None,
    current_price: str | None,
    initial_liquidity: str | None,
    current_liquidity: str | None,
) -> tuple[bool, str | None]:
    """
    Detect if a token has been rugged.
    
    Returns:
        Tuple of (is_rugged, reason)
    """
    reasons = []
    
    # Check price drop
    price_change = calculate_price_change(initial_price, current_price)
    if price_change is not None and price_change <= RUG_PRICE_DROP_PCT:
        reasons.append(f"price_drop_{abs(int(price_change))}pct")
    
    # Check liquidity drop
    liq_change = calculate_price_change(initial_liquidity, current_liquidity)
    if liq_change is not None and liq_change <= RUG_LIQUIDITY_DROP_PCT:
        reasons.append(f"liquidity_drop_{abs(int(liq_change))}pct")
    
    # Check if liquidity is essentially zero
    try:
        current_liq = float(current_liquidity) if current_liquidity else 0
        if current_liq < 100:  # Less than $100 liquidity
            reasons.append("liquidity_drained")
    except (ValueError, TypeError):
        pass
    
    if reasons:
        return True, "; ".join(reasons)
    return False, None


def determine_outcome(
    initial_price: str | None,
    week1_price: str | None,
    day1_rugged: bool | None,
    week1_rugged: bool | None,
) -> str:
    """
    Determine final outcome classification.
    
    Returns one of: SURVIVED, RUGGED, DEAD, MOONED
    """
    # If rugged at any point
    if day1_rugged or week1_rugged:
        return "RUGGED"
    
    # Check price performance
    price_change = calculate_price_change(initial_price, week1_price)
    
    if price_change is None:
        return "DEAD"  # Can't get price = probably dead
    
    if price_change <= DEAD_PRICE_DROP_PCT:
        return "DEAD"
    
    if price_change >= MOON_PRICE_INCREASE_PCT:
        return "MOONED"
    
    return "SURVIVED"


class OpportunityTracker:
    """Tracks opportunity tokens over time to build ML training data."""

    def __init__(
        self,
        database: Database,
        dex_client: DexScreenerClient,
        config: IngestionConfig,
    ) -> None:
        self._database = database
        self._dex_client = dex_client
        self._config = config
        self._running = False
        self._task: asyncio.Task | None = None

    async def create_review(
        self,
        token_address: str,
        alert_id: str,
        snapshot_data: dict[str, Any],
    ) -> OpportunityReview | None:
        """
        Create a new opportunity review when an OPPORTUNITY alert is generated.
        
        Args:
            token_address: Token address
            alert_id: ID of the OPPORTUNITY alert
            snapshot_data: Current snapshot data
        
        Returns:
            Created OpportunityReview or None if already exists
        """
        async with self._database.session() as session:
            repo = OpportunityReviewRepository(session)
            
            # Check if review already exists
            existing = await repo.get_by_token(token_address)
            if existing:
                logger.debug(f"Review already exists for {token_address}")
                return None
            
            review = OpportunityReview(
                token_address=token_address,
                alert_id=alert_id,
                initial_timestamp=datetime.now(timezone.utc),
                initial_price_usd=snapshot_data.get("price_usd"),
                initial_market_cap=snapshot_data.get("market_cap"),
                initial_liquidity_usd=snapshot_data.get("liquidity_usd"),
                initial_holder_count=snapshot_data.get("holder_count"),
                initial_risk_score=snapshot_data.get("risk_score"),
                initial_opportunity_score=snapshot_data.get("opportunity_score"),
            )
            
            await repo.create(review)
            await session.commit()
            
            logger.info(f"Created opportunity review for {token_address}")
            return review

    async def _process_day1_review(self, review: OpportunityReview) -> None:
        """Process a single day-1 review."""
        try:
            # Fetch current data
            token_data = await self._dex_client.fetch(review.token_address)
            
            now = datetime.now(timezone.utc)
            
            if token_data:
                price_change = calculate_price_change(
                    review.initial_price_usd,
                    token_data.price_usd
                )
                is_rugged, rug_reason = detect_rug(
                    review.initial_price_usd,
                    token_data.price_usd,
                    review.initial_liquidity_usd,
                    token_data.liquidity_usd,
                )
                
                async with self._database.session() as session:
                    repo = OpportunityReviewRepository(session)
                    await repo.update_day1_review(
                        review_id=review.id,
                        timestamp=now,
                        price_usd=token_data.price_usd,
                        market_cap=token_data.market_cap,
                        liquidity_usd=token_data.liquidity_usd,
                        holder_count=token_data.holder_count,
                        risk_score=None,  # Would need to re-score
                        price_change_pct=f"{price_change:.2f}" if price_change else None,
                        rugged=is_rugged,
                        rug_reason=rug_reason,
                    )
                    await session.commit()
                
                status = "RUGGED" if is_rugged else "OK"
                logger.info(
                    f"Day1 review for {review.token_address[:8]}...: "
                    f"{status}, price_change={price_change:.1f}%" if price_change else f"{status}"
                )
            else:
                # Token not found - likely rugged/dead
                async with self._database.session() as session:
                    repo = OpportunityReviewRepository(session)
                    await repo.update_day1_review(
                        review_id=review.id,
                        timestamp=now,
                        price_usd=None,
                        market_cap=None,
                        liquidity_usd=None,
                        holder_count=None,
                        risk_score=None,
                        price_change_pct=None,
                        rugged=True,
                        rug_reason="token_not_found",
                    )
                    await session.commit()
                
                logger.info(f"Day1 review for {review.token_address[:8]}...: NOT_FOUND (rugged)")
                
        except Exception as e:
            logger.error(f"Error processing day1 review for {review.token_address}: {e}")

    async def _process_week1_review(self, review: OpportunityReview) -> None:
        """Process a single week-1 review."""
        try:
            # Fetch current data
            token_data = await self._dex_client.fetch(review.token_address)
            
            now = datetime.now(timezone.utc)
            
            if token_data:
                price_change = calculate_price_change(
                    review.initial_price_usd,
                    token_data.price_usd
                )
                is_rugged, rug_reason = detect_rug(
                    review.initial_price_usd,
                    token_data.price_usd,
                    review.initial_liquidity_usd,
                    token_data.liquidity_usd,
                )
                
                final_outcome = determine_outcome(
                    review.initial_price_usd,
                    token_data.price_usd,
                    review.day1_rugged,
                    is_rugged,
                )
                
                outcome_notes = f"Initial: ${review.initial_price_usd}, Week1: ${token_data.price_usd}"
                if price_change:
                    outcome_notes += f", Change: {price_change:.1f}%"
                
                async with self._database.session() as session:
                    repo = OpportunityReviewRepository(session)
                    await repo.update_week1_review(
                        review_id=review.id,
                        timestamp=now,
                        price_usd=token_data.price_usd,
                        market_cap=token_data.market_cap,
                        liquidity_usd=token_data.liquidity_usd,
                        holder_count=token_data.holder_count,
                        risk_score=None,
                        price_change_pct=f"{price_change:.2f}" if price_change else None,
                        rugged=is_rugged,
                        rug_reason=rug_reason,
                        final_outcome=final_outcome,
                        outcome_notes=outcome_notes,
                    )
                    await session.commit()
                
                logger.info(
                    f"Week1 review for {review.token_address[:8]}...: "
                    f"outcome={final_outcome}, price_change={price_change:.1f}%" if price_change else f"outcome={final_outcome}"
                )
            else:
                # Token not found
                final_outcome = "DEAD" if review.day1_rugged else "RUGGED"
                
                async with self._database.session() as session:
                    repo = OpportunityReviewRepository(session)
                    await repo.update_week1_review(
                        review_id=review.id,
                        timestamp=now,
                        price_usd=None,
                        market_cap=None,
                        liquidity_usd=None,
                        holder_count=None,
                        risk_score=None,
                        price_change_pct=None,
                        rugged=True,
                        rug_reason="token_not_found",
                        final_outcome=final_outcome,
                        outcome_notes="Token no longer exists",
                    )
                    await session.commit()
                
                logger.info(f"Week1 review for {review.token_address[:8]}...: outcome={final_outcome} (not found)")
                
        except Exception as e:
            logger.error(f"Error processing week1 review for {review.token_address}: {e}")

    async def _review_loop(self) -> None:
        """Main loop that processes pending reviews."""
        logger.info("Starting opportunity review loop")
        
        while self._running:
            try:
                now = datetime.now(timezone.utc)
                day_ago = now - timedelta(days=1)
                week_ago = now - timedelta(days=7)
                
                # Process day-1 reviews (tokens discovered > 24h ago)
                async with self._database.session() as session:
                    repo = OpportunityReviewRepository(session)
                    pending_day1 = await repo.get_pending_day1_reviews(before=day_ago, limit=10)
                
                for review in pending_day1:
                    await self._process_day1_review(review)
                    await asyncio.sleep(1)  # Rate limiting
                
                # Process week-1 reviews (tokens discovered > 7 days ago, day1 done)
                async with self._database.session() as session:
                    repo = OpportunityReviewRepository(session)
                    pending_week1 = await repo.get_pending_week1_reviews(before=week_ago, limit=10)
                
                for review in pending_week1:
                    await self._process_week1_review(review)
                    await asyncio.sleep(1)  # Rate limiting
                
                # Check every 30 minutes
                await asyncio.sleep(1800)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in review loop: {e}")
                await asyncio.sleep(60)
        
        logger.info("Opportunity review loop stopped")

    async def start(self) -> None:
        """Start the review tracker."""
        if self._running:
            return
        
        self._running = True
        self._task = asyncio.create_task(self._review_loop())
        logger.info("Opportunity tracker started")

    async def stop(self) -> None:
        """Stop the review tracker."""
        if not self._running:
            return
        
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("Opportunity tracker stopped")
