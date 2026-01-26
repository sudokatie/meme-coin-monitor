"""Solana utility functions."""

import base58


def is_valid_address(address: str) -> bool:
    """
    Validate a Solana base58 address.

    Args:
        address: Address to validate

    Returns:
        True if valid Solana address
    """
    try:
        decoded = base58.b58decode(address)
        return len(decoded) == 32
    except Exception:
        return False


def lamports_to_sol(lamports: int) -> float:
    """
    Convert lamports to SOL.

    Args:
        lamports: Amount in lamports

    Returns:
        Amount in SOL
    """
    return lamports / 1_000_000_000


def sol_to_lamports(sol: float) -> int:
    """
    Convert SOL to lamports.

    Args:
        sol: Amount in SOL

    Returns:
        Amount in lamports
    """
    return int(sol * 1_000_000_000)


def token_amount_to_ui(amount: int, decimals: int) -> float:
    """
    Convert raw token amount to UI amount.

    Args:
        amount: Raw token amount
        decimals: Token decimals

    Returns:
        UI-formatted amount
    """
    return amount / (10 ** decimals)
