"""Holder analyzer - analyzes token holder distribution."""

import logging
from collections import Counter
from dataclasses import dataclass
from typing import Any

from src.analysis.base import AnalysisResult, BaseAnalyzer, Confidence, Severity, Signal
from src.config import AnalysisConfig, ThresholdsConfig
from src.ingestion.solana_rpc import HolderInfo, SolanaRpcClient
from src.storage.repositories import WalletRepository


logger = logging.getLogger(__name__)

KNOWN_DEX_POOLS = {
    "5Q544fKrFoe6tsEbD7S8EmxGTJYAKtTVhAW5Q5pge4j1",  # Raydium AMM
    "9W959DqEETiGZocYWCQPaJ6sBmUzgfxXfqGeTEdp3aQP",  # Orca Whirlpool
    "LBUZKhRxPF3XUpBCjp4YzTKgLccjZhTSDM9YuVaPwxo",  # Meteora
}

BURN_ADDRESSES = {
    "1nc1nerator11111111111111111111111111111111",
    "11111111111111111111111111111111",
}

# Wallet prefixes that indicate programmatic/bot wallets (often new wallets)
BOT_WALLET_PREFIXES = [
    "1111",  # Sequential generation pattern
    "aaaa",
    "AAAA",
]


@dataclass
class HolderAnalysis(AnalysisResult):
    """Holder analysis result."""

    total_holders: int = 0
    top_10_percentage: float = 0.0
    top_20_percentage: float = 0.0
    gini_coefficient: float = 0.0
    largest_holder_pct: float = 0.0
    known_scammer_found: bool = False
    scammer_wallets: list[str] | None = None
    new_wallet_percentage: float = 0.0  # % of holders with new/suspicious wallets
    coordinated_buy_detected: bool = False  # Multiple wallets with identical balances


def calculate_gini(balances: list[int]) -> float:
    """
    Calculate Gini coefficient for wealth distribution.

    Args:
        balances: List of holder balances

    Returns:
        Gini coefficient (0 = perfect equality, 1 = one holder has all)
    """
    if len(balances) < 2:
        return 0.0

    sorted_balances = sorted(balances)
    n = len(sorted_balances)
    total = sum(sorted_balances)

    if total == 0:
        return 0.0

    cumulative = 0
    gini_sum = 0

    for i, balance in enumerate(sorted_balances):
        cumulative += balance
        gini_sum += (2 * (i + 1) - n - 1) * balance

    return gini_sum / (n * total)


