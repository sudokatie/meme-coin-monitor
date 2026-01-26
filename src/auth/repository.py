"""Authentication repository for database operations."""

from datetime import datetime
from typing import Optional

from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.models import User, Session


class AuthRepository:
    """Repository for auth-related database operations."""
    
    def __init__(self, session: AsyncSession):
        self.session = session
    
    async def get_user(self, username: str) -> Optional[User]:
        """Get user by username."""
        result = await self.session.execute(
            select(User).where(User.username == username)
        )
        return result.scalar_one_or_none()
    
    async def create_user(self, username: str, password: str) -> User:
        """Create a new user."""
        user = User(
            username=username,
            password_hash=User.hash_password(password)
        )
        self.session.add(user)
        await self.session.commit()
        return user
    
    async def update_last_login(self, username: str) -> None:
        """Update user's last login timestamp."""
        user = await self.get_user(username)
        if user:
            user.last_login = datetime.utcnow()
            await self.session.commit()
    
    async def create_session(
        self,
        username: str,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None
    ) -> Session:
        """Create a new session for a user."""
        session = Session(
            session_id=Session.generate_session_id(),
            username=username,
            expires_at=Session.default_expiry(),
            ip_address=ip_address,
            user_agent=user_agent
        )
        self.session.add(session)
        await self.session.commit()
        return session
    
    async def get_session(self, session_id: str) -> Optional[Session]:
        """Get session by ID."""
        result = await self.session.execute(
            select(Session).where(Session.session_id == session_id)
        )
        return result.scalar_one_or_none()
    
    async def delete_session(self, session_id: str) -> bool:
        """Delete a session (logout)."""
        result = await self.session.execute(
            delete(Session).where(Session.session_id == session_id)
        )
        await self.session.commit()
        return result.rowcount > 0
    
    async def delete_user_sessions(self, username: str) -> int:
        """Delete all sessions for a user."""
        result = await self.session.execute(
            delete(Session).where(Session.username == username)
        )
        await self.session.commit()
        return result.rowcount
    
    async def cleanup_expired_sessions(self) -> int:
        """Remove expired sessions."""
        result = await self.session.execute(
            delete(Session).where(Session.expires_at < datetime.utcnow())
        )
        await self.session.commit()
        return result.rowcount
