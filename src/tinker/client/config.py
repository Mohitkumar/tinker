"""Client-side configuration resolver.

Reads tinker.toml for structural config (mode, backend, server URL).
Secrets and per-backend settings still come from .env / env vars.

Mode resolution order:
  1. Explicit override passed to resolve()
  2. [tinker] mode in tinker.toml
  3. TINKER_MODE env var
  4. Auto-detect: TINKER_SERVER_URL set → server, else → local

tinker.toml schema
------------------
[tinker]
mode = "local"          # "local" | "server"

[local]
backend = "grafana"
default_model = "anthropic/claude-sonnet-4-6"
deep_rca_model = "anthropic/claude-opus-4-6"

[server]
url = "https://tinker.internal"
api_key_env = "TINKER_API_TOKEN"   # name of the env var holding the raw key
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class LocalConfig:
    backend: str = "cloudwatch"
    default_model: str = "anthropic/claude-sonnet-4-6"
    deep_rca_model: str = "anthropic/claude-opus-4-6"


@dataclass
class ServerConfig:
    url: str = ""
    api_key_env: str = "TINKER_API_TOKEN"

    @property
    def api_key(self) -> str:
        key = os.environ.get(self.api_key_env, "")
        if not key:
            raise RuntimeError(
                f"Server API token not set. Export {self.api_key_env}=<your-token>"
            )
        return key


@dataclass
class TinkerClientConfig:
    mode: str                           # "local" | "server"
    local: LocalConfig = field(default_factory=LocalConfig)
    server: ServerConfig = field(default_factory=ServerConfig)
    toml_path: Path | None = None


# ── Reader ────────────────────────────────────────────────────────────────────

def resolve(
    toml_path: Path | None = None,
    mode_override: str | None = None,
) -> TinkerClientConfig:
    """Read tinker.toml and resolve the effective client config."""
    data = _load_toml(toml_path or _find_toml())

    local_data  = data.get("local",  {})
    server_data = data.get("server", {})
    tinker_data = data.get("tinker", {})

    local = LocalConfig(
        backend=local_data.get("backend", os.environ.get("TINKER_BACKEND", "cloudwatch")),
        default_model=local_data.get(
            "default_model",
            os.environ.get("TINKER_DEFAULT_MODEL", "anthropic/claude-sonnet-4-6"),
        ),
        deep_rca_model=local_data.get(
            "deep_rca_model",
            os.environ.get("TINKER_DEEP_RCA_MODEL", "anthropic/claude-opus-4-6"),
        ),
    )

    server = ServerConfig(
        url=server_data.get("url", os.environ.get("TINKER_SERVER_URL", "")),
        api_key_env=server_data.get("api_key_env", "TINKER_API_TOKEN"),
    )

    mode = _resolve_mode(tinker_data, server, mode_override)

    return TinkerClientConfig(mode=mode, local=local, server=server, toml_path=toml_path)


def _resolve_mode(tinker_data: dict, server: ServerConfig, override: str | None) -> str:
    if override:
        return override
    if m := tinker_data.get("mode"):
        return m
    if m := os.environ.get("TINKER_MODE"):
        return m
    # Auto-detect
    if server.url:
        return "server"
    return "local"


def _find_toml() -> Path | None:
    """Walk up from cwd looking for tinker.toml."""
    here = Path.cwd()
    for parent in [here, *here.parents]:
        candidate = parent / "tinker.toml"
        if candidate.exists():
            return candidate
    return None


def _load_toml(path: Path | None) -> dict:
    if path is None or not path.exists():
        return {}
    try:
        try:
            import tomllib
        except ImportError:
            import tomli as tomllib  # type: ignore[no-reuse-def]
        return tomllib.loads(path.read_text())
    except Exception:
        return {}
