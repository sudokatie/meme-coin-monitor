"""Data access repositories."""

import logging
from datetime import datetime
from typing import Sequence

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.storage.models import Alert, Pattern, Snapshot, Token, Wallet


logger = logging.getLogger(__name__)


class TokenRepository:
    """Repository for Token operations."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_address(self, address: str) -> Token | None:
        """Get a token by address."""
        result = await self._session.execute(
            select(Token).where(Token.address == address)
        )
        return result.scalar_one_or_none()

    async def upsert(self, token: Token) -> Token:
        """Insert or update a token."""
        existing = await self.get_by_address(token.address)
        if existing:
            existing.name = token.name
            existing.symbol = token.symbol
            existing.decimals = token.decimals
            existing.mint_authority = token.mint_authority
            existing.freeze_authority = token.freeze_authority
            existing.deployer = token.deployer
            existing.metadata_uri = token.metadata_uri
            if token.created_at:
                existing.created_at = token.created_at
            return existing
        else:
            self._session.add(token)
            return token

    async def list_all(self, limit: int = 100) -> Sequence[Token]:
        """List all tokens."""
        result = await self._session.execute(
            select(Token).order_by(Token.first_seen.desc()).limit(limit)
        )
        return result.scalars().all()


class SnapshotRepository:
    """Repository for Snapshot operations."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, snapshot: Snapshot) -> Snapshot:
        """Create a new snapshot."""
        self._session.add(snapshot)
        return snapshot

    async def get_latest(self, token_address: str) -> Snapshot | None:
        """Get the most recent snapshot for a token."""
        result = await self._session.execute(
            select(Snapshot)
            .where(Snapshot.token_address == token_address)
            .order_by(Snapshot.timestamp.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def get_history(
        self,
        token_address: str,
        start: datetime | None = None,
        end: datetime | None = None,
        limit: int = 100,
    ) -> Sequence[Snapshot]:
        """Get snapshot history for a token."""
        query = select(Snapshot).where(Snapshot.token_address == token_address)

        if start:
            query = query.where(Snapshot.timestamp >= start)
        if end:
            query = query.where(Snapshot.timestamp <= end)

        query = query.order_by(Snapshot.timestamp.desc()).limit(limit)
        result = await self._session.execute(query)
        return result.scalars().all()

    async def get_risky(self, threshold: int = 51, limit: int = 20) -> Sequence[Snapshot]:
        """Get recent snapshots with high risk scores."""
        subquery = (
            select(Snapshot.token_address, Snapshot.timestamp)
            .distinct(Snapshot.token_address)
            .order_by(Snapshot.token_address, Snapshot.timestamp.desc())
        ).subquery()

        result = await self._session.execute(
            select(Snapshot)
            .join(
                subquery,
                (Snapshot.token_address == subquery.c.token_address)
                & (Snapshot.timestamp == subquery.c.timestamp),
            )
            .where(Snapshot.risk_score >= threshold)
            .order_by(Snapshot.risk_score.desc())
            .limit(limit)
        )
        return result.scalars().all()

    async def get_opportunities(
        self, min_score: int = 50, max_risk: int = 50, limit: int = 20
    ) -> Sequence[Snapshot]:
        """Get recent snapshots with high opportunity scores."""
        subquery = (
            select(Snapshot.token_address, Snapshot.timestamp)
            .distinct(Snapshot.token_address)
            .order_by(Snapshot.token_address, Snapshot.timestamp.desc())
        ).subquery()

        result = await self._session.execute(
            select(Snapshot)
            .join(
                subquery,
                (Snapshot.token_address == subquery.c.token_address)
                & (Snapshot.timestamp == subquery.c.timestamp),
            )
            .where(Snapshot.opportunity_score >= min_score)
            .where(Snapshot.risk_score < max_risk)
            .order_by(Snapshot.opportunity_score.desc())
            .limit(limit)
        )
        return result.scalars().all()


class AlertRepository:
    """Repository for Alert operations."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, alert: Alert) -> Alert:
        """Create a new alert."""
        self._session.add(alert)
        return alert

    async def get_recent(
        self,
        limit: int = 50,
        alert_type: str | None = None,
        severity: str | None = None,
    ) -> Sequence[Alert]:
        """Get recent alerts with optional filters."""
        query = select(Alert)

        if alert_type:
            query = query.where(Alert.alert_type == alert_type)
        if severity:
            query = query.where(Alert.severity == severity)

        query = query.order_by(Alert.created_at.desc()).limit(limit)
        result = await self._session.execute(query)
        return result.scalars().all()

    async def get_by_token(
        self, token_address: str, limit: int = 20
    ) -> Sequence[Alert]:
        """Get alerts for a specific token."""
        result = await self._session.execute(
            select(Alert)
            .where(Alert.token_address == token_address)
            .order_by(Alert.created_at.desc())
            .limit(limit)
        )
        return result.scalars().all()

    async def mark_acknowledged(self, alert_id: str) -> bool:
        """Mark an alert as acknowledged."""
        result = await self._session.execute(
            update(Alert)
            .where(Alert.id == alert_id)
            .values(acknowledged=True)
        )
        return result.rowcount > 0

    async def get_last_alert_time(
        self, token_address: str, alert_type: str
    ) -> datetime | None:
        """Get the timestamp of the last alert for throttling."""
        result = await self._session.execute(
            select(Alert.created_at)
            .where(Alert.token_address == token_address)
            .where(Alert.alert_type == alert_type)
            .order_by(Alert.created_at.desc())
            .limit(1)
        )
        row = result.scalar_one_or_none()
        return row


class PatternRepository:
    """Repository for Pattern operations."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_all(self, limit: int = 100) -> Sequence[Pattern]:
        """Get all patterns."""
        result = await self._session.execute(
            select(Pattern).order_by(Pattern.created_at.desc()).limit(limit)
        )
        return result.scalars().all()

    async def get_by_type(self, pattern_type: str) -> Sequence[Pattern]:
        """Get patterns of a specific type."""
        result = await self._session.execute(
            select(Pattern).where(Pattern.pattern_type == pattern_type)
        )
        return result.scalars().all()

    async def create(self, pattern: Pattern) -> Pattern:
        """Create a new pattern."""
        self._session.add(pattern)
        return pattern

    async def update(self, pattern_id: str, **kwargs) -> bool:
        """Update a pattern."""
        result = await self._session.execute(
            update(Pattern).where(Pattern.id == pattern_id).values(**kwargs)
        )
        return result.rowcount > 0

    async def delete(self, pattern_id: str) -> bool:
        """Delete a pattern."""
        result = await self._session.execute(
            delete(Pattern).where(Pattern.id == pattern_id)
        )
        return result.rowcount > 0


class WalletRepository:
    """Repository for Wallet operations."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_address(self, address: str) -> Wallet | None:
        """Get a wallet by address."""
        result = await self._session.execute(
            select(Wallet).where(Wallet.address == address)
        )
        return result.scalar_one_or_none()

    async def upsert(self, wallet: Wallet) -> Wallet:
        """Insert or update a wallet."""
        existing = await self.get_by_address(wallet.address)
        if existing:
            existing.labels = wallet.labels
            existing.risk_flags = wallet.risk_flags
            existing.notes = wallet.notes
            return existing
        else:
            self._session.add(wallet)
            return wallet

    async def get_flagged(self, flag: str | None = None) -> Sequence[Wallet]:
        """Get wallets with risk flags."""
        query = select(Wallet).where(Wallet.risk_flags != [])

        if flag:
            query = query.where(Wallet.risk_flags.contains([flag]))

        result = await self._session.execute(query)
        return result.scalars().all()

    async def get_scammers(self) -> Sequence[Wallet]:
        """Get wallets flagged as known scammers."""
        return await self.get_flagged("scammer")
