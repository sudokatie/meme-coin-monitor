"""User authentication models."""

import secrets
from datetime import datetime, timedelta
from typing import Optional

import bcrypt
from sqlalchemy import Column, String, DateTime, Boolean
from sqlalchemy.orm import declarative_base

Base = declarative_base()


class User(Base):
    """User model for authentication."""
    
    __tablename__ = "users"
    
    username = Column(String(50), primary_key=True)
    password_hash = Column(String(128), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    last_login = Column(DateTime, nullable=True)
    is_active = Column(Boolean, default=True)
    
    @staticmethod
    def hash_password(password: str) -> str:
        """Hash a password using bcrypt."""
        salt = bcrypt.gensalt(rounds=12)
        return bcrypt.hashpw(password.encode('utf-8'), salt).decode('utf-8')
    
    def verify_password(self, password: str) -> bool:
        """Verify a password against the stored hash."""
        return bcrypt.checkpw(
            password.encode('utf-8'),
            self.password_hash.encode('utf-8')
        )


class Session(Base):
    """Session model for tracking logged-in users."""
    
    __tablename__ = "sessions"
    
    session_id = Column(String(64), primary_key=True)
    username = Column(String(50), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=False)
    ip_address = Column(String(45), nullable=True)
    user_agent = Column(String(256), nullable=True)
    
    @staticmethod
    def generate_session_id() -> str:
        """Generate a cryptographically secure session ID."""
        return secrets.token_hex(32)
    
    @staticmethod
    def default_expiry() -> datetime:
        """Get default session expiry (24 hours from now)."""
        return datetime.utcnow() + timedelta(hours=24)
    
    def is_valid(self) -> bool:
        """Check if session is still valid."""
        return datetime.utcnow() < self.expires_at
