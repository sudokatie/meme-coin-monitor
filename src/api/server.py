"""FastAPI server setup."""

import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from src.config import ApiConfig


logger = logging.getLogger(__name__)


_app_state: dict[str, Any] = {}


def get_app_state() -> dict[str, Any]:
    """Get shared application state."""
    return _app_state


def set_app_state(key: str, value: Any) -> None:
    """Set a value in application state."""
    _app_state[key] = value


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan handler."""
    logger.info("API server starting")
    yield
    logger.info("API server stopping")


def create_app(config: ApiConfig) -> FastAPI:
    """
    Create FastAPI application.

    Args:
        config: API configuration

    Returns:
        Configured FastAPI app
    """
    app = FastAPI(
        title="Meme Coin Monitor",
        description="Monitor Solana meme coins for fraud patterns and rug pulls",
        version="0.1.0",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    from src.api.routes import router
    app.include_router(router)

    # Serve dashboard static files
    dashboard_path = Path(__file__).parent.parent.parent / "dashboard"
    if dashboard_path.exists():
        app.mount("/dashboard", StaticFiles(directory=str(dashboard_path), html=True), name="dashboard")
        logger.info(f"Dashboard mounted at /dashboard from {dashboard_path}")

    return app
