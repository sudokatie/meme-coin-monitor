"""API routes."""

import logging
import re
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from src.api.server import get_app_state


logger = logging.getLogger(__name__)
router = APIRouter()

ADDRESS_PATTERN = re.compile(r"^[1-9A-HJ-NP-Za-km-z]{32,44}$")


def validate_address(address: str) -> str:
    """Validate Solana address format."""
    if not ADDRESS_PATTERN.match(address):
        raise HTTPException(status_code=400, detail="Invalid Solana address format")
    return address


class HealthResponse(BaseModel):
    """Health check response."""

    status: str
    version: str = "0.1.0"


class TokenScoreResponse(BaseModel):
    """Token score response."""

    address: str
    name: str | None
    symbol: str | None
    risk_score: int | None
    risk_category: str | None
    opportunity_score: int | None
    opportunity_category: str | None
    confidence: str | None


class TokenAnalysisResponse(TokenScoreResponse):
    """Full token analysis response."""

    price_usd: str | None
    market_cap: str | None
    liquidity_usd: str | None
    holder_count: int | None
    top_10_pct: float | None
    signals: list[dict[str, Any]]


class AlertResponse(BaseModel):
    """Alert response."""

    id: str
    token_address: str
    alert_type: str
    severity: str
    message: str
    created_at: str
    acknowledged: bool


class WatchlistResponse(BaseModel):
    """Watchlist operation response."""

    address: str
    added: bool | None = None
    removed: bool | None = None


class ErrorDetail(BaseModel):
    """Error detail structure."""

    code: str
    message: str


class ErrorResponse(BaseModel):
    """Error response."""

    error: ErrorDetail


class DataWrapper(BaseModel):
    """Generic data wrapper for responses."""

    data: Any


def wrap_response(data: Any) -> dict[str, Any]:
    """Wrap response data in standard format."""
    return {"data": data}


def error_response(code: str, message: str) -> dict[str, Any]:
    """Create error response in standard format."""
    return {"error": {"code": code, "message": message}}


@router.get("/health")
async def health_check() -> dict[str, Any]:
    """Health check endpoint."""
    return wrap_response({"status": "ok", "version": "0.1.0"})


@router.get("/token/{address}")
async def get_token_analysis(address: str) -> dict[str, Any]:
    """
    Get full analysis for a token.

    Args:
        address: Token mint address
    """
    address = validate_address(address)
    state = get_app_state()

    if "database" in state:
        async with state["database"].session() as session:
            from src.storage.repositories import SnapshotRepository
            repo = SnapshotRepository(session)
            snapshot = await repo.get_latest(address)

            if snapshot:
                return wrap_response({
                    "address": address,
                    "risk_score": snapshot.risk_score,
                    "opportunity_score": snapshot.opportunity_score,
                    "confidence": snapshot.confidence,
                    "price_usd": snapshot.price_usd,
                    "market_cap": snapshot.market_cap,
                    "liquidity_usd": snapshot.liquidity_usd,
                    "holder_count": snapshot.holder_count,
                    "top_10_pct": float(snapshot.top_10_pct) if snapshot.top_10_pct else None,
                    "timestamp": snapshot.timestamp.isoformat() if snapshot.timestamp else None,
                })

    # Token not found in database
    raise HTTPException(
        status_code=404,
        detail=error_response("TOKEN_NOT_FOUND", f"No analysis found for token {address}")
    )


@router.get("/token/{address}/score")
async def get_token_score(address: str) -> dict[str, Any]:
    """
    Get just risk and opportunity scores for a token.

    Args:
        address: Token mint address
    """
    address = validate_address(address)
    state = get_app_state()

    if "database" in state:
        async with state["database"].session() as session:
            from src.storage.repositories import SnapshotRepository
            repo = SnapshotRepository(session)
            snapshot = await repo.get_latest(address)

            if snapshot:
                return wrap_response({
                    "address": address,
                    "risk_score": snapshot.risk_score,
                    "opportunity_score": snapshot.opportunity_score,
                    "confidence": snapshot.confidence,
                })

    raise HTTPException(
        status_code=404,
        detail=error_response("TOKEN_NOT_FOUND", f"No score found for token {address}")
    )


@router.get("/tokens/risky")
async def get_risky_tokens(
    limit: int = Query(default=20, ge=1, le=100),
) -> dict[str, Any]:
    """
    Get list of high-risk tokens.

    Args:
        limit: Maximum number of tokens to return
    """
    state = get_app_state()
    tokens = []

    if "database" in state:
        async with state["database"].session() as session:
            from src.storage.repositories import SnapshotRepository
            repo = SnapshotRepository(session)
            snapshots = await repo.get_risky(threshold=51, limit=limit)

            tokens = [
                {
                    "address": s.token_address,
                    "risk_score": s.risk_score,
                    "opportunity_score": s.opportunity_score,
                    "confidence": s.confidence,
                    "timestamp": s.timestamp.isoformat() if s.timestamp else None,
                }
                for s in snapshots
            ]

    return wrap_response(tokens)


@router.get("/tokens/opportunities")
async def get_opportunity_tokens(
    limit: int = Query(default=20, ge=1, le=100),
) -> dict[str, Any]:
    """
    Get list of opportunity tokens.

    Args:
        limit: Maximum number of tokens to return
    """
    state = get_app_state()
    tokens = []

    if "database" in state:
        async with state["database"].session() as session:
            from src.storage.repositories import SnapshotRepository
            repo = SnapshotRepository(session)
            snapshots = await repo.get_opportunities(min_score=50, limit=limit)

            tokens = [
                {
                    "address": s.token_address,
                    "risk_score": s.risk_score,
                    "opportunity_score": s.opportunity_score,
                    "confidence": s.confidence,
                    "timestamp": s.timestamp.isoformat() if s.timestamp else None,
                }
                for s in snapshots
            ]

    return wrap_response(tokens)


