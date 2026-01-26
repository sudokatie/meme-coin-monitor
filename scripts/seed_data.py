"""Seed the database with known scam patterns."""

import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path

from src.config import load_config, setup_logging
from src.storage.database import Database
from src.storage.models import Pattern, Wallet
from src.storage.repositories import PatternRepository, WalletRepository


async def seed_database():
    """Load seed data into the database."""
    config = load_config()
    setup_logging(config.logging)

    db = Database(config.database)
    await db.init()

    seed_file = Path("data/patterns/known_scammers.json")
    if not seed_file.exists():
        print(f"Seed file not found: {seed_file}")
        return

    with open(seed_file) as f:
        data = json.load(f)

    async with db.session() as session:
        wallet_repo = WalletRepository(session)
        pattern_repo = PatternRepository(session)

        # Add known scammer wallets
        wallets_added = 0
        for wallet_data in data.get("wallets", []):
            wallet = Wallet(
                address=wallet_data["address"],
                labels=wallet_data.get("labels", []),
                risk_flags=wallet_data.get("risk_flags", ["scammer"]),
                first_seen=datetime.now(timezone.utc),
                notes=wallet_data.get("notes"),
            )
            await wallet_repo.upsert(wallet)
            wallets_added += 1

        # Add name patterns from nested structure
        patterns_added = 0
        name_patterns = data.get("name_patterns", {})
        
        # High risk patterns
        for name in name_patterns.get("high_risk", []):
            pattern = Pattern(
                name=f"High risk name: {name}",
                description=f"Tokens with names similar to '{name}' are high risk",
                pattern_type="NAME",
                pattern_data={"name": name, "risk_level": "high"},
                confidence="0.8",
                created_at=datetime.now(timezone.utc),
                source_tokens=[],
            )
            await pattern_repo.create(pattern)
            patterns_added += 1

        # Medium risk patterns
        for name in name_patterns.get("medium_risk", []):
            pattern = Pattern(
                name=f"Medium risk name: {name}",
                description=f"Tokens with names similar to '{name}' may be risky",
                pattern_type="NAME",
                pattern_data={"name": name, "risk_level": "medium"},
                confidence="0.5",
                created_at=datetime.now(timezone.utc),
                source_tokens=[],
            )
            await pattern_repo.create(pattern)
            patterns_added += 1

        # Add behavioral patterns
        behavioral_added = 0
        for pattern_id, pattern_data in data.get("behavioral_patterns", {}).items():
            pattern = Pattern(
                name=f"Behavioral: {pattern_id}",
                description=pattern_data.get("description", ""),
                pattern_type="BEHAVIORAL",
                pattern_data={
                    "id": pattern_id,
                    "indicators": pattern_data.get("indicators", []),
                    "risk_weight": pattern_data.get("risk_weight", 10),
                },
                confidence="0.7",
                created_at=datetime.now(timezone.utc),
                source_tokens=[],
            )
            await pattern_repo.create(pattern)
            behavioral_added += 1

        print(f"Seeded database:")
        print(f"  - {wallets_added} scammer wallets")
        print(f"  - {patterns_added} name patterns")
        print(f"  - {behavioral_added} behavioral patterns")

    await db.close()


async def clear_and_reseed():
    """Clear existing patterns and reseed."""
    config = load_config()
    setup_logging(config.logging)

    db = Database(config.database)
    await db.init()

    async with db.session() as session:
        # Clear existing data
        from sqlalchemy import delete
        from src.storage.models import Pattern, Wallet
        
        await session.execute(delete(Pattern))
        await session.execute(delete(Wallet))
        await session.commit()
        print("Cleared existing patterns and wallets")

    await db.close()
    
    # Now reseed
    await seed_database()


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == "--clear":
        asyncio.run(clear_and_reseed())
    else:
        asyncio.run(seed_database())
