"""Webhook delivery channel."""

import asyncio
import logging
from datetime import datetime
from typing import Any

import httpx

from src.alerts.alert_manager import AlertChannel
from src.storage.models import Alert


logger = logging.getLogger(__name__)


class WebhookChannel(AlertChannel):
    """Delivers alerts via HTTP webhook."""

    MAX_RETRIES = 3
    TIMEOUT_SECONDS = 5

    def __init__(
        self,
        webhook_url: str,
        headers: dict[str, str] | None = None,
    ) -> None:
        """
        Initialize webhook channel.

        Args:
            webhook_url: URL to POST alerts to
            headers: Optional custom headers
        """
        self._url = webhook_url
        self._headers = headers or {}
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(self.TIMEOUT_SECONDS),
            )
        return self._client

    async def close(self) -> None:
        """Close HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None

    def _format_payload(self, alert: Alert) -> dict[str, Any]:
        """Format alert as JSON payload."""
        return {
            "type": "alert",
            "alert_type": alert.alert_type,
            "severity": alert.severity,
            "token_address": alert.token_address,
            "message": alert.message,
            "data": alert.data,
            "timestamp": alert.created_at.isoformat() + "Z",
        }

    async def deliver(self, alert: Alert) -> bool:
        """
        Deliver alert via webhook.

        Args:
            alert: Alert to deliver

        Returns:
            True if delivery succeeded
        """
        client = await self._get_client()
        payload = self._format_payload(alert)

        for attempt in range(self.MAX_RETRIES):
            try:
                response = await client.post(
                    self._url,
                    json=payload,
                    headers=self._headers,
                )

                if 200 <= response.status_code < 300:
                    logger.debug(f"Webhook delivered: {alert.alert_type}")
                    return True

                logger.warning(
                    f"Webhook returned {response.status_code}: {response.text[:100]}"
                )

            except httpx.TimeoutException:
                logger.warning(f"Webhook timeout (attempt {attempt + 1})")
            except httpx.RequestError as e:
                logger.warning(f"Webhook error (attempt {attempt + 1}): {e}")

            if attempt < self.MAX_RETRIES - 1:
                delay = 2 ** attempt
                await asyncio.sleep(delay)

        logger.error(f"Webhook delivery failed after {self.MAX_RETRIES} attempts")
        logger.debug(f"Failed payload: {payload}")
        return False
