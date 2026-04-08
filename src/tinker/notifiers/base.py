"""AlertNotifier abstract base class."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class AlertNotifier(ABC):
    """Send an alert for a set of anomalies to a destination."""

    @property
    @abstractmethod
    def type_name(self) -> str:
        """Short type identifier, e.g. 'slack', 'discord', 'webhook'."""

    @abstractmethod
    async def send_alert(
        self,
        anomalies: list[Any],  # list[Anomaly] — avoid circular import
        service: str,
        destination: str | None,
        watch_id: str,
    ) -> None:
        """Send anomaly alert.

        Parameters
        ----------
        anomalies:   non-empty list of Anomaly objects
        service:     service name, for display
        destination: platform-specific target (Slack channel, webhook URL …).
                     None means use the notifier's own configured default.
        watch_id:    watch identifier, for correlation
        """