class HolderAnalyzer(BaseAnalyzer):
    """Analyzes token holder distribution."""

    def __init__(
        self,
        rpc_client: SolanaRpcClient,
        wallet_repo: WalletRepository | None = None,
        config: AnalysisConfig | None = None,
        thresholds: ThresholdsConfig | None = None,
    ) -> None:
        """
        Initialize holder analyzer.

        Args:
            rpc_client: Solana RPC client
            wallet_repo: Wallet repository for scammer lookup
            config: Analysis configuration
            thresholds: Scoring thresholds
        """
        self._rpc = rpc_client
        self._wallet_repo = wallet_repo
        self._config = config or AnalysisConfig()
        self._thresholds = thresholds or ThresholdsConfig()

    async def analyze(self, token_address: str, data: dict[str, Any]) -> HolderAnalysis:
        """
        Analyze token holder distribution.

        Args:
            token_address: Token mint address
            data: Should contain 'supply' for percentage calculations

        Returns:
            HolderAnalysis with distribution metrics and signals
        """
        signals: list[Signal] = []
        total_supply = data.get("supply", 0)

        holders = await self._rpc.get_token_holders(
            token_address,
            limit=self._config.holder_sample_limit,
        )

        if not holders:
            return HolderAnalysis(
                signals=[Signal(
                    name="NO_HOLDER_DATA",
                    severity=Severity.MEDIUM,
                    description="Could not fetch holder data",
                )],
                confidence=Confidence.LOW,
            )

        filtered_holders = [
            h for h in holders
            if h.wallet not in KNOWN_DEX_POOLS and h.wallet not in BURN_ADDRESSES
        ]

        if not filtered_holders:
            filtered_holders = holders

        total_holders = len(filtered_holders)
        balances = [h.balance for h in filtered_holders]
        total_balance = sum(balances)

        if total_supply == 0:
            total_supply = total_balance

        top_10 = balances[:10] if len(balances) >= 10 else balances
        top_20 = balances[:20] if len(balances) >= 20 else balances

        top_10_pct = (sum(top_10) / total_supply * 100) if total_supply > 0 else 0
        top_20_pct = (sum(top_20) / total_supply * 100) if total_supply > 0 else 0
        largest_pct = (balances[0] / total_supply * 100) if balances and total_supply > 0 else 0

        gini = calculate_gini(balances)

        if top_10_pct >= self._thresholds.top_holder_critical:
            signals.append(Signal(
                name="CRITICAL_CONCENTRATION",
                severity=Severity.CRITICAL,
                description=f"Top 10 holders control {top_10_pct:.1f}% of supply",
                value=top_10_pct,
            ))
        elif top_10_pct >= self._thresholds.top_holder_warning:
            signals.append(Signal(
                name="HIGH_CONCENTRATION",
                severity=Severity.HIGH,
                description=f"Top 10 holders control {top_10_pct:.1f}% of supply",
                value=top_10_pct,
            ))
        elif top_10_pct >= 30:
            signals.append(Signal(
                name="MODERATE_CONCENTRATION",
                severity=Severity.MEDIUM,
                description=f"Top 10 holders control {top_10_pct:.1f}% of supply",
                value=top_10_pct,
            ))

        if largest_pct >= 20:
            signals.append(Signal(
                name="WHALE_RISK",
                severity=Severity.MEDIUM,
                description=f"Single holder controls {largest_pct:.1f}% of supply",
                value=largest_pct,
            ))

        scammer_wallets: list[str] = []
        if self._wallet_repo:
            for holder in filtered_holders[:50]:
                wallet = await self._wallet_repo.get_by_address(holder.wallet)
                if wallet and "scammer" in wallet.risk_flags:
                    scammer_wallets.append(holder.wallet)

        if scammer_wallets:
            signals.append(Signal(
                name="KNOWN_SCAMMER_HOLDER",
                severity=Severity.CRITICAL,
                description=f"Found {len(scammer_wallets)} known scammer wallet(s) holding tokens",
                value=scammer_wallets,
            ))

        if total_holders < 10:
            signals.append(Signal(
                name="LOW_HOLDER_COUNT",
                severity=Severity.MEDIUM,
                description=f"Only {total_holders} holders",
                value=total_holders,
            ))

        # Check for coordinated buying (same block/slot purchases)
        # Detected by finding multiple wallets with identical non-trivial balances
        coordinated_buy_detected = False
        if len(balances) >= 5:
            balance_counts = Counter(balances)
            # Find balances that appear 3+ times (excluding dust amounts)
            min_meaningful_balance = total_balance * 0.001  # 0.1% of total
            suspicious_balances = [
                (bal, count) for bal, count in balance_counts.items()
                if count >= 3 and bal >= min_meaningful_balance
            ]
            if suspicious_balances:
                coordinated_buy_detected = True
                largest_cluster = max(suspicious_balances, key=lambda x: x[1])
                signals.append(Signal(
                    name="COORDINATED_BUYING",
                    severity=Severity.HIGH,
                    description=f"Found {largest_cluster[1]} wallets with identical balance ({largest_cluster[0]:,} tokens)",
                    value={"cluster_size": largest_cluster[1], "balance": largest_cluster[0]},
                ))

        # Check for new/suspicious wallets (wallet age analysis)
        # Wallets with certain patterns often indicate programmatic creation
        new_wallet_count = 0
        for holder in filtered_holders[:50]:  # Check top 50 holders
            wallet = holder.wallet
            # Check for suspicious prefixes (often bot-generated wallets)
            if any(wallet.startswith(prefix) for prefix in BOT_WALLET_PREFIXES):
                new_wallet_count += 1
            # Check for sequential-looking addresses (very short unique portion)
            elif len(set(wallet[:8])) <= 3:  # Low entropy in first 8 chars
                new_wallet_count += 1

        new_wallet_percentage = (new_wallet_count / min(len(filtered_holders), 50)) * 100
        if new_wallet_percentage >= 30:
            signals.append(Signal(
                name="HIGH_NEW_WALLET_RATIO",
                severity=Severity.MEDIUM,
                description=f"{new_wallet_percentage:.0f}% of top holders appear to be new/bot wallets",
                value=new_wallet_percentage,
            ))

        return HolderAnalysis(
            signals=signals,
            confidence=Confidence.HIGH if len(holders) >= 10 else Confidence.MEDIUM,
            total_holders=total_holders,
            top_10_percentage=top_10_pct,
            top_20_percentage=top_20_pct,
            gini_coefficient=gini,
            largest_holder_pct=largest_pct,
            known_scammer_found=len(scammer_wallets) > 0,
            scammer_wallets=scammer_wallets if scammer_wallets else None,
            new_wallet_percentage=new_wallet_percentage,
            coordinated_buy_detected=coordinated_buy_detected,
            raw_data={
                "holder_count": len(holders),
                "filtered_count": len(filtered_holders),
            },
        )
