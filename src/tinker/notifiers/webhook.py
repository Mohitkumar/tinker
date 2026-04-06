"""Generic HTTP webhook notifier."""

from __future__ import annotations

from typing import Any

import structlog

from tinker.notifiers.base import AlertNotifier

log = structlog.get_logger(__name__)


class WebhookNotifier(AlertNotifier):
    """Posts a JSON payload to an HTTP endpoint (PagerDuty, custom receiver, etc.).

    ``destination`` overrides the configured URL if provided.

    Headers prefixed with ``header_`` in config options are sent with the request,
    e.g. ``header_Authorization = "Bearer …"``.
    """

    type_name = "webhook"

    def __init__(self, url: str, headers: dict[str, str] | None = None) -> None:
        self._url = url
        self._headers = headers or {}

    async def send_alert(
        self,
        anomalies: list[Any],
        service: str,
        destination: str | None,
        watch_id: str,
    ) -> None:
        import httpx

        url = destination or self._url
        payload: dict[str, Any] = {
            "watch_id": watch_id,
            "service": service,
            "anomaly_count": len(anomalies),
            "anomalies": [a.to_dict() for a in anomalies],
        }
        async with httpx.AsyncClient() as client:
            resp = await client.post(url, json=payload, headers=self._headers, timeout=10)
            resp.raise_for_status()
        log.info("notifier.webhook.sent", watch_id=watch_id, url=url, count=len(anomalies))
