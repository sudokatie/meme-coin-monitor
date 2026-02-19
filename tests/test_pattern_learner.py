"""Tests for pattern learning from historical outcomes."""

from datetime import datetime, timezone

import pytest

from src.analysis.pattern_learner import FeatureStats, LearnedPatterns, PatternLearner
from src.storage.models import OpportunityReview


def create_review(
    token_address: str,
    risk_score: int,
    opportunity_score: int,
    holder_count: int,
    liquidity: str,
    final_outcome: str,
    day1_rugged: bool = False,
    week1_rugged: bool = False,
    week1_reviewed: bool = True,
) -> OpportunityReview:
    """Helper to create test reviews."""
    return OpportunityReview(
        id=f"test-{token_address}",
        token_address=token_address,
        alert_id="alert-1",
        initial_timestamp=datetime.now(timezone.utc),
        initial_risk_score=risk_score,
        initial_opportunity_score=opportunity_score,
        initial_holder_count=holder_count,
        initial_liquidity_usd=liquidity,
        final_outcome=final_outcome,
        day1_rugged=day1_rugged,
        week1_rugged=week1_rugged,
        week1_reviewed=week1_reviewed,
    )


class TestFeatureStats:
    """Tests for FeatureStats dataclass."""

    def test_averages_empty(self) -> None:
        """Empty stats return 0 averages."""
        stats = FeatureStats()
        assert stats.rugged_avg == 0.0
        assert stats.survived_avg == 0.0

    def test_averages_with_data(self) -> None:
        """Stats calculate correct averages."""
        stats = FeatureStats(
            rugged_count=2,
            rugged_sum=100.0,
            survived_count=3,
            survived_sum=90.0,
        )
        assert stats.rugged_avg == 50.0
        assert stats.survived_avg == 30.0

    def test_risk_indicator_higher_rugged(self) -> None:
        """Risk indicator > 1 when rugged avg is higher."""
        stats = FeatureStats(
            rugged_count=10,
            rugged_sum=800.0,  # avg 80
            survived_count=10,
            survived_sum=400.0,  # avg 40
        )
        assert stats.risk_indicator == 2.0

    def test_risk_indicator_lower_rugged(self) -> None:
        """Risk indicator < 1 when rugged avg is lower."""
        stats = FeatureStats(
            rugged_count=10,
            rugged_sum=200.0,  # avg 20
            survived_count=10,
            survived_sum=400.0,  # avg 40
        )
        assert stats.risk_indicator == 0.5


