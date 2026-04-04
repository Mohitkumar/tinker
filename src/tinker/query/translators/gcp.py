"""Translate a Tinker QueryNode to a GCP Cloud Logging filter string.

resource:TYPE controls the resource.type filter:
    resource:cloudrun  → resource.type="cloud_run_revision"
    resource:gke       → resource.type="k8s_container"
    resource:gce       → resource.type="gce_instance"
    resource:cloudfn   → resource.type="cloud_function"
    resource:appengine → resource.type="gae_app"
    (no resource)      → resource.labels.service_name="{service}" (Cloud Run default)
"""

from __future__ import annotations

from tinker.query.ast import AndExpr, FieldFilter, NotExpr, OrExpr, QueryNode, TextFilter
from tinker.query.resource import GCP_RESOURCE, extract_resource

_SEVERITY_MAP: dict[str, str] = {
    "debug":    "DEBUG",
    "info":     "INFO",
    "warn":     "WARNING",
    "warning":  "WARNING",
    "error":    "ERROR",
    "critical": "CRITICAL",
    "fatal":    "CRITICAL",
}

_FIELD_MAP: dict[str, str] = {
    "level":    "severity",
    "service":  "resource.labels.service_name",
    "message":  "textPayload",
    "trace_id": "trace",
    "span_id":  "spanId",
}


def _gcp_field(name: str) -> str:
    return _FIELD_MAP.get(name, name)


def _gcp_severity(v: str) -> str:
    return _SEVERITY_MAP.get(v.lower(), v.upper())


def translate(node: QueryNode) -> str:
    """Return a GCP filter expression (without service/resource clause)."""
    if isinstance(node, TextFilter):
        if node.text == "*":
            return ""
        return f'textPayload:"{node.text}"'

    if isinstance(node, FieldFilter):
        if node.field == "resource":
            return ""   # consumed by to_filter()
        gcp_field = _gcp_field(node.field)
        values = (
            [_gcp_severity(v) for v in node.values]
            if node.field == "level"
            else node.values
        )
        if len(values) == 1:
            return f'{gcp_field}="{values[0]}"'
        parts = [f'{gcp_field}="{v}"' for v in values]
        return "(" + " OR ".join(parts) + ")"

    if isinstance(node, AndExpr):
        l, r = translate(node.left), translate(node.right)
        if not l: return r
        if not r: return l
        return f"({l}) AND ({r})"

    if isinstance(node, OrExpr):
        l, r = translate(node.left), translate(node.right)
        return f"({l}) OR ({r})"

    if isinstance(node, NotExpr):
        inner = translate(node.operand)
        return f"NOT ({inner})"

    raise TypeError(f"Unknown node type: {type(node)}")


def to_filter(node: QueryNode, service: str) -> str:
    """Return a complete GCP Cloud Logging filter including resource and service."""
    resource_type, stripped = extract_resource(node)

    if resource_type and resource_type in GCP_RESOURCE:
        rtype, label_key = GCP_RESOURCE[resource_type]
        resource_clause = (
            f'resource.type="{rtype}" AND '
            f'resource.labels.{label_key}="{service}"'
        )
    else:
        # Default: Cloud Run / generic service label
        resource_clause = f'resource.labels.service_name="{service}"'
        if resource_type and resource_type not in GCP_RESOURCE:
            # Unknown type — best-effort pass-through
            resource_clause = (
                f'resource.labels.service_name="{service}" AND '
                f'resource.type="{resource_type}"'
            )

    expr = translate(stripped)
    if not expr:
        return resource_clause
    return f"{resource_clause} AND ({expr})"
