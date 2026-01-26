"""Authentication middleware for protecting routes."""

import logging
from typing import Callable

from fastapi import Request, Response
from fastapi.responses import RedirectResponse, JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from src.api.server import get_app_state
from src.auth.repository import AuthRepository


logger = logging.getLogger(__name__)

SESSION_COOKIE = "mcm_session"

# Paths that don't require authentication
PUBLIC_PATHS = {
    "/health",
    "/auth/login",
    "/auth/logout",
    "/auth/session",
    "/login",
    "/login.html",
    "/docs",
    "/openapi.json",
    "/redoc",
}

# Path prefixes that don't require authentication
PUBLIC_PREFIXES = [
    "/static/",
]


class AuthMiddleware(BaseHTTPMiddleware):
    """Middleware to check authentication on protected routes."""
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        path = request.url.path
        
        # Check if path is public
        if self._is_public_path(path):
            return await call_next(request)
        
        # Check authentication
        session_id = request.cookies.get(SESSION_COOKIE)
        
        if not session_id:
            return self._unauthorized_response(request)
        
        # Verify session
        state = get_app_state()
        if "database" not in state:
            return await call_next(request)
        
        try:
            async with state["database"].session() as session:
                repo = AuthRepository(session)
                auth_session = await repo.get_session(session_id)
                
                if not auth_session or not auth_session.is_valid():
                    return self._unauthorized_response(request)
                
                # Store username in request state for use in routes
                request.state.username = auth_session.username
        except Exception as e:
            logger.error(f"Auth middleware error: {e}")
            return self._unauthorized_response(request)
        
        return await call_next(request)
    
    def _is_public_path(self, path: str) -> bool:
        """Check if path is public (no auth required)."""
        if path in PUBLIC_PATHS:
            return True
        
        for prefix in PUBLIC_PREFIXES:
            if path.startswith(prefix):
                return True
        
        return False
    
    def _unauthorized_response(self, request: Request) -> Response:
        """Return appropriate unauthorized response."""
        # For API requests, return JSON
        if request.url.path.startswith("/token") or \
           request.url.path.startswith("/alerts") or \
           request.url.path.startswith("/watch"):
            return JSONResponse(
                status_code=401,
                content={"error": {"code": "UNAUTHORIZED", "message": "Authentication required"}}
            )
        
        # For dashboard/HTML requests, redirect to login
        return RedirectResponse(url="/login", status_code=302)
