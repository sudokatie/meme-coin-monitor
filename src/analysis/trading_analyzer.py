"""Trading analyzer - analyzes trading patterns."""

import logging
from dataclasses import dataclass
from typing import Any

from src.analysis.base import AnalysisResult, BaseAnalyzer, Confidence, Severity, Signal
from src.ingestion.dex_screener import DexScreenerClient


logger = logging.getLogger(__name__)


@dataclass
class TradingAnalysis(AnalysisResult):
    """Trading analysis result."""

    volume_24h: float = 0.0
    volume_market_cap_ratio: float = 0.0
    buy_count: int = 0
    sell_count: int = 0
    unique_buyers: int = 0
    unique_sellers: int = 0
    buy_sell_ratio: float = 0.0
    wash_trading_score: float = 0.0
    pump_detected: bool = False


class TradingAnalyzer(BaseAnalyzer):
    """Analyzes trading patterns for suspicious activity."""

    def __init__(self, dex_client: DexScreenerClient) -> None:
        """
        Initialize trading analyzer.

        Args:
            dex_client: DEX Screener client
        """
        self._dex = dex_client

    async def analyze(self, token_address: str, data: dict[str, Any]) -> TradingAnalysis:
        """
        Analyze trading patterns.

        Args:
            token_address: Token mint address
            data: Should contain market_cap, volume_24h from ingestion

        Returns:
            TradingAnalysis with volume metrics and signals
        """
        signals: list[Signal] = []

        volume_24h = float(data.get("volume_24h", 0) or 0)
        market_cap = float(data.get("market_cap", 0) or 0)

        volume_ratio = (volume_24h / market_cap) if market_cap > 0 else 0

        pairs = await self._dex.get_token_pairs(token_address)

        buy_count = 0
        sell_count = 0
        price_change_5m = 0.0
        price_change_1h = 0.0

        unique_buyers = 0
        unique_sellers = 0

        if pairs:
            main_pair = pairs[0]
            txns = main_pair.get("txns", {})

            h24 = txns.get("h24", {})
            buy_count = h24.get("buys", 0)
            sell_count = h24.get("sells", 0)

            # DEX Screener provides maker counts in some responses
            makers = main_pair.get("makers", {})
            if makers:
                h24_makers = makers.get("h24", {})
                unique_buyers = h24_makers.get("buys", 0)
                unique_sellers = h24_makers.get("sells", 0)

            price_change = main_pair.get("priceChange", {})
            price_change_5m = float(price_change.get("m5", 0) or 0)
            price_change_1h = float(price_change.get("h1", 0) or 0)

        total_txns = buy_count + sell_count
        buy_sell_ratio = (buy_count / sell_count) if sell_count > 0 else float("inf")

        wash_trading_score = 0.0

        # Wash trading indicators
        # 1. High volume with few transactions
        if volume_ratio > 10 and total_txns < 100:
            wash_trading_score += 0.3
            signals.append(Signal(
                name="SUSPICIOUS_VOLUME",
                severity=Severity.MEDIUM,
                description=f"High volume ({volume_ratio:.1f}x market cap) with few transactions",
                value=volume_ratio,
            ))

        # 2. Very few unique traders relative to transaction count
        if unique_buyers > 0 and unique_sellers > 0:
            avg_txns_per_trader = total_txns / max(unique_buyers + unique_sellers, 1)
            if avg_txns_per_trader > 20:
                wash_trading_score += 0.25
                signals.append(Signal(
                    name="LOW_UNIQUE_TRADERS",
                    severity=Severity.MEDIUM,
                    description=f"Average {avg_txns_per_trader:.1f} txns per unique trader",
                    value=avg_txns_per_trader,
                ))

        # 3. Suspiciously balanced buy/sell (could indicate wash)
        if buy_count > 50 and sell_count > 50:
            if 0.95 <= buy_sell_ratio <= 1.05:
                wash_trading_score += 0.2

        if volume_ratio > 5:
            signals.append(Signal(
                name="UNUSUAL_VOLUME",
                severity=Severity.MEDIUM,
                description=f"24h volume is {volume_ratio:.1f}x market cap",
                value=volume_ratio,
            ))

        if buy_sell_ratio < 0.2 and sell_count > 10:
            signals.append(Signal(
                name="HEAVY_SELLING",
                severity=Severity.HIGH,
                description=f"Buy/sell ratio is {buy_sell_ratio:.2f} (heavy selling)",
                value=buy_sell_ratio,
            ))

        pump_detected = False
        if price_change_1h > 100:
            pump_detected = True
            signals.append(Signal(
                name="PUMP_PATTERN",
                severity=Severity.MEDIUM,
                description=f"Price increased {price_change_1h:.0f}% in last hour",
                value=price_change_1h,
            ))

        if price_change_5m < -20:
            signals.append(Signal(
                name="RAPID_DUMP",
                severity=Severity.HIGH,
                description=f"Price dropped {abs(price_change_5m):.0f}% in last 5 minutes",
                value=price_change_5m,
            ))

        if wash_trading_score > 0.7:
            signals.append(Signal(
                name="WASH_TRADING_DETECTED",
                severity=Severity.HIGH,
                description="Trading patterns suggest wash trading",
                value=wash_trading_score,
            ))

        if volume_24h == 0 and market_cap > 0:
            signals.append(Signal(
                name="NO_TRADING_ACTIVITY",
                severity=Severity.MEDIUM,
                description="No trading activity in last 24 hours",
            ))

        return TradingAnalysis(
            signals=signals,
            confidence=Confidence.MEDIUM,
            volume_24h=volume_24h,
            volume_market_cap_ratio=volume_ratio,
            buy_count=buy_count,
            sell_count=sell_count,
            unique_buyers=unique_buyers,
            unique_sellers=unique_sellers,
            buy_sell_ratio=buy_sell_ratio if buy_sell_ratio != float("inf") else 999,
            wash_trading_score=wash_trading_score,
            pump_detected=pump_detected,
            raw_data={
                "price_change_5m": price_change_5m,
                "price_change_1h": price_change_1h,
            },
        )
