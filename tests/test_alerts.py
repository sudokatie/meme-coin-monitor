"""Tests for alerts module."""

from datetime import datetime, timezone

import pytest

from src.alerts.telegram import TelegramChannel
from src.alerts.webhook import WebhookChannel
from src.storage.models import Alert


class TestTelegramChannel:
    """Tests for TelegramChannel."""

    def test_format_message_critical(self):
        """Critical alerts should format with proper emoji and structure."""
        channel = TelegramChannel("test_token", "test_chat")
        
        alert = Alert(
            token_address="So11111111111111111111111111111111111111112",
            alert_type="RUG_WARNING",
            severity="CRITICAL",
            message="CRITICAL risk detected",
            data={
                "token_name": "Test Token",
                "token_symbol": "TEST",
                "risk_score": 85,
                "risk_category": "CRITICAL",
                "signals": [
                    {"name": "MINT_AUTHORITY_ACTIVE", "contribution": 25},
                    {"name": "HIGH_CONCENTRATION", "contribution": 20},
                ],
            },
            created_at=datetime.now(timezone.utc),
        )
        
        message = channel._format_message(alert)
        
        assert "[!!!]" in message  # Critical prefix
        assert "<b>RUG_WARNING</b>" in message
        assert "[CRITICAL]" in message
        assert "TEST" in message
        assert "Test Token" in message
        assert "85/100" in message
        assert "MINT_AUTHORITY_ACTIVE" in message
        assert "solscan.io" in message

    def test_format_message_high(self):
        """High severity alerts should use warning emoji."""
        channel = TelegramChannel("test_token", "test_chat")
        
        alert = Alert(
            token_address="test_address",
            alert_type="RUG_WARNING",
            severity="HIGH",
            message="High risk detected",
            data={
                "token_name": "Risky Token",
                "token_symbol": "RISK",
                "risk_score": 65,
                "risk_category": "HIGH",
                "signals": [],
            },
            created_at=datetime.now(timezone.utc),
        )
        
        message = channel._format_message(alert)
        
        assert "[!]" in message  # High severity prefix

    def test_format_message_opportunity(self):
        """Opportunity alerts should include opportunity score."""
        channel = TelegramChannel("test_token", "test_chat")
        
        alert = Alert(
            token_address="test_address",
            alert_type="OPPORTUNITY",
            severity="HIGH",
            message="Strong opportunity found",
            data={
                "token_name": "Good Token",
                "token_symbol": "GOOD",
                "risk_score": 25,
                "risk_category": "LOW",
                "opportunity_score": 80,
                "signals": [],
            },
            created_at=datetime.now(timezone.utc),
        )
        
        message = channel._format_message(alert)
        
        assert "Opportunity Score: <b>80/100</b>" in message

    def test_severity_prefix_mapping(self):
        """All severity levels should have prefixes."""
        channel = TelegramChannel("test_token", "test_chat")
        
        assert channel._severity_prefix("CRITICAL") == "[!!!]"
        assert channel._severity_prefix("HIGH") == "[!]"
        assert channel._severity_prefix("MEDIUM") == "[*]"
        assert channel._severity_prefix("LOW") == "[-]"
        assert channel._severity_prefix("UNKNOWN") == "[?]"  # Default


class TestWebhookChannel:
    """Tests for WebhookChannel."""

    def test_format_payload(self):
        """Payload should contain all required fields."""
        channel = WebhookChannel("https://example.com/webhook")
        
        alert = Alert(
            token_address="test_address_123",
            alert_type="PATTERN_MATCH",
            severity="CRITICAL",
            message="Known scammer detected",
            data={"extra": "data"},
            created_at=datetime(2025, 1, 25, 12, 0, 0, tzinfo=timezone.utc),
        )
        
        payload = channel._format_payload(alert)
        
        assert payload["type"] == "alert"
        assert payload["alert_type"] == "PATTERN_MATCH"
        assert payload["severity"] == "CRITICAL"
        assert payload["token_address"] == "test_address_123"
        assert payload["message"] == "Known scammer detected"
        assert payload["data"] == {"extra": "data"}
        assert "2025-01-25" in payload["timestamp"]
