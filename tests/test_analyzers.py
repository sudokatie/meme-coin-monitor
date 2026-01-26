"""Tests for analysis modules."""

import pytest

from src.analysis.base import Confidence, Severity, Signal
from src.analysis.pattern_matcher import PatternMatcher, similarity_score


class TestSimilarityScore:
    """Tests for string similarity scoring."""

    def test_identical_strings(self):
        """Identical strings should return 1.0."""
        assert similarity_score("PEPE", "PEPE") == 1.0

    def test_case_insensitive(self):
        """Comparison should be case insensitive."""
        assert similarity_score("pepe", "PEPE") == 1.0

    def test_similar_strings(self):
        """Similar strings should have high score."""
        score = similarity_score("SAFEMOON", "SAFEMOON2")
        assert score > 0.7

    def test_different_strings(self):
        """Different strings should have low score."""
        score = similarity_score("BITCOIN", "ETHEREUM")
        assert score < 0.3

    def test_empty_strings(self):
        """Empty strings should return 0."""
        assert similarity_score("", "test") == 0.0
        assert similarity_score("test", "") == 0.0


class TestPatternMatcher:
    """Tests for PatternMatcher."""

    @pytest.mark.asyncio
    async def test_known_scam_name_detected(self):
        """Known scam names should trigger signals."""
        matcher = PatternMatcher()

        # Use exact match to known pattern
        result = await matcher.analyze(
            "test_address",
            {"name": "SQUID", "symbol": "SQUID", "deployer": ""},
        )

        # Should match against SQUID in KNOWN_SCAM_NAMES
        assert result.has_signal("SIMILAR_NAME") or result.has_signal("COPYCAT_NAME")

    @pytest.mark.asyncio
    async def test_clean_name_no_match(self):
        """Clean names should not trigger name signals."""
        matcher = PatternMatcher()

        result = await matcher.analyze(
            "test_address",
            {"name": "Unique Token", "symbol": "UNIQ", "deployer": ""},
        )

        assert not result.has_signal("SIMILAR_NAME")
        assert not result.has_signal("COPYCAT_NAME")

    @pytest.mark.asyncio
    async def test_overall_score_with_matches(self):
        """Overall similarity score should reflect matches."""
        matcher = PatternMatcher()

        result = await matcher.analyze(
            "test_address",
            {"name": "SQUID Game Token", "symbol": "SQUID", "deployer": ""},
        )

        assert result.overall_similarity_score > 0


class TestSignal:
    """Tests for Signal class."""

    def test_signal_creation(self):
        """Signals should be created with all fields."""
        signal = Signal(
            name="TEST_SIGNAL",
            severity=Severity.HIGH,
            description="Test description",
            value=42,
        )

        assert signal.name == "TEST_SIGNAL"
        assert signal.severity == Severity.HIGH
        assert signal.description == "Test description"
        assert signal.value == 42

    def test_signal_repr(self):
        """Signal repr should be readable."""
        signal = Signal(
            name="TEST",
            severity=Severity.CRITICAL,
            description="Test",
        )

        repr_str = repr(signal)
        assert "TEST" in repr_str
        assert "CRITICAL" in repr_str
