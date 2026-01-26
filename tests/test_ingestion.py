"""Tests for ingestion modules."""

import pytest

from src.ingestion.base import TokenData
from src.utils.solana import is_valid_address


class TestTokenData:
    """Tests for TokenData class."""

    def test_token_data_creation(self):
        """TokenData should be created with required fields."""
        token = TokenData(
            address="So11111111111111111111111111111111111111112",
            name="Wrapped SOL",
            symbol="SOL",
        )

        assert token.address == "So11111111111111111111111111111111111111112"
        assert token.name == "Wrapped SOL"
        assert token.symbol == "SOL"
        assert token.price_usd is None

    def test_token_data_with_optional_fields(self):
        """TokenData should accept optional fields."""
        token = TokenData(
            address="test",
            name="Test",
            symbol="TEST",
            price_usd="1.00",
            market_cap="1000000",
            volume_24h="50000",
        )

        assert token.price_usd == "1.00"
        assert token.market_cap == "1000000"
        assert token.volume_24h == "50000"

    def test_token_data_repr(self):
        """TokenData repr should be readable."""
        token = TokenData(
            address="ABC123456789012345678901234567890123456789012",
            name="Test",
            symbol="TEST",
            price_usd="1.00",
        )

        repr_str = repr(token)
        assert "TEST" in repr_str
        assert "ABC12345" in repr_str


class TestAddressValidation:
    """Tests for Solana address validation."""

    def test_valid_address(self):
        """Valid Solana addresses should pass."""
        # Wrapped SOL address
        assert is_valid_address("So11111111111111111111111111111111111111112")
        # USDC address
        assert is_valid_address("EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v")

    def test_invalid_address_too_short(self):
        """Short addresses should fail."""
        assert not is_valid_address("short")

    def test_invalid_address_bad_chars(self):
        """Addresses with invalid characters should fail."""
        assert not is_valid_address("0OIl11111111111111111111111111111111111111")  # 0, O, I, l not in base58

    def test_empty_address(self):
        """Empty address should fail."""
        assert not is_valid_address("")
