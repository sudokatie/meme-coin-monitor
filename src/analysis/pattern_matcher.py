"""Pattern matcher - matches tokens against known scam patterns."""

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.analysis.base import AnalysisResult, BaseAnalyzer, Confidence, Severity, Signal
from src.storage.repositories import PatternRepository, WalletRepository


logger = logging.getLogger(__name__)

# Default patterns file location
PATTERNS_FILE = Path("data/patterns/known_scammers.json")


def similarity_score(s1: str, s2: str) -> float:
    """
    Calculate simple similarity score between two strings.

    Uses Jaccard similarity on character bigrams.

    Args:
        s1: First string
        s2: Second string

    Returns:
        Similarity score 0.0 to 1.0
    """
    if not s1 or not s2:
        return 0.0

    s1 = s1.lower().strip()
    s2 = s2.lower().strip()

    if s1 == s2:
        return 1.0

    def bigrams(s: str) -> set[str]:
        return {s[i:i+2] for i in range(len(s) - 1)} if len(s) > 1 else {s}

    b1 = bigrams(s1)
    b2 = bigrams(s2)

    intersection = len(b1 & b2)
    union = len(b1 | b2)

    return intersection / union if union > 0 else 0.0


@dataclass
class PatternAnalysis(AnalysisResult):
    """Pattern matching analysis result."""

    deployer_flagged: bool = False
    deployer_flags: list[str] | None = None
    name_similarity_matches: list[tuple[str, float]] | None = None
    behavioral_matches: list[str] | None = None
    overall_similarity_score: float = 0.0


