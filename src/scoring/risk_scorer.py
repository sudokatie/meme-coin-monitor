"""Risk scorer - calculates overall risk score from analysis signals."""

import logging
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING

from src.analysis.base import AnalysisResult, Severity, Signal
from src.config import RiskWeightsConfig, ThresholdsConfig

if TYPE_CHECKING:
    from src.analysis.pattern_learner import PatternLearner


logger = logging.getLogger(__name__)


class RiskCategory(str, Enum):
    """Risk score categories."""

    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


@dataclass
class ScoredSignal:
    """A signal with its contribution to the score."""

    name: str
    severity: str
    weight: int
    contribution: int

    def __repr__(self) -> str:
        return f"<ScoredSignal {self.name} +{self.contribution}>"


@dataclass
class RiskScore:
    """Risk scoring result."""

    score: int
    category: RiskCategory
    signals: list[ScoredSignal]
    confidence: str

    def __repr__(self) -> str:
        return f"<RiskScore {self.score} [{self.category.value}]>"


SIGNAL_WEIGHT_MAP = {
    "MINT_AUTHORITY_ACTIVE": "mint_authority_active",
    "FREEZE_AUTHORITY_ACTIVE": "freeze_authority_active",
    "CRITICAL_CONCENTRATION": "high_concentration",
    "HIGH_CONCENTRATION": "high_concentration",
    "MODERATE_CONCENTRATION": "moderate_concentration",
    "UNLOCKED_LIQUIDITY": "unlocked_liquidity",
    "KNOWN_SCAMMER_DEPLOYER": "known_scammer_deployer",
    "KNOWN_SCAMMER_HOLDER": "known_scammer_holder",
    "LOW_LIQUIDITY": "low_liquidity",
    "CRITICAL_LOW_LIQUIDITY": "critical_low_liquidity",
    "WASH_TRADING_DETECTED": "wash_trading_detected",
    "SIMILAR_NAME": "similar_name",
    "COPYCAT_NAME": "copycat_name",
    "HIGH_SLIPPAGE": "high_slippage",
    "HEAVY_SELLING": "heavy_selling",
    "COORDINATED_BUYING": "coordinated_buying",
    "HIGH_NEW_WALLET_RATIO": "high_new_wallet_ratio",
}

INSTANT_CRITICAL_SIGNALS = {
    "KNOWN_SCAMMER_DEPLOYER",
    "KNOWN_SCAMMER_HOLDER",
}


class RiskScorer:
    """Calculates risk scores from analysis results."""

    def __init__(
        self,
        weights: RiskWeightsConfig | None = None,
        thresholds: ThresholdsConfig | None = None,
        pattern_learner: "PatternLearner | None" = None,
    ) -> None:
        """
        Initialize risk scorer.

        Args:
            weights: Risk signal weights
            thresholds: Score thresholds
            pattern_learner: Optional trained pattern learner for historical adjustments
        """
        self._weights = weights or RiskWeightsConfig()
        self._thresholds = thresholds or ThresholdsConfig()
        self._pattern_learner = pattern_learner

    def _get_weight(self, signal_name: str) -> int:
        """Get weight for a signal."""
        weight_key = SIGNAL_WEIGHT_MAP.get(signal_name)
        if weight_key:
            return getattr(self._weights, weight_key, 10)
        return 10

    def _severity_multiplier(self, severity: Severity) -> float:
        """Get multiplier based on severity."""
        multipliers = {
            Severity.LOW: 0.5,
            Severity.MEDIUM: 0.75,
            Severity.HIGH: 1.0,
            Severity.CRITICAL: 1.5,
        }
        return multipliers.get(severity, 1.0)

    def _categorize(self, score: int) -> RiskCategory:
        """Categorize a risk score."""
        if score >= self._thresholds.critical_risk:
            return RiskCategory.CRITICAL
        elif score >= self._thresholds.high_risk:
            return RiskCategory.HIGH
        elif score >= 26:
            return RiskCategory.MEDIUM
        return RiskCategory.LOW

    def score(
        self,
        analyses: dict[str, AnalysisResult],
        token_features: dict[str, float | None] | None = None,
    ) -> RiskScore:
        """
        Calculate risk score from analysis results.

        Args:
            analyses: Dict of analyzer name to AnalysisResult
            token_features: Optional features for pattern learning adjustment

        Returns:
            RiskScore with total, category, and signal breakdown
        """
        scored_signals: list[ScoredSignal] = []
        raw_score = 0
        has_instant_critical = False

        all_signals: list[Signal] = []
        confidence_levels: list[str] = []

        for name, result in analyses.items():
            all_signals.extend(result.signals)
            confidence_levels.append(result.confidence.value)

        for signal in all_signals:
            if signal.name in INSTANT_CRITICAL_SIGNALS:
                has_instant_critical = True

            weight = self._get_weight(signal.name)
            multiplier = self._severity_multiplier(signal.severity)
            contribution = int(weight * multiplier)

            raw_score += contribution

            scored_signals.append(ScoredSignal(
                name=signal.name,
                severity=signal.severity.value,
                weight=weight,
                contribution=contribution,
            ))

        # Apply learned pattern adjustment if available
        pattern_adjustment = 0
        if (
            self._pattern_learner is not None
            and self._pattern_learner.is_trained
            and token_features is not None
        ):
            pattern_adjustment = self._pattern_learner.get_risk_adjustment(token_features)
            if pattern_adjustment != 0:
                raw_score += pattern_adjustment
                scored_signals.append(ScoredSignal(
                    name="LEARNED_PATTERN_ADJUSTMENT",
                    severity="MEDIUM",
                    weight=abs(pattern_adjustment),
                    contribution=pattern_adjustment,
                ))
                logger.debug(f"Applied pattern learning adjustment: {pattern_adjustment}")

        if has_instant_critical:
            final_score = 100
        else:
            final_score = min(max(raw_score, 0), 100)  # Clamp to 0-100

        category = self._categorize(final_score)

        if "HIGH" in confidence_levels or "MEDIUM" in confidence_levels:
            confidence = "HIGH" if confidence_levels.count("HIGH") > confidence_levels.count("LOW") else "MEDIUM"
        else:
            confidence = "LOW"

        scored_signals.sort(key=lambda s: s.contribution, reverse=True)

        return RiskScore(
            score=final_score,
            category=category,
            signals=scored_signals,
            confidence=confidence,
        )
