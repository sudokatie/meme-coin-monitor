"""Tests for EVM RPC clients (Base, Arbitrum)."""

import pytest

from src.ingestion.evm_rpc import (
    ArbitrumRpcClient,
    BaseChainRpcClient,
    EvmRpcClient,
    EvmTokenInfo,
    decode_string_response,
    decode_uint256_response,
    is_valid_evm_address,
)


class TestAddressValidation:
    """Tests for EVM address validation."""

    def test_valid_address(self) -> None:
        """Valid EVM address should pass."""
        assert is_valid_evm_address("0x1234567890abcdef1234567890abcdef12345678")

    def test_valid_address_uppercase(self) -> None:
        """Valid address with uppercase should pass."""
        assert is_valid_evm_address("0x1234567890ABCDEF1234567890ABCDEF12345678")

    def test_invalid_no_prefix(self) -> None:
        """Address without 0x prefix should fail."""
        assert not is_valid_evm_address("1234567890abcdef1234567890abcdef12345678")

    def test_invalid_too_short(self) -> None:
        """Address too short should fail."""
        assert not is_valid_evm_address("0x1234567890abcdef")

    def test_invalid_too_long(self) -> None:
        """Address too long should fail."""
        assert not is_valid_evm_address("0x1234567890abcdef1234567890abcdef1234567890")

    def test_invalid_not_hex(self) -> None:
        """Address with non-hex characters should fail."""
        assert not is_valid_evm_address("0x1234567890ghijkl1234567890ghijkl12345678")


class TestDecodeResponses:
    """Tests for decoding EVM call responses."""

    def test_decode_uint256_zero(self) -> None:
        """Decode zero uint256."""
        assert decode_uint256_response("0x0") == 0

    def test_decode_uint256_small(self) -> None:
        """Decode small uint256."""
        assert decode_uint256_response("0x10") == 16

    def test_decode_uint256_large(self) -> None:
        """Decode large uint256."""
        result = decode_uint256_response(
            "0x00000000000000000000000000000000000000000000d3c21bcecceda1000000"
        )
        assert result == 1000000000000000000000000  # 1M tokens with 18 decimals

    def test_decode_uint256_empty(self) -> None:
        """Decode empty response returns 0."""
        assert decode_uint256_response("0x") == 0

    def test_decode_string_simple(self) -> None:
        """Decode simple string."""
        # "Test" encoded as EVM string response
        # Offset (32 bytes) + Length (32 bytes) + Data
        encoded = (
            "0x"
            + "0000000000000000000000000000000000000000000000000000000000000020"  # offset
            + "0000000000000000000000000000000000000000000000000000000000000004"  # length=4
            + "5465737400000000000000000000000000000000000000000000000000000000"  # "Test"
        )
        assert decode_string_response(encoded) == "Test"

    def test_decode_string_empty(self) -> None:
        """Decode empty response returns empty string."""
        assert decode_string_response("0x") == ""


class TestEvmTokenInfo:
    """Tests for EvmTokenInfo dataclass."""

    def test_repr(self) -> None:
        """Test string representation."""
        info = EvmTokenInfo(
            name="Test Token",
            symbol="TEST",
            decimals=18,
            total_supply=1000000000000000000000000,
        )
        assert "<EvmToken TEST decimals=18>" in repr(info)


class TestBaseChainClient:
    """Tests for Base chain client."""

    def test_default_endpoint(self) -> None:
        """Base client uses correct default endpoint."""
        client = BaseChainRpcClient()
        assert client._endpoint == "https://mainnet.base.org"
        assert client.CHAIN_NAME == "base"

    def test_custom_endpoint(self) -> None:
        """Base client accepts custom endpoint."""
        client = BaseChainRpcClient(endpoint="https://custom.rpc.url")
        assert client._endpoint == "https://custom.rpc.url"


class TestArbitrumClient:
    """Tests for Arbitrum chain client."""

    def test_default_endpoint(self) -> None:
        """Arbitrum client uses correct default endpoint."""
        client = ArbitrumRpcClient()
        assert client._endpoint == "https://arb1.arbitrum.io/rpc"
        assert client.CHAIN_NAME == "arbitrum"

    def test_custom_endpoint(self) -> None:
        """Arbitrum client accepts custom endpoint."""
        client = ArbitrumRpcClient(endpoint="https://custom.arb.rpc")
        assert client._endpoint == "https://custom.arb.rpc"


class TestEvmRpcClientBase:
    """Tests for base EVM RPC client behavior."""

    def test_request_interval(self) -> None:
        """Client has default request interval."""
        client = BaseChainRpcClient()
        assert client.BASE_REQUEST_INTERVAL == 0.2
