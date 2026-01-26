#!/usr/bin/env python3
"""
Data retention cleanup script.

Per SPECS.md Section 6.3:
- Snapshots: keep hourly for 7 days, daily for 90 days, weekly for 1 year
- Raw API responses: 24 hours only (handled by log rotation, not this script)

Run daily via cron to maintain database size.
"""

import asyncio
import logging
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import load_config, setup_logging
from src.storage.database import Database
from src.storage.models import Snapshot


logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


async def cleanup_snapshots(session: AsyncSession) -> dict[str, int]:
    """
    Clean up old snapshots per retention policy.

    Policy:
    - Keep all snapshots from last 7 days (hourly resolution)
    - Keep 1 snapshot per day for 8-90 days ago
    - Keep 1 snapshot per week for 91-365 days ago
    - Delete everything older than 365 days

    Returns:
        Dict with counts of deleted snapshots by category
    """
    now = datetime.now(timezone.utc)
    stats = {
        "hourly_kept": 0,
        "daily_reduced": 0,
        "weekly_reduced": 0,
        "old_deleted": 0,
    }

    # Phase 1: Delete everything older than 1 year
    one_year_ago = now - timedelta(days=365)
    result = await session.execute(
        delete(Snapshot).where(Snapshot.timestamp < one_year_ago)
    )
    stats["old_deleted"] = result.rowcount
    if stats["old_deleted"] > 0:
        logger.info(f"Deleted {stats['old_deleted']} snapshots older than 1 year")

    # Phase 2: Keep only 1 per week for 91-365 days ago
    week_start = now - timedelta(days=365)
    week_end = now - timedelta(days=90)

    # Get all snapshots in this range, grouped by token and week
    snapshots_to_delete = []
    result = await session.execute(
        select(Snapshot)
        .where(Snapshot.timestamp >= week_start)
        .where(Snapshot.timestamp < week_end)
        .order_by(Snapshot.token_address, Snapshot.timestamp)
    )
    snapshots = result.scalars().all()

    # Group by token and ISO week, keep only first in each group
    seen_weeks: dict[str, set[str]] = {}  # token_address -> set of "year-week" strings
    for snapshot in snapshots:
        token = snapshot.token_address
        week_key = snapshot.timestamp.strftime("%Y-%W")

        if token not in seen_weeks:
            seen_weeks[token] = set()

        if week_key in seen_weeks[token]:
            snapshots_to_delete.append(snapshot.id)
        else:
            seen_weeks[token].add(week_key)

    if snapshots_to_delete:
        await session.execute(
            delete(Snapshot).where(Snapshot.id.in_(snapshots_to_delete))
        )
        stats["weekly_reduced"] = len(snapshots_to_delete)
        logger.info(f"Reduced weekly snapshots: deleted {stats['weekly_reduced']}")

    # Phase 3: Keep only 1 per day for 8-90 days ago
    day_start = now - timedelta(days=90)
    day_end = now - timedelta(days=7)

    snapshots_to_delete = []
    result = await session.execute(
        select(Snapshot)
        .where(Snapshot.timestamp >= day_start)
        .where(Snapshot.timestamp < day_end)
        .order_by(Snapshot.token_address, Snapshot.timestamp)
    )
    snapshots = result.scalars().all()

    # Group by token and date, keep only first in each group
    seen_days: dict[str, set[str]] = {}  # token_address -> set of "YYYY-MM-DD" strings
    for snapshot in snapshots:
        token = snapshot.token_address
        day_key = snapshot.timestamp.strftime("%Y-%m-%d")

        if token not in seen_days:
            seen_days[token] = set()

        if day_key in seen_days[token]:
            snapshots_to_delete.append(snapshot.id)
        else:
            seen_days[token].add(day_key)

    if snapshots_to_delete:
        await session.execute(
            delete(Snapshot).where(Snapshot.id.in_(snapshots_to_delete))
        )
        stats["daily_reduced"] = len(snapshots_to_delete)
        logger.info(f"Reduced daily snapshots: deleted {stats['daily_reduced']}")

    await session.commit()
    return stats


async def get_database_stats(session: AsyncSession) -> dict[str, int]:
    """Get current database statistics."""
    result = await session.execute(select(func.count(Snapshot.id)))
    snapshot_count = result.scalar() or 0

    result = await session.execute(
        select(func.count(Snapshot.id))
        .where(Snapshot.timestamp >= datetime.now(timezone.utc) - timedelta(days=7))
    )
    recent_count = result.scalar() or 0

    return {
        "total_snapshots": snapshot_count,
        "snapshots_last_7_days": recent_count,
    }


async def main() -> None:
    """Run the cleanup."""
    try:
        config = load_config()
    except FileNotFoundError:
        logger.error("Config file not found. Run from project root.")
        sys.exit(1)

    setup_logging(config.logging)

    logger.info("Starting data retention cleanup")
    logger.info(f"Database: {config.database.path}")

    database = Database(config.database)
    await database.init()

    try:
        async with database.session() as session:
            # Get stats before cleanup
            before_stats = await get_database_stats(session)
            logger.info(f"Before cleanup: {before_stats['total_snapshots']} total snapshots")

            # Run cleanup
            cleanup_stats = await cleanup_snapshots(session)

            # Get stats after cleanup
            after_stats = await get_database_stats(session)
            logger.info(f"After cleanup: {after_stats['total_snapshots']} total snapshots")

            total_deleted = (
                cleanup_stats["old_deleted"]
                + cleanup_stats["weekly_reduced"]
                + cleanup_stats["daily_reduced"]
            )

            logger.info(f"Cleanup complete. Deleted {total_deleted} snapshots total.")
            logger.info(f"  - Older than 1 year: {cleanup_stats['old_deleted']}")
            logger.info(f"  - Weekly reduction (91-365d): {cleanup_stats['weekly_reduced']}")
            logger.info(f"  - Daily reduction (8-90d): {cleanup_stats['daily_reduced']}")

    finally:
        await database.close()


if __name__ == "__main__":
    asyncio.run(main())
