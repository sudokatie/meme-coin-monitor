"""Pytest configuration and fixtures."""

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from src.storage.models import Base


@pytest_asyncio.fixture
async def db_session():
    """Create an in-memory database session for testing."""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=False,
    )

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    async with session_factory() as session:
        yield session

    await engine.dispose()


@pytest.fixture
def sample_token_data():
    """Sample token data for testing."""
    return {
        "address": "So11111111111111111111111111111111111111112",
        "name": "Test Token",
        "symbol": "TEST",
        "price_usd": "0.001",
        "market_cap": "1000000",
        "volume_24h": "50000",
        "liquidity_usd": "100000",
    }


@pytest.fixture
def sample_scam_token_data():
    """Sample scam token data for testing."""
    return {
        "address": "ScamTokenAddress1111111111111111111111111",
        "name": "SafeMoon Inu",
        "symbol": "SAFEMOONINU",
        "price_usd": "0.0000001",
        "market_cap": "500000",
        "volume_24h": "5000000",
        "liquidity_usd": "500",
    }
