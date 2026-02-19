"""Pattern learning from historical outcomes."""

import logging
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from src.storage.models import OpportunityReview


logger = logging.getLogger(__name__)


@dataclass
class FeatureStats:
    """Statistics for a single feature across outcomes."""

    rugged_count: int = 0
    rugged_sum: float = 0.0
    survived_count: int = 0
    survived_sum: float = 0.0

    @property
    def rugged_avg(self) -> float:
        """Average value for rugged tokens."""
        return self.rugged_sum / self.rugged_count if self.rugged_count > 0 else 0.0

    @property
    def survived_avg(self) -> float:
        """Average value for survived tokens."""
        return self.survived_sum / self.survived_count if self.survived_count > 0 else 0.0

    @property
    def risk_indicator(self) -> float:
        """
        Ratio indicating risk level.
        
        > 1.0 means feature is higher for rugged tokens (risky)
        < 1.0 means feature is lower for rugged tokens (safer)
        """
        if self.survived_avg == 0:
            return 1.0
        return self.rugged_avg / self.survived_avg if self.survived_avg != 0 else 1.0


@dataclass
class LearnedPatterns:
    """Patterns learned from historical data."""

    # Feature statistics
    feature_stats: dict[str, FeatureStats] = field(default_factory=dict)
    
    # Risk adjustments per feature (positive = increase risk, negative = decrease)
    risk_adjustments: dict[str, int] = field(default_factory=dict)
    
    # Sample counts
    rugged_samples: int = 0
    survived_samples: int = 0
    
    # Model version/timestamp
    trained_at: str | None = None
    
    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "feature_stats": {
                k: {
                    "rugged_avg": v.rugged_avg,
                    "survived_avg": v.survived_avg,
                    "risk_indicator": v.risk_indicator,
                }
                for k, v in self.feature_stats.items()
            },
            "risk_adjustments": self.risk_adjustments,
            "rugged_samples": self.rugged_samples,
            "survived_samples": self.survived_samples,
            "trained_at": self.trained_at,
        }


