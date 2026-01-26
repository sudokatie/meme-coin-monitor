"""Formatting utility functions."""

from datetime import datetime


def format_usd(amount: float | str | None) -> str:
    """
    Format amount as USD string.

    Args:
        amount: Amount to format

    Returns:
        Formatted USD string
    """
    if amount is None:
        return "$0.00"

    try:
        value = float(amount)
    except (ValueError, TypeError):
        return "$0.00"

    if value >= 1_000_000_000:
        return f"${value / 1_000_000_000:.2f}B"
    elif value >= 1_000_000:
        return f"${value / 1_000_000:.2f}M"
    elif value >= 1_000:
        return f"${value / 1_000:.2f}K"
    elif value >= 1:
        return f"${value:.2f}"
    elif value > 0:
        return f"${value:.6f}"
    else:
        return "$0.00"


def format_pct(value: float | str | None, decimals: int = 1) -> str:
    """
    Format value as percentage string.

    Args:
        value: Value to format (0-100 scale)
        decimals: Decimal places

    Returns:
        Formatted percentage string
    """
    if value is None:
        return "0%"

    try:
        num = float(value)
    except (ValueError, TypeError):
        return "0%"

    return f"{num:.{decimals}f}%"


def format_timestamp(dt: datetime | None) -> str:
    """
    Format datetime as ISO string.

    Args:
        dt: Datetime to format

    Returns:
        ISO formatted string
    """
    if dt is None:
        return ""
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def format_address(address: str, chars: int = 8) -> str:
    """
    Format address with truncation.

    Args:
        address: Full address
        chars: Characters to show at start and end

    Returns:
        Truncated address like "ABC...XYZ"
    """
    if len(address) <= chars * 2:
        return address
    return f"{address[:chars]}...{address[-chars:]}"
