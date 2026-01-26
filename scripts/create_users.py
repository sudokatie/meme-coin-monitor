#!/usr/bin/env python3
"""Create initial users for the meme coin monitor."""

import asyncio
import secrets
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

from src.auth.models import Base, User


def generate_password(length: int = 24) -> str:
    """Generate a secure random password."""
    # Use a mix of alphanumeric characters
    alphabet = "abcdefghijkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    return ''.join(secrets.choice(alphabet) for _ in range(length))


async def create_users(db_path: str, users: dict[str, str]) -> None:
    """Create users in the database."""
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}")
    
    async with engine.begin() as conn:
        # Create auth tables
        await conn.run_sync(Base.metadata.create_all)
    
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    
    async with async_session() as session:
        for username, password in users.items():
            # Check if user exists
            result = await session.execute(
                text("SELECT username FROM users WHERE username = :username"),
                {"username": username}
            )
            existing = result.scalar_one_or_none()
            
            if existing:
                print(f"User '{username}' already exists, updating password...")
                await session.execute(
                    text("UPDATE users SET password_hash = :hash WHERE username = :username"),
                    {"username": username, "hash": User.hash_password(password)}
                )
            else:
                print(f"Creating user '{username}'...")
                user = User(
                    username=username,
                    password_hash=User.hash_password(password)
                )
                session.add(user)
            
            await session.commit()
            print(f"  Username: {username}")
            print(f"  Password: {password}")
            print()
    
    await engine.dispose()


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="Create users for meme coin monitor")
    parser.add_argument("--db", default="data/meme_monitor.db", help="Database path")
    parser.add_argument("--user", action="append", nargs=2, metavar=("USERNAME", "PASSWORD"),
                        help="Add user with specific password")
    parser.add_argument("--generate", action="append", metavar="USERNAME",
                        help="Generate password for user")
    
    args = parser.parse_args()
    
    users = {}
    
    # Add users with specific passwords
    if args.user:
        for username, password in args.user:
            users[username] = password
    
    # Add users with generated passwords
    if args.generate:
        for username in args.generate:
            users[username] = generate_password()
    
    if not users:
        # Default: create katie and slippage with generated passwords
        users = {
            "katie": generate_password(),
            "slippage": generate_password(),
        }
    
    print("=" * 50)
    print("Creating users for Meme Coin Monitor")
    print("=" * 50)
    print()
    
    asyncio.run(create_users(args.db, users))
    
    print("=" * 50)
    print("Users created successfully!")
    print("=" * 50)


if __name__ == "__main__":
    main()
