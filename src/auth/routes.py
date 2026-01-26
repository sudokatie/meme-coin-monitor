"""Authentication API routes."""

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel

from src.api.server import get_app_state
from src.auth.repository import AuthRepository


logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["auth"])

SESSION_COOKIE = "mcm_session"
COOKIE_MAX_AGE = 86400  # 24 hours


class LoginRequest(BaseModel):
    """Login request body."""
    username: str
    password: str


class LoginResponse(BaseModel):
    """Login response."""
    success: bool
    username: Optional[str] = None
    message: Optional[str] = None


class SessionResponse(BaseModel):
    """Session check response."""
    authenticated: bool
    username: Optional[str] = None


def get_session_cookie(request: Request) -> Optional[str]:
    """Extract session ID from cookies."""
    return request.cookies.get(SESSION_COOKIE)


@router.post("/login")
async def login(request: Request, response: Response, body: LoginRequest) -> dict:
    """
    Authenticate user and create session.
    
    Sets a secure HTTP-only cookie with the session ID.
    """
    state = get_app_state()
    
    if "database" not in state:
        raise HTTPException(status_code=500, detail="Database not available")
    
    async with state["database"].session() as session:
        repo = AuthRepository(session)
        
        # Get user
        user = await repo.get_user(body.username)
        if not user:
            logger.warning(f"Login attempt for unknown user: {body.username}")
            raise HTTPException(status_code=401, detail="Invalid credentials")
        
        # Verify password
        if not user.verify_password(body.password):
            logger.warning(f"Invalid password for user: {body.username}")
            raise HTTPException(status_code=401, detail="Invalid credentials")
        
        if not user.is_active:
            logger.warning(f"Login attempt for inactive user: {body.username}")
            raise HTTPException(status_code=401, detail="Account disabled")
        
        # Create session
        client_ip = request.client.host if request.client else None
        user_agent = request.headers.get("user-agent", "")[:256]
        
        auth_session = await repo.create_session(
            username=user.username,
            ip_address=client_ip,
            user_agent=user_agent
        )
        
        await repo.update_last_login(user.username)
        
        # Set session cookie
        response.set_cookie(
            key=SESSION_COOKIE,
            value=auth_session.session_id,
            max_age=COOKIE_MAX_AGE,
            httponly=True,
            samesite="lax",
            secure=False,  # Set to True in production with HTTPS
        )
        
        logger.info(f"User logged in: {body.username}")
        
        return {"data": {"success": True, "username": user.username}}


@router.post("/logout")
async def logout(request: Request, response: Response) -> dict:
    """
    Logout user and invalidate session.
    """
    session_id = get_session_cookie(request)
    
    if session_id:
        state = get_app_state()
        if "database" in state:
            async with state["database"].session() as session:
                repo = AuthRepository(session)
                await repo.delete_session(session_id)
    
    # Clear cookie
    response.delete_cookie(key=SESSION_COOKIE)
    
    return {"data": {"success": True}}


@router.get("/session")
async def check_session(request: Request) -> dict:
    """
    Check if current session is valid.
    """
    session_id = get_session_cookie(request)
    
    if not session_id:
        return {"data": {"authenticated": False}}
    
    state = get_app_state()
    if "database" not in state:
        return {"data": {"authenticated": False}}
    
    async with state["database"].session() as session:
        repo = AuthRepository(session)
        auth_session = await repo.get_session(session_id)
        
        if auth_session and auth_session.is_valid():
            return {"data": {"authenticated": True, "username": auth_session.username}}
    
    return {"data": {"authenticated": False}}