class PatternLearner:
    """Learns patterns from historical token outcomes."""

    # Minimum samples needed before applying learned patterns
    MIN_SAMPLES = 20

    # Features to extract from reviews
    NUMERIC_FEATURES = [
        "initial_risk_score",
        "initial_opportunity_score",
        "initial_holder_count",
    ]

    def __init__(self) -> None:
        self._patterns: LearnedPatterns | None = None

    @property
    def is_trained(self) -> bool:
        """Check if model has been trained with sufficient data."""
        if self._patterns is None:
            return False
        total = self._patterns.rugged_samples + self._patterns.survived_samples
        return total >= self.MIN_SAMPLES

    @property
    def patterns(self) -> LearnedPatterns | None:
        """Get learned patterns."""
        return self._patterns

    def _extract_features(self, review: OpportunityReview) -> dict[str, float | None]:
        """Extract numeric features from a review."""
        features: dict[str, float | None] = {}
        
        # Initial scores
        features["initial_risk_score"] = (
            float(review.initial_risk_score) if review.initial_risk_score else None
        )
        features["initial_opportunity_score"] = (
            float(review.initial_opportunity_score) if review.initial_opportunity_score else None
        )
        features["initial_holder_count"] = (
            float(review.initial_holder_count) if review.initial_holder_count else None
        )
        
        # Derived features
        if review.initial_liquidity_usd:
            try:
                features["initial_liquidity"] = float(review.initial_liquidity_usd)
            except (ValueError, TypeError):
                features["initial_liquidity"] = None
        else:
            features["initial_liquidity"] = None

        if review.initial_market_cap:
            try:
                features["initial_market_cap"] = float(review.initial_market_cap)
            except (ValueError, TypeError):
                features["initial_market_cap"] = None
        else:
            features["initial_market_cap"] = None

        return features

    def _classify_outcome(self, review: OpportunityReview) -> str | None:
        """
        Classify outcome as 'rugged' or 'survived'.
        
        Returns None if outcome is ambiguous.
        """
        # Use explicit final_outcome if set
        if review.final_outcome:
            if review.final_outcome in ("RUGGED", "DEAD"):
                return "rugged"
            elif review.final_outcome in ("SURVIVED", "MOONED"):
                return "survived"
        
        # Infer from day1/week1 data
        if review.day1_rugged or review.week1_rugged:
            return "rugged"
        
        # If week1 reviewed and not rugged, consider survived
        if review.week1_reviewed and not review.week1_rugged:
            return "survived"
        
        return None

    def train(self, reviews: list[OpportunityReview]) -> LearnedPatterns:
        """
        Train pattern model from historical reviews.
        
        Args:
            reviews: List of completed opportunity reviews
            
        Returns:
            LearnedPatterns containing statistics and adjustments
        """
        from datetime import datetime, timezone
        
        patterns = LearnedPatterns()
        patterns.trained_at = datetime.now(timezone.utc).isoformat()
        
        # Initialize feature stats
        for feature in self.NUMERIC_FEATURES + ["initial_liquidity", "initial_market_cap"]:
            patterns.feature_stats[feature] = FeatureStats()
        
        # Process each review
        for review in reviews:
            outcome = self._classify_outcome(review)
            if outcome is None:
                continue
            
            features = self._extract_features(review)
            
            if outcome == "rugged":
                patterns.rugged_samples += 1
            else:
                patterns.survived_samples += 1
            
            # Accumulate feature statistics
            for feature_name, value in features.items():
                if value is None:
                    continue
                    
                stats = patterns.feature_stats.get(feature_name)
                if stats is None:
                    stats = FeatureStats()
                    patterns.feature_stats[feature_name] = stats
                
                if outcome == "rugged":
                    stats.rugged_count += 1
                    stats.rugged_sum += value
                else:
                    stats.survived_count += 1
                    stats.survived_sum += value
        
        # Calculate risk adjustments based on feature differences
        patterns.risk_adjustments = self._calculate_risk_adjustments(patterns.feature_stats)
        
        self._patterns = patterns
        logger.info(
            f"Pattern learning complete: {patterns.rugged_samples} rugged, "
            f"{patterns.survived_samples} survived samples"
        )
        
        return patterns

    def _calculate_risk_adjustments(
        self, feature_stats: dict[str, FeatureStats]
    ) -> dict[str, int]:
        """
        Calculate risk score adjustments based on feature differences.
        
        Returns dict mapping feature conditions to risk adjustments.
        """
        adjustments: dict[str, int] = {}
        
        for feature_name, stats in feature_stats.items():
            # Skip features with insufficient data
            if stats.rugged_count < 5 or stats.survived_count < 5:
                continue
            
            indicator = stats.risk_indicator
            
            # Strong indicator (>1.5x or <0.67x difference)
            if indicator > 1.5:
                # Feature is significantly higher for rugged tokens
                adjustments[f"high_{feature_name}"] = 10
            elif indicator < 0.67:
                # Feature is significantly lower for rugged tokens
                adjustments[f"low_{feature_name}"] = 10
        
        return adjustments

    def get_risk_adjustment(self, features: dict[str, float | None]) -> int:
        """
        Get risk score adjustment for a token based on learned patterns.
        
        Args:
            features: Dict of feature name to value
            
        Returns:
            Risk adjustment (positive increases risk, negative decreases)
        """
        if not self.is_trained or self._patterns is None:
            return 0
        
        adjustment = 0
        
        for feature_name, value in features.items():
            if value is None:
                continue
            
            stats = self._patterns.feature_stats.get(feature_name)
            if stats is None:
                continue
            
            # Check if value is in "risky" range
            if stats.rugged_count >= 5 and stats.survived_count >= 5:
                indicator = stats.risk_indicator
                
                if indicator > 1.5 and value > stats.survived_avg:
                    # Value is higher than survived average for a high-risk feature
                    adj_key = f"high_{feature_name}"
                    adjustment += self._patterns.risk_adjustments.get(adj_key, 0)
                elif indicator < 0.67 and value < stats.survived_avg:
                    # Value is lower than survived average for a low-risk feature
                    adj_key = f"low_{feature_name}"
                    adjustment += self._patterns.risk_adjustments.get(adj_key, 0)
        
        return adjustment
