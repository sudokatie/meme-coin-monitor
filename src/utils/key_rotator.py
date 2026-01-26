"""API key rotation for rate limit distribution."""

import logging
import threading
from typing import List


logger = logging.getLogger(__name__)


class KeyRotator:
    """
    Thread-safe round-robin API key rotator.
    
    Distributes requests across multiple API keys to maximize
    effective rate limits.
    """

    def __init__(self, keys: List[str]) -> None:
        """
        Initialize the key rotator.

        Args:
            keys: List of API keys to rotate through.
                  Must have at least one key.

        Raises:
            ValueError: If no keys provided.
        """
        if not keys:
            raise ValueError("At least one API key is required")
        
        self._keys = keys
        self._index = 0
        self._lock = threading.Lock()
        
        logger.info(f"Key rotator initialized with {len(keys)} key(s)")

    def get_next(self) -> str:
        """
        Get the next API key in rotation.

        Returns:
            The next API key.
        """
        with self._lock:
            key = self._keys[self._index]
            self._index = (self._index + 1) % len(self._keys)
            return key

    def get_endpoint(self, base_url: str = "https://mainnet.helius-rpc.com") -> str:
        """
        Get the next endpoint URL with API key.

        Args:
            base_url: Base Helius RPC URL.

        Returns:
            Full endpoint URL with API key parameter.
        """
        key = self.get_next()
        return f"{base_url}/?api-key={key}"

    @property
    def key_count(self) -> int:
        """Number of keys in rotation."""
        return len(self._keys)

    @classmethod
    def from_env(cls, env_value: str) -> "KeyRotator":
        """
        Create a KeyRotator from an environment variable value.

        Args:
            env_value: Comma-separated list of API keys.

        Returns:
            KeyRotator instance.

        Raises:
            ValueError: If env_value is empty or has no valid keys.
        """
        keys = [k.strip() for k in env_value.split(",") if k.strip()]
        if not keys:
            raise ValueError("No valid API keys found in environment variable")
        return cls(keys)
