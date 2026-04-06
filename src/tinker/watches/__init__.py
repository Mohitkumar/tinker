"""Tinker background watch management.

A watch is a recurring anomaly-detection task that dispatches alerts
via a configured notifier when the anomaly set changes.

Usage
-----
    from tinker.watches import WatchManager
    from tinker.notifiers import NotifierRegistry

    registry = NotifierRegistry()
    registry.build_from_toml(cfg.get_notifiers())

    manager = WatchManager(registry=registry)
    await manager.start()   # resumes persisted watches
    ...
    await manager.stop()    # cancels all tasks on shutdown
"""

from tinker.watches.manager import WatchManager

__all__ = ["WatchManager"]
