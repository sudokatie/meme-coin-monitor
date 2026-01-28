"""SQLAlchemy database models."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, Index, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Base class for all models."""

    pass


def generate_uuid() -> str:
    """Generate a new UUID string."""
    return str(uuid.uuid4())


class Token(Base):
    """Token model - stores token metadata."""

    __tablename__ = "tokens"

    address: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    symbol: Mapped[str] = mapped_column(String(32), nullable=False)
    decimals: Mapped[int] = mapped_column(Integer, nullable=False, default=9)
    created_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    first_seen: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    mint_authority: Mapped[str | None] = mapped_column(String(64), nullable=True)
    freeze_authority: Mapped[str | None] = mapped_column(String(64), nullable=True)
    deployer: Mapped[str] = mapped_column(String(64), nullable=False)
    metadata_uri: Mapped[str | None] = mapped_column(Text, nullable=True)

    def __repr__(self) -> str:
        return f"<Token {self.symbol} ({self.address[:8]}...)>"


class Snapshot(Base):
    """Snapshot model - stores point-in-time token data."""

    __tablename__ = "snapshots"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=generate_uuid
    )
    token_address: Mapped[str] = mapped_column(
        String(64), nullable=False, index=True
    )
    timestamp: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    price_usd: Mapped[str | None] = mapped_column(String(64), nullable=True)
    market_cap: Mapped[str | None] = mapped_column(String(64), nullable=True)
    volume_24h: Mapped[str | None] = mapped_column(String(64), nullable=True)
    liquidity_usd: Mapped[str | None] = mapped_column(String(64), nullable=True)
    holder_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    top_10_pct: Mapped[str | None] = mapped_column(String(16), nullable=True)
    risk_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    opportunity_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    confidence: Mapped[str | None] = mapped_column(String(16), nullable=True)

    __table_args__ = (
        Index("ix_snapshots_token_timestamp", "token_address", "timestamp"),
    )

    def __repr__(self) -> str:
        return f"<Snapshot {self.token_address[:8]}... @ {self.timestamp}>"


class Alert(Base):
    """Alert model - stores generated alerts."""

    __tablename__ = "alerts"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=generate_uuid
    )
    token_address: Mapped[str] = mapped_column(
        String(64), nullable=False, index=True
    )
    alert_type: Mapped[str] = mapped_column(String(32), nullable=False)
    severity: Mapped[str] = mapped_column(String(16), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    data: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    acknowledged: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    __table_args__ = (
        Index("ix_alerts_token_type", "token_address", "alert_type"),
    )

    def __repr__(self) -> str:
        return f"<Alert {self.alert_type} [{self.severity}] {self.token_address[:8]}...>"


class Pattern(Base):
    """Pattern model - stores known fraud patterns."""

    __tablename__ = "patterns"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=generate_uuid
    )
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    pattern_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    pattern_data: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    confidence: Mapped[str] = mapped_column(String(16), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    source_tokens: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)

    def __repr__(self) -> str:
        return f"<Pattern {self.name} ({self.pattern_type})>"


class Wallet(Base):
    """Wallet model - stores known wallet information."""

    __tablename__ = "wallets"

    address: Mapped[str] = mapped_column(String(64), primary_key=True)
    labels: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    risk_flags: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    first_seen: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    def __repr__(self) -> str:
        labels_str = ", ".join(self.labels[:2]) if self.labels else "no labels"
        return f"<Wallet {self.address[:8]}... ({labels_str})>"


class OpportunityReview(Base):
    """Tracks follow-up reviews of opportunity tokens for ML training data."""

    __tablename__ = "opportunity_reviews"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=generate_uuid
    )
    token_address: Mapped[str] = mapped_column(
        String(64), nullable=False, index=True
    )
    alert_id: Mapped[str] = mapped_column(String(36), nullable=False)
    
    # Initial state when opportunity was flagged
    initial_timestamp: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    initial_price_usd: Mapped[str | None] = mapped_column(String(64), nullable=True)
    initial_market_cap: Mapped[str | None] = mapped_column(String(64), nullable=True)
    initial_liquidity_usd: Mapped[str | None] = mapped_column(String(64), nullable=True)
    initial_holder_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    initial_risk_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    initial_opportunity_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    
    # 1-day follow-up
    day1_reviewed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    day1_timestamp: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    day1_price_usd: Mapped[str | None] = mapped_column(String(64), nullable=True)
    day1_market_cap: Mapped[str | None] = mapped_column(String(64), nullable=True)
    day1_liquidity_usd: Mapped[str | None] = mapped_column(String(64), nullable=True)
    day1_holder_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    day1_risk_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    day1_price_change_pct: Mapped[str | None] = mapped_column(String(32), nullable=True)
    day1_rugged: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    day1_rug_reason: Mapped[str | None] = mapped_column(String(256), nullable=True)
    
    # 1-week follow-up
    week1_reviewed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    week1_timestamp: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    week1_price_usd: Mapped[str | None] = mapped_column(String(64), nullable=True)
    week1_market_cap: Mapped[str | None] = mapped_column(String(64), nullable=True)
    week1_liquidity_usd: Mapped[str | None] = mapped_column(String(64), nullable=True)
    week1_holder_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    week1_risk_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    week1_price_change_pct: Mapped[str | None] = mapped_column(String(32), nullable=True)
    week1_rugged: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    week1_rug_reason: Mapped[str | None] = mapped_column(String(256), nullable=True)
    
    # Final outcome classification for ML
    final_outcome: Mapped[str | None] = mapped_column(String(32), nullable=True)  # SURVIVED, RUGGED, DEAD, MOONED
    outcome_notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        Index("ix_opportunity_reviews_pending_day1", "day1_reviewed", "initial_timestamp"),
        Index("ix_opportunity_reviews_pending_week1", "week1_reviewed", "initial_timestamp"),
    )

    def __repr__(self) -> str:
        return f"<OpportunityReview {self.token_address[:8]}... outcome={self.final_outcome}>"
