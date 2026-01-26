"""Alert manager - handles alert generation and delivery."""

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from src.config import AlertsConfig
from src.scoring.risk_scorer import RiskCategory, RiskScore
from src.scoring.opportunity_scorer import OpportunityCategory, OpportunityScore
from src.storage.models import Alert
from src.storage.repositories import AlertRepository


logger = logging.getLogger(__name__)


class AlertChannel(ABC):
    """Abstract base for alert delivery channels."""

    @abstractmethod
    async def deliver(self, alert: Alert) -> bool:
        """
        Deliver an alert.

        Args:
            alert: Alert to deliver

        Returns:
            True if delivery succeeded
        """
        pass


@dataclass
class AlertDecision:
    """Decision about whether to send an alert."""

    should_alert: bool
    alert_type: str
    severity: str
    message: str
    data: dict[str, Any]


class AlertManager:
    """Manages alert generation and delivery."""

    def __init__(
        self,
        config: AlertsConfig,
        alert_repo: AlertRepository | None = None,
    ) -> None:
        """
        Initialize alert manager.

        Args:
            config: Alert configuration
            alert_repo: Alert repository for persistence
        """
        self._config = config
        self._alert_repo = alert_repo
        self._channels: list[AlertChannel] = []
        self._throttle_state: dict[str, datetime] = {}
        self._global_alert_times: list[datetime] = []

    def add_channel(self, channel: AlertChannel) -> None:
        """Add a delivery channel."""
        self._channels.append(channel)

    def _is_throttled(self, token_address: str, alert_type: str) -> bool:
        """Check if an alert should be throttled."""
        key = f"{token_address}:{alert_type}"
        last_alert = self._throttle_state.get(key)

        if last_alert:
            throttle_window = timedelta(minutes=self._config.throttle_per_token_minutes)
            if datetime.now(timezone.utc) - last_alert < throttle_window:
                return True

        now = datetime.now(timezone.utc)
        window_start = now - timedelta(hours=1)
        self._global_alert_times = [t for t in self._global_alert_times if t > window_start]

        if len(self._global_alert_times) >= self._config.throttle_global_per_hour:
            return True

        return False

    def _record_alert(self, token_address: str, alert_type: str) -> None:
        """Record that an alert was sent."""
        key = f"{token_address}:{alert_type}"
        now = datetime.now(timezone.utc)
        self._throttle_state[key] = now
        self._global_alert_times.append(now)

    def decide(
        self,
        token_address: str,
        token_name: str,
        token_symbol: str,
        risk_score: RiskScore,
        opportunity_score: OpportunityScore | None = None,
    ) -> AlertDecision:
        """
        Decide whether to generate an alert.

        Args:
            token_address: Token address
            token_name: Token name
            token_symbol: Token symbol
            risk_score: Calculated risk score
            opportunity_score: Optional opportunity score

        Returns:
            AlertDecision with alert details
        """
        should_alert = False
        alert_type = ""
        severity = ""
        message = ""
        data: dict[str, Any] = {
            "token_address": token_address,
            "token_name": token_name,
            "token_symbol": token_symbol,
            "risk_score": risk_score.score,
            "risk_category": risk_score.category.value,
            "signals": [
                {"name": s.name, "contribution": s.contribution}
                for s in risk_score.signals[:5]
            ],
        }

        is_critical_scammer = any(
            s.name in ("KNOWN_SCAMMER_DEPLOYER", "KNOWN_SCAMMER_HOLDER")
            for s in risk_score.signals
        )

        if is_critical_scammer:
            should_alert = True
            alert_type = "PATTERN_MATCH"
            severity = "CRITICAL"
            signal_names = [s.name for s in risk_score.signals if "SCAMMER" in s.name]
            message = f"CRITICAL: {token_symbol} deployed/held by known scammer"
            data["bypass_throttle"] = True

        elif risk_score.category == RiskCategory.CRITICAL:
            should_alert = True
            alert_type = "RUG_WARNING"
            severity = "CRITICAL"
            top_signals = [s.name for s in risk_score.signals[:3]]
            message = f"CRITICAL risk for {token_symbol}: {', '.join(top_signals)}"

        elif risk_score.category == RiskCategory.HIGH:
            should_alert = True
            alert_type = "RUG_WARNING"
            severity = "HIGH"
            top_signals = [s.name for s in risk_score.signals[:3]]
            message = f"High risk for {token_symbol}: {', '.join(top_signals)}"

        elif opportunity_score and opportunity_score.category == OpportunityCategory.STRONG:
            should_alert = True
            alert_type = "OPPORTUNITY"
            severity = "HIGH"
            message = f"Strong opportunity: {token_symbol} (risk: {risk_score.score})"
            data["opportunity_score"] = opportunity_score.score

        return AlertDecision(
            should_alert=should_alert,
            alert_type=alert_type,
            severity=severity,
            message=message,
            data=data,
        )

    async def process(
        self,
        token_address: str,
        token_name: str,
        token_symbol: str,
        risk_score: RiskScore,
        opportunity_score: OpportunityScore | None = None,
    ) -> Alert | None:
        """
        Process scores and potentially generate/deliver an alert.

        Args:
            token_address: Token address
            token_name: Token name
            token_symbol: Token symbol
            risk_score: Calculated risk score
            opportunity_score: Optional opportunity score

        Returns:
            Alert if one was generated, None otherwise
        """
        if not self._config.enabled:
            return None

        decision = self.decide(
            token_address,
            token_name,
            token_symbol,
            risk_score,
            opportunity_score,
        )

        if not decision.should_alert:
            return None

        bypass_throttle = decision.data.get("bypass_throttle", False)
        if not bypass_throttle and self._is_throttled(token_address, decision.alert_type):
            logger.debug(f"Alert throttled for {token_address}")
            return None

        alert = Alert(
            token_address=token_address,
            alert_type=decision.alert_type,
            severity=decision.severity,
            message=decision.message,
            data=decision.data,
            created_at=datetime.now(timezone.utc),
        )

        # Note: Alert persistence is handled by the caller who has the database session
        # The alert_repo should be used within a proper session context
        # For now, we track alerts in memory for throttling

        for channel in self._channels:
            try:
                success = await channel.deliver(alert)
                if success:
                    logger.info(f"Alert delivered: {decision.alert_type} for {token_symbol}")
                else:
                    logger.warning(f"Alert delivery failed for {token_symbol}")
            except Exception as e:
                logger.error(f"Alert channel error: {e}")

        self._record_alert(token_address, decision.alert_type)

        return alert

    async def process_graduation(
        self,
        token_address: str,
        token_name: str,
        token_symbol: str,
        market_cap: float | None = None,
        dex: str | None = None,
    ) -> Alert | None:
        """
        Process a pump.fun graduation event.

        Graduation occurs when a token reaches ~$90k market cap and
        moves from pump.fun bonding curve to Raydium DEX.

        Args:
            token_address: Token address
            token_name: Token name
            token_symbol: Token symbol
            market_cap: Market cap at graduation
            dex: DEX the token graduated to (e.g., "raydium")

        Returns:
            Alert if one was generated, None otherwise
        """
        if not self._config.enabled:
            return None

        if self._is_throttled(token_address, "GRADUATION"):
            logger.debug(f"Graduation alert throttled for {token_address}")
            return None

        data: dict[str, Any] = {
            "token_address": token_address,
            "token_name": token_name,
            "token_symbol": token_symbol,
            "event": "graduation",
        }

        if market_cap:
            data["market_cap"] = market_cap
        if dex:
            data["graduated_to"] = dex

        message = f"GRADUATION: {token_symbol} graduated from pump.fun"
        if dex:
            message += f" to {dex.title()}"
        if market_cap:
            message += f" (mcap: ${market_cap:,.0f})"

        alert = Alert(
            token_address=token_address,
            alert_type="GRADUATION",
            severity="MEDIUM",
            message=message,
            data=data,
            created_at=datetime.now(timezone.utc),
        )

        for channel in self._channels:
            try:
                success = await channel.deliver(alert)
                if success:
                    logger.info(f"Graduation alert delivered for {token_symbol}")
            except Exception as e:
                logger.error(f"Graduation alert channel error: {e}")

        self._record_alert(token_address, "GRADUATION")

        return alert
