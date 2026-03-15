"""Telegram delivery channel."""

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any

import httpx

from src.alerts.alert_manager import AlertChannel
from src.storage.models import Alert


logger = logging.getLogger(__name__)


@dataclass
class TelegramThresholds:
    """Configurable thresholds for Telegram alerts.
    
    Allows filtering which alerts are sent to Telegram based on
    risk score, opportunity score, and alert type.
    """
    
    # Minimum risk score to send RUG_WARNING alerts (0-100)
    min_risk_score: int = 0
    
    # Minimum opportunity score to send OPPORTUNITY alerts (0-100)
    min_opportunity_score: int = 0
    
    # Alert types to include (empty = all)
    allowed_alert_types: list[str] = field(default_factory=list)
    
    # Severity levels to include (empty = all)
    allowed_severities: list[str] = field(default_factory=list)
    
    def should_send(self, alert: Alert) -> bool:
        """Check if alert passes threshold filters.
        
        Args:
            alert: Alert to check
            
        Returns:
            True if alert should be sent
        """
        # Check allowed alert types
        if self.allowed_alert_types and alert.alert_type not in self.allowed_alert_types:
            return False
        
        # Check allowed severities
        if self.allowed_severities and alert.severity not in self.allowed_severities:
            return False
        
        # Check risk score threshold for RUG_WARNING
        if alert.alert_type == "RUG_WARNING":
            risk_score = alert.data.get("risk_score", 0)
            if risk_score < self.min_risk_score:
                return False
        
        # Check opportunity score threshold for OPPORTUNITY
        if alert.alert_type == "OPPORTUNITY":
            opp_score = alert.data.get("opportunity_score", 0)
            if opp_score < self.min_opportunity_score:
                return False
        
        return True


class TelegramChannel(AlertChannel):
    """Delivers alerts via Telegram Bot API."""

    API_BASE = "https://api.telegram.org/bot"
    MAX_RETRIES = 3
    TIMEOUT_SECONDS = 10
    
    # Telegram rate limit: 30 messages per second to same chat
    # We use conservative delay between retries
    RATE_LIMIT_DELAY = 1.0

    def __init__(
        self,
        bot_token: str,
        chat_id: str,
        parse_mode: str = "HTML",
        thresholds: TelegramThresholds | None = None,
    ) -> None:
        """
        Initialize Telegram channel.

        Args:
            bot_token: Telegram bot token from @BotFather
            chat_id: Target chat/channel ID
            parse_mode: Message parse mode (HTML or Markdown)
            thresholds: Optional alert thresholds for filtering
        """
        self._bot_token = bot_token
        self._chat_id = chat_id
        self._parse_mode = parse_mode
        self._thresholds = thresholds or TelegramThresholds()
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

    def _severity_prefix(self, severity: str) -> str:
        """Get prefix for severity level."""
        return {
            "CRITICAL": "[!!!]",
            "HIGH": "[!]",
            "MEDIUM": "[*]",
            "LOW": "[-]",
        }.get(severity, "[?]")

    def _format_message(self, alert: Alert) -> str:
        """
        Format alert as Telegram message.

        Args:
            alert: Alert to format

        Returns:
            Formatted message string
        """
        prefix = self._severity_prefix(alert.severity)
        
        # Extract token info from alert data
        token_name = alert.data.get("token_name", "Unknown")
        token_symbol = alert.data.get("token_symbol", "???")
        risk_score = alert.data.get("risk_score", "N/A")
        risk_category = alert.data.get("risk_category", "")
        signals = alert.data.get("signals", [])
        
        # Build message
        lines = [
            f"{prefix} <b>{alert.alert_type}</b> [{alert.severity}]",
            "",
            f"<b>{token_symbol}</b> ({token_name})",
            f"<code>{alert.token_address}</code>",
            "",
            alert.message,
        ]
        
        # Add risk score if present
        if risk_score != "N/A":
            lines.append("")
            lines.append(f"Risk Score: <b>{risk_score}/100</b> ({risk_category})")
        
        # Add opportunity score if present
        opp_score = alert.data.get("opportunity_score")
        if opp_score is not None:
            lines.append(f"Opportunity Score: <b>{opp_score}/100</b>")
        
        # Add top signals
        if signals:
            lines.append("")
            lines.append("Signals:")
            for sig in signals[:5]:
                name = sig.get("name", "Unknown")
                contrib = sig.get("contribution", 0)
                lines.append(f"  • {name}: +{contrib}")
        
        # Add Solscan link
        lines.append("")
        lines.append(f'<a href="https://solscan.io/token/{alert.token_address}">View on Solscan</a>')
        
        return "\n".join(lines)

    async def deliver(self, alert: Alert) -> bool:
        """
        Deliver alert via Telegram.

        Args:
            alert: Alert to deliver

        Returns:
            True if delivery succeeded, False if filtered or failed
        """
        # Check thresholds
        if not self._thresholds.should_send(alert):
            logger.debug(f"Alert filtered by thresholds: {alert.alert_type}")
            return True  # Not an error, just filtered
        
        client = await self._get_client()
        message = self._format_message(alert)
        
        url = f"{self.API_BASE}{self._bot_token}/sendMessage"
        payload = {
            "chat_id": self._chat_id,
            "text": message,
            "parse_mode": self._parse_mode,
            "disable_web_page_preview": True,
        }

        for attempt in range(self.MAX_RETRIES):
            try:
                response = await client.post(url, json=payload)
                data = response.json()

                if response.status_code == 200 and data.get("ok"):
                    logger.debug(f"Telegram delivered: {alert.alert_type}")
                    return True

                # Handle rate limiting
                if response.status_code == 429:
                    retry_after = data.get("parameters", {}).get("retry_after", 5)
                    logger.warning(f"Telegram rate limited, waiting {retry_after}s")
                    await asyncio.sleep(retry_after)
                    continue

                error_desc = data.get("description", "Unknown error")
                logger.warning(
                    f"Telegram API error (attempt {attempt + 1}): "
                    f"{response.status_code} - {error_desc}"
                )

            except httpx.TimeoutException:
                logger.warning(f"Telegram timeout (attempt {attempt + 1})")
            except httpx.RequestError as e:
                logger.warning(f"Telegram request error (attempt {attempt + 1}): {e}")
            except Exception as e:
                logger.error(f"Telegram unexpected error: {e}")

            if attempt < self.MAX_RETRIES - 1:
                delay = self.RATE_LIMIT_DELAY * (2 ** attempt)
                await asyncio.sleep(delay)

        logger.error(f"Telegram delivery failed after {self.MAX_RETRIES} attempts")
        return False

    async def send_test(self) -> bool:
        """
        Send a test message to verify configuration.

        Returns:
            True if test succeeded
        """
        client = await self._get_client()
        
        url = f"{self.API_BASE}{self._bot_token}/sendMessage"
        payload = {
            "chat_id": self._chat_id,
            "text": "Meme Coin Monitor connected successfully.",
            "parse_mode": self._parse_mode,
        }

        try:
            response = await client.post(url, json=payload)
            data = response.json()
            return response.status_code == 200 and data.get("ok", False)
        except Exception as e:
            logger.error(f"Telegram test failed: {e}")
            return False