@router.get("/alerts")
async def get_alerts(
    token: str | None = Query(default=None),
    alert_type: str | None = Query(default=None, alias="type"),
    limit: int = Query(default=50, ge=1, le=200),
) -> dict[str, Any]:
    """
    Query alerts.

    Args:
        token: Filter by token address
        alert_type: Filter by alert type
        limit: Maximum alerts to return
    """
    state = get_app_state()
    alerts_list = []

    if "database" in state:
        async with state["database"].session() as session:
            from src.storage.repositories import AlertRepository
            repo = AlertRepository(session)

            if token:
                token = validate_address(token)
                alerts = await repo.get_by_token(token, limit=limit)
            else:
                alerts = await repo.get_recent(
                    limit=limit,
                    alert_type=alert_type,
                )

            alerts_list = [
                {
                    "id": a.id,
                    "token_address": a.token_address,
                    "alert_type": a.alert_type,
                    "severity": a.severity,
                    "message": a.message,
                    "created_at": a.created_at.isoformat(),
                    "acknowledged": a.acknowledged,
                }
                for a in alerts
            ]

    return wrap_response(alerts_list)


@router.post("/watch/{address}")
async def add_to_watchlist(address: str) -> dict[str, Any]:
    """
    Add token to watchlist.

    Args:
        address: Token mint address
    """
    address = validate_address(address)
    state = get_app_state()

    scheduler = state.get("scheduler")
    if scheduler:
        scheduler.add_to_watchlist(address)

    return wrap_response({"address": address, "added": True})


@router.delete("/watch/{address}")
async def remove_from_watchlist(address: str) -> dict[str, Any]:
    """
    Remove token from watchlist.

    Args:
        address: Token mint address
    """
    address = validate_address(address)
    state = get_app_state()

    scheduler = state.get("scheduler")
    if scheduler:
        scheduler.remove_from_watchlist(address)

    return wrap_response({"address": address, "removed": True})


# --- Pattern Management Endpoints (per SPECS.md 7.2.2) ---


class PatternCreate(BaseModel):
    """Pattern creation request."""

    name: str
    description: str
    pattern_type: str  # DEPLOYER, CONTRACT, TRADING, HOLDER, NAME
    pattern_data: dict[str, Any]
    confidence: str = "MEDIUM"
    source_tokens: list[str] = []


class PatternResponse(BaseModel):
    """Pattern response."""

    id: str
    name: str
    description: str
    pattern_type: str
    pattern_data: dict[str, Any]
    confidence: str
    created_at: str
    source_tokens: list[str]


@router.get("/patterns")
async def list_patterns(
    pattern_type: str | None = Query(default=None, alias="type"),
    limit: int = Query(default=100, ge=1, le=500),
) -> dict[str, Any]:
    """
    List known patterns.

    Args:
        pattern_type: Filter by pattern type (DEPLOYER, CONTRACT, TRADING, HOLDER, NAME)
        limit: Maximum patterns to return
    """
    state = get_app_state()
    patterns_list = []

    if "database" in state:
        async with state["database"].session() as session:
            from src.storage.repositories import PatternRepository
            repo = PatternRepository(session)

            if pattern_type:
                patterns = await repo.get_by_type(pattern_type.upper())
            else:
                patterns = await repo.get_all(limit=limit)

            patterns_list = [
                {
                    "id": p.id,
                    "name": p.name,
                    "description": p.description,
                    "pattern_type": p.pattern_type,
                    "pattern_data": p.pattern_data,
                    "confidence": p.confidence,
                    "created_at": p.created_at.isoformat() if p.created_at else None,
                    "source_tokens": p.source_tokens or [],
                }
                for p in patterns
            ]

    return wrap_response(patterns_list)


@router.post("/pattern")
async def create_pattern(pattern: PatternCreate) -> dict[str, Any]:
    """
    Add a new pattern.

    Args:
        pattern: Pattern data
    """
    from datetime import datetime, timezone
    from src.storage.models import Pattern

    state = get_app_state()

    if "database" not in state:
        raise HTTPException(status_code=503, detail="Database not available")

    # Validate pattern type
    valid_types = {"DEPLOYER", "CONTRACT", "TRADING", "HOLDER", "NAME"}
    if pattern.pattern_type.upper() not in valid_types:
        raise HTTPException(
            status_code=400,
            detail=error_response(
                "INVALID_PATTERN_TYPE",
                f"pattern_type must be one of: {', '.join(valid_types)}"
            )
        )

    async with state["database"].session() as session:
        from src.storage.repositories import PatternRepository
        repo = PatternRepository(session)

        new_pattern = Pattern(
            name=pattern.name,
            description=pattern.description,
            pattern_type=pattern.pattern_type.upper(),
            pattern_data=pattern.pattern_data,
            confidence=pattern.confidence.upper(),
            created_at=datetime.now(timezone.utc),
            source_tokens=pattern.source_tokens,
        )

        await repo.create(new_pattern)
        await session.commit()

        return wrap_response({
            "id": new_pattern.id,
            "name": new_pattern.name,
            "pattern_type": new_pattern.pattern_type,
            "created": True,
        })
