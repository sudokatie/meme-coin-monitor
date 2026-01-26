"""Base classes for analysis engine."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class Severity(str, Enum):
    """Signal severity levels."""

    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class Confidence(str, Enum):
    """Analysis confidence levels."""

    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    UNKNOWN = "UNKNOWN"


@dataclass
class Signal:
    """A risk or opportunity signal."""

    name: str
    severity: Severity
    description: str
    value: Any = None

    def __repr__(self) -> str:
        return f"<Signal {self.name} [{self.severity.value}]>"


@dataclass
class AnalysisResult:
    """Base result from any analyzer."""

    signals: list[Signal] = field(default_factory=list)
    confidence: Confidence = Confidence.UNKNOWN
    raw_data: dict[str, Any] = field(default_factory=dict)

    def has_signal(self, name: str) -> bool:
        """Check if a specific signal is present."""
        return any(s.name == name for s in self.signals)

    def get_signal(self, name: str) -> Signal | None:
        """Get a signal by name."""
        for s in self.signals:
            if s.name == name:
                return s
        return None

    @property
    def max_severity(self) -> Severity | None:
        """Get the highest severity among signals."""
        if not self.signals:
            return None

        severity_order = [Severity.LOW, Severity.MEDIUM, Severity.HIGH, Severity.CRITICAL]
        max_idx = -1

        for signal in self.signals:
            idx = severity_order.index(signal.severity)
            if idx > max_idx:
                max_idx = idx

        return severity_order[max_idx] if max_idx >= 0 else None


class BaseAnalyzer(ABC):
    """Abstract base class for token analyzers."""

    @abstractmethod
    async def analyze(self, token_address: str, data: dict[str, Any]) -> AnalysisResult:
        """
        Analyze a token.

        Args:
            token_address: Token contract address
            data: Additional data from ingestion

        Returns:
            AnalysisResult with signals and confidence
        """
        pass
