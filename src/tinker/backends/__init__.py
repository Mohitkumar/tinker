"""Observability backend registry.

Backend selection
-----------------
The active backend is determined by the active profile in ~/.tinkr/config.toml:

    active_profile = "aws-prod"

    [profiles.aws-prod]
    backend = "cloudwatch"
    region  = "us-east-1"

All services in a profile share the profile's backend.
Use get_backend_for_service(service) in route handlers.
"""

from __future__ import annotations

import importlib
import structlog

from tinker.backends.base import ObservabilityBackend

log = structlog.get_logger(__name__)

# Lazy registry — values are import paths to avoid loading all SDKs at startup.
_REGISTRY: dict[str, str] = {
    "cloudwatch": "tinker.backends.cloudwatch:CloudWatchBackend",
    "gcp": "tinker.backends.gcp:GCPBackend",
    "azure": "tinker.backends.azure:AzureBackend",
    "grafana": "tinker.backends.grafana:GrafanaBackend",
    "datadog": "tinker.backends.datadog:DatadogBackend",
    "elastic": "tinker.backends.elastic:ElasticBackend",
    "elasticsearch": "tinker.backends.elastic:ElasticBackend",
    "opensearch": "tinker.backends.elastic:ElasticBackend",
    "otel": "tinker.backends.otel:OTelBackend",
}

# Cache of named backend instances (keyed by TOML backend name or type string)
_instances: dict[str, ObservabilityBackend] = {}


def _make_backend(type_key: str, config: dict | None = None) -> ObservabilityBackend:
    """Instantiate a backend by type key, passing optional TOML config dict."""
    key = type_key.lower()
    if key not in _REGISTRY:
        available = ", ".join(k for k in _REGISTRY if k not in ("elasticsearch", "opensearch"))
        raise ValueError(f"Unknown backend type '{key}'. Available: {available}")

    module_path, cls_name = _REGISTRY[key].split(":")
    module = importlib.import_module(module_path)
    cls = getattr(module, cls_name)
    return cls(config=config) if config is not None else cls()


def get_backend() -> ObservabilityBackend:
    """Return the backend for the active profile."""
    from tinker import toml_config as tc

    cfg = tc.get()
    profile = cfg.active_profile_config()
    if not profile:
        raise RuntimeError(
            "No active profile configured. "
            "Run 'tinker init server' or add a profile with 'tinker profile add'."
        )
    cache_key = f"profile:{cfg.active_profile or next(iter(cfg.profiles))}"
    if cache_key not in _instances:
        log.info("backend.init", profile=cfg.active_profile, type=profile.backend)
        _instances[cache_key] = _make_backend(profile.backend, profile.options)
    return _instances[cache_key]


def get_backend_for_service(_service: str) -> ObservabilityBackend:
    """Return the backend for the given service (uses the active profile's backend)."""
    return get_backend()


def available_backends() -> list[str]:
    return sorted(set(_REGISTRY.keys()) - {"elasticsearch", "opensearch"})


def clear_cache() -> None:
    """Discard all cached backend instances (useful in tests)."""
    _instances.clear()


__all__ = [
    "ObservabilityBackend",
    "get_backend",
    "get_backend_for_service",
    "available_backends",
    "clear_cache",
]
