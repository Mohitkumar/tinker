"""NotifierRegistry — maps names to AlertNotifier instances and dispatches alerts."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import structlog

from tinker.notifiers.base import AlertNotifier

if TYPE_CHECKING:
    from tinker.toml_config import NotifierConfig

log = structlog.get_logger(__name__)


class NotifierRegistry:
    """Maps notifier names to ``AlertNotifier`` instances.

    Populated at server startup from ``[notifiers.*]`` in config.toml.
    WatchManager calls ``registry.send(name, ...)`` without knowing the platform.
    """

    def __init__(self) -> None:
        self._notifiers: dict[str, AlertNotifier] = {}

    def register(self, name: str, notifier: AlertNotifier) -> None:
        self._notifiers[name] = notifier

    def get(self, name: str) -> AlertNotifier | None:
        return self._notifiers.get(name)

    def __len__(self) -> int:
        return len(self._notifiers)

    async def send(
        self,
        notifier_name: str | None,
        anomalies: list[Any],
        service: str,
        destination: str | None,
        watch_id: str,
    ) -> None:
        """Dispatch to the named notifier.

        Falls back to "default" if *notifier_name* is None.
        Falls back to the first registered notifier if there is only one.
        """
        name = notifier_name or "default"
        notifier = self._notifiers.get(name)
        if notifier is None and self._notifiers:
            if len(self._notifiers) == 1:
                notifier = next(iter(self._notifiers.values()))
            else:
                log.warning("notifier.not_found", name=name, registered=list(self._notifiers))
                return
        if notifier is None:
            log.warning("notifier.registry_empty", watch_id=watch_id)
            return
        try:
            await notifier.send_alert(anomalies, service, destination, watch_id)
        except Exception as exc:
            log.warning("notifier.send_failed", notifier=name, watch_id=watch_id, error=str(exc))

    def build_from_toml(self, notifiers_cfg: dict[str, NotifierConfig]) -> None:
        """Register all notifiers defined in config.toml."""
        from tinker.notifiers import make_notifier
        for name, cfg in notifiers_cfg.items():
            notifier = make_notifier(cfg.type, cfg.options)
            if notifier is not None:
                self.register(name, notifier)
                log.info("notifier.registered", name=name, type=cfg.type)
