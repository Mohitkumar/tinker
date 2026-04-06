"""Discord alert notifier."""

from __future__ import annotations

from typing import Any

import structlog

from tinker.notifiers.base import AlertNotifier

log = structlog.get_logger(__name__)


class DiscordNotifier(AlertNotifier):
    """Sends alerts to a Discord channel via an Incoming Webhook.

    ``destination`` is ignored; the webhook URL is fixed at config time.
    """

    type_name = "discord"

    def __init__(self, webhook_url: str) -> None:
        self._url = webhook_url

    async def send_alert(
        self,
        anomalies: list[Any],
        service: str,
        destination: str | None,
        watch_id: str,
    ) -> None:
        import httpx

        lines = [f"**Tinker Watch** — `{service}`  [{watch_id}]", ""]
        for a in anomalies[:5]:
            lines.append(f"• **{a.severity.upper()}** `{a.metric}` — {a.description}")
        if len(anomalies) > 5:
            lines.append(f"*…and {len(anomalies) - 5} more*")

        payload = {"content": "\n".join(lines)}
        async with httpx.AsyncClient() as client:
            resp = await client.post(self._url, json=payload, timeout=10)
            resp.raise_for_status()
        log.info("notifier.discord.sent", watch_id=watch_id, count=len(anomalies))