class PatternMatcher(BaseAnalyzer):
    """Matches tokens against known scam patterns."""

    # Fallback patterns if file/database unavailable
    FALLBACK_SCAM_NAMES = [
        "SQUID", "SAFE", "ELON", "MOON", "DOGE", "INU", "PEPE", "SHIB",
        "100X", "1000X", "SAFEMOON", "BABYDOGE", "LAMBO", "GEM", "ROCKET",
    ]

    def __init__(
        self,
        wallet_repo: WalletRepository | None = None,
        pattern_repo: PatternRepository | None = None,
        patterns_file: Path | None = None,
    ) -> None:
        """
        Initialize pattern matcher.

        Args:
            wallet_repo: Wallet repository for scammer lookup
            pattern_repo: Pattern repository for known patterns
            patterns_file: Path to JSON patterns file (fallback)
        """
        self._wallet_repo = wallet_repo
        self._pattern_repo = pattern_repo
        self._patterns_file = patterns_file or PATTERNS_FILE
        self._file_data: dict[str, Any] | None = None
        self._load_file_patterns()

    def _load_file_patterns(self) -> None:
        """Load patterns from JSON file."""
        if self._patterns_file.exists():
            try:
                with open(self._patterns_file) as f:
                    self._file_data = json.load(f)
                logger.debug(f"Loaded patterns from {self._patterns_file}")
            except Exception as e:
                logger.warning(f"Failed to load patterns file: {e}")
                self._file_data = None

    def _get_scammer_wallets(self) -> dict[str, dict[str, Any]]:
        """Get known scammer wallets from file data."""
        if not self._file_data:
            return {}
        
        wallets = {}
        for w in self._file_data.get("wallets", []):
            wallets[w["address"]] = w
        return wallets

    def _get_name_patterns(self) -> list[tuple[str, str]]:
        """Get name patterns with risk level from file data."""
        patterns = []
        
        if self._file_data:
            name_patterns = self._file_data.get("name_patterns", {})
            for name in name_patterns.get("high_risk", []):
                patterns.append((name, "high"))
            for name in name_patterns.get("medium_risk", []):
                patterns.append((name, "medium"))
        
        # Add fallback patterns as medium risk
        for name in self.FALLBACK_SCAM_NAMES:
            if not any(p[0].upper() == name.upper() for p in patterns):
                patterns.append((name, "medium"))
        
        return patterns

    async def analyze(self, token_address: str, data: dict[str, Any]) -> PatternAnalysis:
        """
        Match token against known patterns.

        Args:
            token_address: Token mint address
            data: Should contain 'name', 'symbol', 'deployer'

        Returns:
            PatternAnalysis with match results and signals
        """
        signals: list[Signal] = []

        name = data.get("name", "")
        symbol = data.get("symbol", "")
        deployer = data.get("deployer", "")

        deployer_flagged = False
        deployer_flags: list[str] = []

        # Check deployer against database
        if deployer and self._wallet_repo:
            wallet = await self._wallet_repo.get_by_address(deployer)
            if wallet and wallet.risk_flags:
                deployer_flagged = True
                deployer_flags = wallet.risk_flags

        # Also check deployer against file-based wallet list (fallback)
        if deployer and not deployer_flagged:
            file_wallets = self._get_scammer_wallets()
            if deployer in file_wallets:
                deployer_flagged = True
                wallet_info = file_wallets[deployer]
                deployer_flags = wallet_info.get("risk_flags", ["scammer"])

        # Generate signals for flagged deployer
        if deployer_flagged:
            if "scammer" in deployer_flags:
                signals.append(Signal(
                    name="KNOWN_SCAMMER_DEPLOYER",
                    severity=Severity.CRITICAL,
                    description="Token deployed by known scammer wallet",
                    value=deployer,
                ))
            else:
                signals.append(Signal(
                    name="FLAGGED_DEPLOYER",
                    severity=Severity.HIGH,
                    description=f"Deployer has flags: {', '.join(deployer_flags)}",
                    value=deployer_flags,
                ))

        # Collect name patterns from all sources
        name_matches: list[tuple[str, float, str]] = []  # (name, score, risk_level)
        
        # Load patterns from database if repository available
        db_patterns: list[tuple[str, str]] = []
        if self._pattern_repo:
            try:
                patterns = await self._pattern_repo.get_by_type("NAME")
                for p in patterns:
                    if p.pattern_data and p.pattern_data.get("name"):
                        risk_level = p.pattern_data.get("risk_level", "medium")
                        db_patterns.append((p.pattern_data["name"], risk_level))
                logger.debug(f"Loaded {len(db_patterns)} name patterns from database")
            except Exception as e:
                logger.warning(f"Failed to load patterns from database: {e}")

        # Get file-based patterns
        file_patterns = self._get_name_patterns()
        
        # Combine all patterns, prefer database (more up-to-date)
        all_patterns: dict[str, str] = {}
        for pname, risk in file_patterns:
            all_patterns[pname.upper()] = risk
        for pname, risk in db_patterns:
            all_patterns[pname.upper()] = risk  # DB overrides file

        # Match against patterns
        for known_name, risk_level in all_patterns.items():
            name_sim = similarity_score(name, known_name)
            symbol_sim = similarity_score(symbol, known_name)
            max_sim = max(name_sim, symbol_sim)

            if max_sim >= 0.7:
                name_matches.append((known_name, max_sim, risk_level))

        # Generate signals for name matches
        if name_matches:
            name_matches.sort(key=lambda x: x[1], reverse=True)

            best_match = name_matches[0]
            match_name, match_score, match_risk = best_match
            
            if match_score >= 0.9:
                signals.append(Signal(
                    name="COPYCAT_NAME",
                    severity=Severity.HIGH if match_risk == "high" else Severity.MEDIUM,
                    description=f"Name closely matches known pattern: {match_name} ({match_score:.0%})",
                    value=(match_name, match_score),
                ))
            elif match_score >= 0.7:
                signals.append(Signal(
                    name="SIMILAR_NAME",
                    severity=Severity.MEDIUM if match_risk == "high" else Severity.LOW,
                    description=f"Name similar to known pattern: {match_name} ({match_score:.0%})",
                    value=(match_name, match_score),
                ))

        behavioral_matches: list[str] = []

        # Calculate overall similarity score
        overall_score = 0.0
        if name_matches:
            overall_score = max(m[1] for m in name_matches)
        if deployer_flagged:
            overall_score = max(overall_score, 0.8)

        return PatternAnalysis(
            signals=signals,
            confidence=Confidence.MEDIUM,
            deployer_flagged=deployer_flagged,
            deployer_flags=deployer_flags if deployer_flags else None,
            name_similarity_matches=[(m[0], m[1]) for m in name_matches] if name_matches else None,
            behavioral_matches=behavioral_matches if behavioral_matches else None,
            overall_similarity_score=overall_score,
            raw_data={
                "name": name,
                "symbol": symbol,
                "deployer": deployer,
            },
        )
