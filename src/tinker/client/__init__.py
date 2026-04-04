"""Tinker client factory.

Usage:
    from tinker.client import get_client

    client = get_client()           # auto-detects from tinker.toml / env
    client = get_client("local")    # force local mode
    client = get_client("server")   # force server mode
"""

from __future__ import annotations

from pathlib import Path

from tinker.client.base import TinkerClient
from tinker.client.config import TinkerClientConfig, resolve


def get_client(
    mode_override: str | None = None,
    toml_path: Path | None = None,
) -> TinkerClient:
    """Return the appropriate client for the resolved mode.

    Raises RuntimeError if server mode is requested but no URL is configured.
    """
    cfg = resolve(toml_path=toml_path, mode_override=mode_override)

    if cfg.mode == "server":
        return _make_server_client(cfg)
    return _make_local_client(cfg)


def _make_local_client(cfg: TinkerClientConfig) -> TinkerClient:
    from tinker.client.local import LocalClient
    return LocalClient(cfg.local)


def _make_server_client(cfg: TinkerClientConfig) -> TinkerClient:
    from tinker.client.remote import RemoteClient

    if not cfg.server.url:
        raise RuntimeError(
            "Server mode requires a server URL.\n"
            "Set [server] url in tinker.toml or TINKER_SERVER_URL env var.\n\n"
            "To deploy a server:  tinker deploy\n"
            "To switch to local:  tinker --mode local <command>"
        )

    return RemoteClient(cfg.server)


__all__ = ["TinkerClient", "get_client"]