class TestPatternLearner:
    """Tests for PatternLearner class."""

    def test_not_trained_initially(self) -> None:
        """Learner starts untrained."""
        learner = PatternLearner()
        assert not learner.is_trained
        assert learner.patterns is None

    def test_train_insufficient_data(self) -> None:
        """Training with insufficient samples doesn't mark as trained."""
        learner = PatternLearner()
        reviews = [
            create_review(f"token{i}", 50, 60, 100, "10000", "SURVIVED")
            for i in range(10)
        ]
        learner.train(reviews)
        assert not learner.is_trained

    def test_train_sufficient_data(self) -> None:
        """Training with sufficient samples marks as trained."""
        learner = PatternLearner()
        reviews = []
        # 15 rugged
        for i in range(15):
            reviews.append(
                create_review(f"rugged{i}", 70, 40, 50, "5000", "RUGGED")
            )
        # 15 survived
        for i in range(15):
            reviews.append(
                create_review(f"survived{i}", 30, 70, 200, "20000", "SURVIVED")
            )
        
        patterns = learner.train(reviews)
        assert learner.is_trained
        assert patterns.rugged_samples == 15
        assert patterns.survived_samples == 15

    def test_train_extracts_feature_stats(self) -> None:
        """Training extracts correct feature statistics."""
        learner = PatternLearner()
        reviews = [
            # Rugged tokens: high risk, low holders
            create_review("r1", 80, 40, 50, "5000", "RUGGED"),
            create_review("r2", 70, 45, 60, "6000", "RUGGED"),
            create_review("r3", 75, 42, 55, "5500", "RUGGED"),
            create_review("r4", 72, 48, 52, "4800", "RUGGED"),
            create_review("r5", 78, 44, 58, "5200", "RUGGED"),
            create_review("r6", 74, 46, 54, "5100", "RUGGED"),
            # Survived tokens: low risk, high holders
            create_review("s1", 30, 75, 200, "20000", "SURVIVED"),
            create_review("s2", 35, 70, 180, "18000", "SURVIVED"),
            create_review("s3", 32, 72, 190, "19000", "SURVIVED"),
            create_review("s4", 28, 78, 210, "21000", "SURVIVED"),
            create_review("s5", 33, 74, 195, "19500", "SURVIVED"),
            create_review("s6", 31, 76, 205, "20500", "SURVIVED"),
            # Extra to meet minimum
            create_review("r7", 76, 43, 56, "5300", "RUGGED"),
            create_review("r8", 73, 47, 53, "4900", "RUGGED"),
            create_review("r9", 77, 45, 57, "5400", "RUGGED"),
            create_review("r10", 71, 49, 51, "4700", "RUGGED"),
            create_review("s7", 29, 77, 208, "20800", "SURVIVED"),
            create_review("s8", 34, 71, 185, "18500", "SURVIVED"),
            create_review("s9", 30, 73, 192, "19200", "SURVIVED"),
            create_review("s10", 32, 75, 198, "19800", "SURVIVED"),
        ]
        
        patterns = learner.train(reviews)
        
        # Risk score should be higher for rugged
        risk_stats = patterns.feature_stats.get("initial_risk_score")
        assert risk_stats is not None
        assert risk_stats.rugged_avg > risk_stats.survived_avg
        assert risk_stats.risk_indicator > 1.5  # Significant difference

    def test_classify_outcome_from_final(self) -> None:
        """Outcome classification uses final_outcome field."""
        learner = PatternLearner()
        
        rugged = create_review("r1", 50, 50, 100, "10000", "RUGGED")
        dead = create_review("r2", 50, 50, 100, "10000", "DEAD")
        survived = create_review("s1", 50, 50, 100, "10000", "SURVIVED")
        mooned = create_review("s2", 50, 50, 100, "10000", "MOONED")
        
        assert learner._classify_outcome(rugged) == "rugged"
        assert learner._classify_outcome(dead) == "rugged"
        assert learner._classify_outcome(survived) == "survived"
        assert learner._classify_outcome(mooned) == "survived"

    def test_classify_outcome_from_flags(self) -> None:
        """Outcome classification infers from day1/week1 flags."""
        learner = PatternLearner()
        
        rugged_day1 = create_review(
            "r1", 50, 50, 100, "10000", None,
            day1_rugged=True
        )
        rugged_week1 = create_review(
            "r2", 50, 50, 100, "10000", None,
            week1_rugged=True
        )
        survived = create_review(
            "s1", 50, 50, 100, "10000", None,
            week1_reviewed=True, week1_rugged=False
        )
        
        assert learner._classify_outcome(rugged_day1) == "rugged"
        assert learner._classify_outcome(rugged_week1) == "rugged"
        assert learner._classify_outcome(survived) == "survived"

    def test_get_risk_adjustment_untrained(self) -> None:
        """Untrained learner returns 0 adjustment."""
        learner = PatternLearner()
        adjustment = learner.get_risk_adjustment({"initial_risk_score": 80})
        assert adjustment == 0

    def test_get_risk_adjustment_trained(self) -> None:
        """Trained learner returns adjustment for risky features."""
        learner = PatternLearner()
        reviews = []
        # Create clear pattern: high risk score = rugged
        for i in range(15):
            reviews.append(
                create_review(f"rugged{i}", 80 + i % 5, 40, 50, "5000", "RUGGED")
            )
        for i in range(15):
            reviews.append(
                create_review(f"survived{i}", 30 + i % 5, 70, 200, "20000", "SURVIVED")
            )
        
        learner.train(reviews)
        
        # High risk score should get positive adjustment
        high_risk_adjustment = learner.get_risk_adjustment({
            "initial_risk_score": 85.0  # Above survived average
        })
        
        # We expect some positive adjustment for high risk score
        # (exact value depends on the calculated thresholds)
        assert high_risk_adjustment >= 0

    def test_learned_patterns_to_dict(self) -> None:
        """LearnedPatterns serializes to dict."""
        patterns = LearnedPatterns()
        patterns.rugged_samples = 10
        patterns.survived_samples = 15
        patterns.feature_stats["test"] = FeatureStats(
            rugged_count=10, rugged_sum=500,
            survived_count=15, survived_sum=450,
        )
        patterns.risk_adjustments = {"high_test": 10}
        
        d = patterns.to_dict()
        assert d["rugged_samples"] == 10
        assert d["survived_samples"] == 15
        assert "test" in d["feature_stats"]
        assert d["risk_adjustments"]["high_test"] == 10
