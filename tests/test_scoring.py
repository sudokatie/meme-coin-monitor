"""Tests for scoring module."""

import pytest

from src.analysis.base import AnalysisResult, Confidence, Severity, Signal
from src.scoring.risk_scorer import RiskCategory, RiskScore, RiskScorer


class TestRiskScorer:
    """Tests for RiskScorer."""

    def test_empty_analyses_returns_low_risk(self):
        """No signals should result in low risk."""
        scorer = RiskScorer()
        result = scorer.score({})

        assert result.score == 0
        assert result.category == RiskCategory.LOW
        assert len(result.signals) == 0

    def test_single_high_signal(self):
        """Single high-severity signal should increase score."""
        scorer = RiskScorer()

        analysis = AnalysisResult(
            signals=[
                Signal(
                    name="MINT_AUTHORITY_ACTIVE",
                    severity=Severity.HIGH,
                    description="Test",
                )
            ],
            confidence=Confidence.HIGH,
        )

        result = scorer.score({"contract": analysis})

        assert result.score > 0
        assert len(result.signals) == 1
        assert result.signals[0].name == "MINT_AUTHORITY_ACTIVE"

    def test_known_scammer_instant_critical(self):
        """Known scammer signal should result in score 100."""
        scorer = RiskScorer()

        analysis = AnalysisResult(
            signals=[
                Signal(
                    name="KNOWN_SCAMMER_DEPLOYER",
                    severity=Severity.CRITICAL,
                    description="Test",
                )
            ],
            confidence=Confidence.HIGH,
        )

        result = scorer.score({"pattern": analysis})

        assert result.score == 100
        assert result.category == RiskCategory.CRITICAL

    def test_multiple_signals_accumulate(self):
        """Multiple signals should accumulate score."""
        scorer = RiskScorer()

        analysis = AnalysisResult(
            signals=[
                Signal(name="MINT_AUTHORITY_ACTIVE", severity=Severity.HIGH, description=""),
                Signal(name="FREEZE_AUTHORITY_ACTIVE", severity=Severity.MEDIUM, description=""),
                Signal(name="HIGH_CONCENTRATION", severity=Severity.HIGH, description=""),
            ],
            confidence=Confidence.HIGH,
        )

        result = scorer.score({"combined": analysis})

        assert result.score > 30
        assert len(result.signals) == 3

    def test_score_capped_at_100(self):
        """Score should not exceed 100."""
        scorer = RiskScorer()

        signals = [
            Signal(name=f"SIGNAL_{i}", severity=Severity.HIGH, description="")
            for i in range(20)
        ]

        analysis = AnalysisResult(signals=signals, confidence=Confidence.HIGH)

        result = scorer.score({"many": analysis})

        assert result.score <= 100

    def test_category_thresholds(self):
        """Categories should match threshold values."""
        scorer = RiskScorer()

        assert scorer._categorize(0) == RiskCategory.LOW
        assert scorer._categorize(25) == RiskCategory.LOW
        assert scorer._categorize(26) == RiskCategory.MEDIUM
        assert scorer._categorize(50) == RiskCategory.MEDIUM
        assert scorer._categorize(51) == RiskCategory.HIGH
        assert scorer._categorize(75) == RiskCategory.HIGH
        assert scorer._categorize(76) == RiskCategory.CRITICAL
        assert scorer._categorize(100) == RiskCategory.CRITICAL
