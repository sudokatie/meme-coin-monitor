"""Contract analyzer - checks mint/freeze authority and token program."""

import logging
from dataclasses import dataclass, field
from typing import Any

from src.analysis.base import AnalysisResult, BaseAnalyzer, Confidence, Severity, Signal
from src.ingestion.solana_rpc import SolanaRpcClient


logger = logging.getLogger(__name__)


@dataclass
class ContractAnalysis(AnalysisResult):
    """Contract analysis result."""

    mint_authority_active: bool = False
    freeze_authority_active: bool = False
    is_token_2022: bool = False
    has_transfer_fee: bool = False
    decimals: int = 9
    supply: int = 0


class ContractAnalyzer(BaseAnalyzer):
    """Analyzes token contract for risk signals."""

    def __init__(self, rpc_client: SolanaRpcClient) -> None:
        """
        Initialize contract analyzer.

        Args:
            rpc_client: Solana RPC client
        """
        self._rpc = rpc_client
        self._cache: dict[str, ContractAnalysis] = {}

    async def analyze(self, token_address: str, data: dict[str, Any]) -> ContractAnalysis:
        """
        Analyze token contract.

        Args:
            token_address: Token mint address
            data: Additional data (unused)

        Returns:
            ContractAnalysis with authority status and signals
        """
        if token_address in self._cache:
            logger.debug(f"Contract analysis cache hit: {token_address[:8]}...")
            return self._cache[token_address]

        signals: list[Signal] = []
        mint_authority_active = False
        freeze_authority_active = False
        is_token_2022 = False
        has_transfer_fee = False
        decimals = 9
        supply = 0

        mint_info = await self._rpc.get_mint_info(token_address)

        if mint_info:
            mint_authority_active = mint_info.mint_authority_active
            freeze_authority_active = mint_info.freeze_authority_active
            is_token_2022 = mint_info.is_token_2022
            decimals = mint_info.decimals
            supply = mint_info.supply

            if mint_authority_active:
                signals.append(Signal(
                    name="MINT_AUTHORITY_ACTIVE",
                    severity=Severity.HIGH,
                    description="Mint authority is active - unlimited tokens can be created",
                    value=mint_info.mint_authority,
                ))

            if freeze_authority_active:
                signals.append(Signal(
                    name="FREEZE_AUTHORITY_ACTIVE",
                    severity=Severity.MEDIUM,
                    description="Freeze authority is active - token transfers can be frozen",
                    value=mint_info.freeze_authority,
                ))

            if is_token_2022:
                signals.append(Signal(
                    name="TOKEN_2022_PROGRAM",
                    severity=Severity.LOW,
                    description="Uses Token-2022 program with extension support",
                ))

            confidence = Confidence.HIGH
        else:
            signals.append(Signal(
                name="CONTRACT_FETCH_FAILED",
                severity=Severity.MEDIUM,
                description="Could not fetch contract data",
            ))
            confidence = Confidence.LOW

        result = ContractAnalysis(
            signals=signals,
            confidence=confidence,
            mint_authority_active=mint_authority_active,
            freeze_authority_active=freeze_authority_active,
            is_token_2022=is_token_2022,
            has_transfer_fee=has_transfer_fee,
            decimals=decimals,
            supply=supply,
            raw_data={"mint_info": mint_info.__dict__ if mint_info else None},
        )

        self._cache[token_address] = result
        return result

    def clear_cache(self, token_address: str | None = None) -> None:
        """Clear analysis cache."""
        if token_address:
            self._cache.pop(token_address, None)
        else:
            self._cache.clear()
