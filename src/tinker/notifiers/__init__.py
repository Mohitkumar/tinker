"""Tinker alert notifiers.

Notifiers deliver watch alerts to messaging platforms.
Configure them in ``[notifiers.*]`` in ``~/.tinkr/config.toml``.

Example config
--------------
    [notifiers.default]
    type = "slack"
    bot_token = "env:SLACK_BOT_TOKEN"
    channel = "#incidents"

    [notifiers.ops-discord]
    type = "discord"
    webhook_url = "env:DISCORD_WEBHOOK_URL"

    [notifiers.pagerduty]
    type = "webhook"
    url = "env:PAGERDUTY_WEBHOOK_URL"
    header_Authorization = "env:PAGERDUTY_API_KEY"

Adding a new notifier type
--------------------------
1. Create ``src/tinker/notifiers/<type>.py`` — subclass ``AlertNotifier``
2. Register it in ``make_notifier()`` below
"""

from __future__ import annotations

import structlog

from tinker.notifiers.base import AlertNotifier
from tinker.notifiers.discord import DiscordNotifier
from tinker.notifiers.registry import NotifierRegistry
from tinker.notifiers.slack import SlackNotifier
from tinker.notifiers.webhook import WebhookNotifier

log = structlog.get_logger(__name__)

__all__ = [
    "AlertNotifier",
    "SlackNotifier",
    "DiscordNotifier",
    "WebhookNotifier",
    "NotifierRegistry",
    "make_notifier",
]


def make_notifier(type_key: str, options: dict[str, str]) -> AlertNotifier | None:
    """Instantiate the named notifier type from config options.

    Returns ``None`` if the type is unknown or required config is missing.
    """
    if type_key == "slack":
        token = options.get("bot_token") or options.get("token")
        if not token:
            log.warning("notifier.slack.no_token")
            return None
        channel = options.get("channel", "#incidents")
        return SlackNotifier(token=token, default_channel=channel)

    if type_key == "discord":
        url = options.get("webhook_url", "")
        if not url:
            log.warning("notifier.discord.no_webhook_url")
            return None
        return DiscordNotifier(webhook_url=url)

    if type_key == "webhook":
        url = options.get("url", "")
        if not url:
            log.warning("notifier.webhook.no_url")
            return None
        headers = {k[len("header_") :]: v for k, v in options.items() if k.startswith("header_")}
        return WebhookNotifier(url=url, headers=headers)

    log.warning("notifier.unknown_type", type=type_key)
    return None
