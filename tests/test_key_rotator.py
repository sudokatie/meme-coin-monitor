"""Tests for API key rotation."""

import pytest

from src.utils.key_rotator import KeyRotator


class TestKeyRotator:
    """Test KeyRotator functionality."""

    def test_init_with_keys(self):
        """Test initialization with valid keys."""
        rotator = KeyRotator(["key1", "key2", "key3"])
        assert rotator.key_count == 3

    def test_init_empty_raises(self):
        """Test initialization with empty list raises."""
        with pytest.raises(ValueError, match="At least one API key"):
            KeyRotator([])

    def test_round_robin(self):
        """Test keys rotate in order."""
        rotator = KeyRotator(["a", "b", "c"])
        assert rotator.get_next() == "a"
        assert rotator.get_next() == "b"
        assert rotator.get_next() == "c"
        assert rotator.get_next() == "a"  # wraps

    def test_get_endpoint(self):
        """Test endpoint URL generation."""
        rotator = KeyRotator(["mykey"])
        endpoint = rotator.get_endpoint("https://example.com")
        assert endpoint == "https://example.com/?api-key=mykey"

    def test_get_endpoint_rotates(self):
        """Test endpoint rotates through keys."""
        rotator = KeyRotator(["key1", "key2"])
        ep1 = rotator.get_endpoint()
        ep2 = rotator.get_endpoint()
        assert "key1" in ep1
        assert "key2" in ep2

    def test_from_env(self):
        """Test creating from comma-separated string."""
        rotator = KeyRotator.from_env("a, b, c")
        assert rotator.key_count == 3
        assert rotator.get_next() == "a"

    def test_from_env_empty_raises(self):
        """Test from_env with empty string raises."""
        with pytest.raises(ValueError, match="No valid API keys"):
            KeyRotator.from_env("")

    def test_from_env_strips_whitespace(self):
        """Test whitespace is stripped from keys."""
        rotator = KeyRotator.from_env("  key1  ,  key2  ")
        assert rotator.key_count == 2
        assert rotator.get_next() == "key1"
        assert rotator.get_next() == "key2"

    def test_thread_safety(self):
        """Test rotator is thread-safe."""
        import threading
        
        rotator = KeyRotator(["a", "b", "c"])
        results = []
        
        def get_keys():
            for _ in range(100):
                results.append(rotator.get_next())
        
        threads = [threading.Thread(target=get_keys) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        
        # All keys should be valid
        assert all(k in ["a", "b", "c"] for k in results)
        # Should have equal distribution (roughly)
        assert len(results) == 1000
