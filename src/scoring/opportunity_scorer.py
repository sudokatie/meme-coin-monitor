"""Opportunity scorer - calculates opportunity score for low-risk tokens."""

import logging
from dataclasses import dataclass
from enum import Enum

from src.analysis.base import AnalysisResult
from src.scoring.risk_scorer import RiskScore, ScoredSignal


logger = logging.getLogger(__name__)


class OpportunityCategory(str, Enum):
    """Opportunity score categories."""

    PASS = "PASS"
    WATCH = "WATCH"
    INTEREST = "INTEREST"
    STRONG = "STRONG"


@dataclass
class OpportunityScore:
    """Opportunity scoring result."""

    score: int
    category: OpportunityCategory
    signals: list[ScoredSignal]

    def __repr__(self) -> str:
        return f"<OpportunityScore {self.score} [{self.category.value}]>"


class OpportunityScorer:
    """Calculates opportunity scores for low-risk tokens."""

    RISK_THRESHOLD = 50

    def __init__(self) -> None:
        """Initialize opportunity scorer."""
        pass

    def _categorize(self, score: int) -> OpportunityCategory:
        """Categorize an opportunity score."""
        if score >= 76:
            return OpportunityCategory.STRONG
        elif score >= 51:
            return OpportunityCategory.INTEREST
        elif score >= 26:
            return OpportunityCategory.WATCH
        return OpportunityCategory.PASS

    def score(
        self,
        analyses: dict[str, AnalysisResult],
        risk_score: RiskScore,
    ) -> OpportunityScore | None:
        """
        Calculate opportunity score.

        Only calculated if risk score is below threshold.

        Args:
            analyses: Dict of analyzer name to AnalysisResult
            risk_score: Calculated risk score

        Returns:
            OpportunityScore or None if risk too high
        """
        if risk_score.score >= self.RISK_THRESHOLD:
            logger.debug(f"Risk score {risk_score.score} too high for opportunity scoring")
            return None

        scored_signals: list[ScoredSignal] = []
        raw_score = 0

        holder_analysis = analyses.get("holder")
        if holder_analysis:
            top_10_pct = holder_analysis.raw_data.get("top_10_percentage", 100)

            if hasattr(holder_analysis, "top_10_percentage"):
                top_10_pct = holder_analysis.top_10_percentage

            if top_10_pct < 30:
                contribution = 20
                raw_score += contribution
                scored_signals.append(ScoredSignal(
                    name="HEALTHY_DISTRIBUTION",
                    severity="LOW",
                    weight=20,
                    contribution=contribution,
                ))

            if hasattr(holder_analysis, "total_holders"):
                holders = holder_analysis.total_holders
                if holders >= 100:
                    contribution = 15
                    raw_score += contribution
                    scored_signals.append(ScoredSignal(
                        name="GOOD_HOLDER_COUNT",
                        severity="LOW",
                        weight=15,
                        contribution=contribution,
                    ))

        liquidity_analysis = analyses.get("liquidity")
        if liquidity_analysis:
            if hasattr(liquidity_analysis, "liquidity_ratio"):
                ratio = liquidity_analysis.liquidity_ratio
                if ratio >= 0.1:
                    contribution = 15
                    raw_score += contribution
                    scored_signals.append(ScoredSignal(
                        name="STRONG_LIQUIDITY",
                        severity="LOW",
                        weight=15,
                        contribution=contribution,
                    ))

            if hasattr(liquidity_analysis, "total_liquidity_usd"):
                liq = liquidity_analysis.total_liquidity_usd
                if liq >= 50000:
                    contribution = 10
                    raw_score += contribution
                    scored_signals.append(ScoredSignal(
                        name="DEEP_LIQUIDITY",
                        severity="LOW",
                        weight=10,
                        contribution=contribution,
                    ))

        trading_analysis = analyses.get("trading")
        if trading_analysis:
            if hasattr(trading_analysis, "buy_sell_ratio"):
                ratio = trading_analysis.buy_sell_ratio
                if 0.8 <= ratio <= 1.5:
                    contribution = 15
                    raw_score += contribution
                    scored_signals.append(ScoredSignal(
                        name="BALANCED_TRADING",
                        severity="LOW",
                        weight=15,
                        contribution=contribution,
                    ))

            if hasattr(trading_analysis, "wash_trading_score"):
                wash = trading_analysis.wash_trading_score
                if wash < 0.2:
                    contribution = 10
                    raw_score += contribution
                    scored_signals.append(ScoredSignal(
                        name="ORGANIC_VOLUME",
                        severity="LOW",
                        weight=10,
                        contribution=contribution,
                    ))

        contract_analysis = analyses.get("contract")
        if contract_analysis:
            if hasattr(contract_analysis, "mint_authority_active"):
                if not contract_analysis.mint_authority_active:
                    contribution = 10
                    raw_score += contribution
                    scored_signals.append(ScoredSignal(
                        name="MINT_REVOKED",
                        severity="LOW",
                        weight=10,
                        contribution=contribution,
                    ))

            if hasattr(contract_analysis, "freeze_authority_active"):
                if not contract_analysis.freeze_authority_active:
                    contribution = 5
                    raw_score += contribution
                    scored_signals.append(ScoredSignal(
                        name="FREEZE_REVOKED",
                        severity="LOW",
                        weight=5,
                        contribution=contribution,
                    ))

        pattern_analysis = analyses.get("pattern")
        if pattern_analysis:
            if hasattr(pattern_analysis, "deployer_flagged"):
                if not pattern_analysis.deployer_flagged:
                    contribution = 10
                    raw_score += contribution
                    scored_signals.append(ScoredSignal(
                        name="CLEAN_DEPLOYER",
                        severity="LOW",
                        weight=10,
                        contribution=contribution,
                    ))

        final_score = min(raw_score, 100)
        category = self._categorize(final_score)

        scored_signals.sort(key=lambda s: s.contribution, reverse=True)

        return OpportunityScore(
            score=final_score,
            category=category,
            signals=scored_signals,
        )
