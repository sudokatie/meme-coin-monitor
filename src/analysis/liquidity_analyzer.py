"""Liquidity analyzer - analyzes token liquidity pools."""

import logging
from dataclasses import dataclass
from typing import Any

from src.analysis.base import AnalysisResult, BaseAnalyzer, Confidence, Severity, Signal
from src.config import ThresholdsConfig
from src.ingestion.dex_screener import DexScreenerClient


logger = logging.getLogger(__name__)


@dataclass
class LiquidityAnalysis(AnalysisResult):
    """Liquidity analysis result."""

    total_liquidity_usd: float = 0.0
    liquidity_ratio: float = 0.0
    pool_count: int = 0
    main_dex: str | None = None
    lp_locked: bool | None = None
    lp_lock_days: int | None = None
    estimated_slippage_1k: float = 0.0
    estimated_slippage_10k: float = 0.0


def estimate_slippage(trade_size_usd: float, liquidity_usd: float) -> float:
    """
    Estimate price slippage for a trade.

    Uses simplified constant product formula approximation.

    Args:
        trade_size_usd: Size of trade in USD
        liquidity_usd: Total pool liquidity in USD

    Returns:
        Estimated slippage percentage
    """
    if liquidity_usd <= 0:
        return 100.0

    slippage = (trade_size_usd / (liquidity_usd * 2)) * 100
    return min(slippage, 100.0)


class LiquidityAnalyzer(BaseAnalyzer):
    """Analyzes token liquidity pools."""

    def __init__(
        self,
        dex_client: DexScreenerClient,
        thresholds: ThresholdsConfig | None = None,
    ) -> None:
        """
        Initialize liquidity analyzer.

        Args:
            dex_client: DEX Screener client
            thresholds: Scoring thresholds
        """
        self._dex = dex_client
        self._thresholds = thresholds or ThresholdsConfig()

    async def analyze(self, token_address: str, data: dict[str, Any]) -> LiquidityAnalysis:
        """
        Analyze token liquidity.

        Args:
            token_address: Token mint address
            data: Should contain 'market_cap' for ratio calculation

        Returns:
            LiquidityAnalysis with pool metrics and signals
        """
        signals: list[Signal] = []
        market_cap = float(data.get("market_cap", 0) or 0)

        pairs = await self._dex.get_token_pairs(token_address)

        if not pairs:
            return LiquidityAnalysis(
                signals=[Signal(
                    name="NO_LIQUIDITY_DATA",
                    severity=Severity.HIGH,
                    description="No liquidity pools found",
                )],
                confidence=Confidence.LOW,
            )

        total_liquidity = 0.0
        main_dex = None
        max_liquidity = 0.0

        for pair in pairs:
            liq = pair.get("liquidity", {})
            pair_liquidity = float(liq.get("usd", 0) or 0)
            total_liquidity += pair_liquidity

            if pair_liquidity > max_liquidity:
                max_liquidity = pair_liquidity
                main_dex = pair.get("dexId")

        pool_count = len(pairs)
        liquidity_ratio = (total_liquidity / market_cap) if market_cap > 0 else 0

        slippage_1k = estimate_slippage(1000, total_liquidity)
        slippage_10k = estimate_slippage(10000, total_liquidity)

        if total_liquidity < self._thresholds.min_liquidity_usd:
            signals.append(Signal(
                name="CRITICAL_LOW_LIQUIDITY",
                severity=Severity.CRITICAL,
                description=f"Total liquidity ${total_liquidity:,.0f} is critically low",
                value=total_liquidity,
            ))
        elif total_liquidity < self._thresholds.critical_liquidity_usd:
            signals.append(Signal(
                name="LOW_LIQUIDITY",
                severity=Severity.HIGH,
                description=f"Total liquidity ${total_liquidity:,.0f} is low",
                value=total_liquidity,
            ))

        if liquidity_ratio < 0.05 and market_cap > 0:
            signals.append(Signal(
                name="THIN_LIQUIDITY_RATIO",
                severity=Severity.MEDIUM,
                description=f"Liquidity is only {liquidity_ratio:.1%} of market cap",
                value=liquidity_ratio,
            ))

        if slippage_1k > 10:
            signals.append(Signal(
                name="HIGH_SLIPPAGE",
                severity=Severity.MEDIUM,
                description=f"Estimated {slippage_1k:.1f}% slippage on $1k trade",
                value=slippage_1k,
            ))

        if slippage_10k > 50:
            signals.append(Signal(
                name="EXTREME_SLIPPAGE",
                severity=Severity.HIGH,
                description=f"Estimated {slippage_10k:.1f}% slippage on $10k trade",
                value=slippage_10k,
            ))

        # Check for LP lock indicators in pair data
        lp_locked = None
        lp_lock_days = None

        for pair in pairs:
            # Check if liquidity is marked as locked in pair info
            pair_info = pair.get("info", {})
            if pair_info:
                # Some DEX Screener responses include lock info
                if pair_info.get("locked"):
                    lp_locked = True
                    break

        # If we couldn't determine lock status and liquidity is significant, flag it
        if lp_locked is None and total_liquidity > 10000:
            signals.append(Signal(
                name="UNLOCKED_LIQUIDITY",
                severity=Severity.HIGH,
                description="Liquidity lock status unknown - may be unlocked",
                value=None,
            ))
        elif lp_locked is False:
            signals.append(Signal(
                name="UNLOCKED_LIQUIDITY",
                severity=Severity.HIGH,
                description="Liquidity is not locked - rug pull risk",
                value=False,
            ))

        return LiquidityAnalysis(
            signals=signals,
            confidence=Confidence.HIGH if total_liquidity > 0 else Confidence.MEDIUM,
            total_liquidity_usd=total_liquidity,
            liquidity_ratio=liquidity_ratio,
            pool_count=pool_count,
            main_dex=main_dex,
            lp_locked=lp_locked,
            lp_lock_days=lp_lock_days,
            estimated_slippage_1k=slippage_1k,
            estimated_slippage_10k=slippage_10k,
            raw_data={"pairs": pairs},
        )
