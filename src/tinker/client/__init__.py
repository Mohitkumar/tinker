"""Tinker client — always talks to a Tinker server over HTTP.

Usage:
    from tinker.client import get_client

    client = get_client()                          # reads ~/.tinkr/config
    client = get_client("http://localhost:8000")   # explicit URL override
"""

from tinker.client.remote import RemoteClient
from tinker.client.config import resolve


def get_client(url_override: str | None = None) -> RemoteClient:
    """Return a RemoteClient configured from environment / ~/.tinkr/config."""
    cfg = resolve(url_override=url_override)
    return RemoteClient(cfg)

__all__ = ["RemoteClient", "get_client"]
