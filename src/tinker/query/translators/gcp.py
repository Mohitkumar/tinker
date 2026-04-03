"""Translate a Tinker QueryNode to a GCP Cloud Logging filter string.

GCP filter syntax uses `=`, `!=`, `:` (substring), `AND`, `OR`, `NOT`.
https://cloud.google.com/logging/docs/view/logging-query-language

Examples:
    level:ERROR
      → severity="ERROR" AND resource.labels.service_name="payments-api"

    level:(ERROR OR WARN)
      → (severity="ERROR" OR severity="WARNING") AND resource.labels.service_name="..."

    "timeout" AND level:ERROR
      → textPayload:"timeout" AND severity="ERROR" AND resource.labels.service_name="..."

GCP uses "severity" not "level", and has specific severity names.
"""

from __future__ import annotations

from tinker.query.ast import AndExpr, FieldFilter, NotExpr, OrExpr, QueryNode, TextFilter

# GCP severity mapping
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
    """Return a GCP Cloud Logging filter expression (without the service clause)."""
    if isinstance(node, TextFilter):
        if node.text == "*":
            return ""
        return f'textPayload:"{node.text}"'

    if isinstance(node, FieldFilter):
        gcp_field = _gcp_field(node.field)
        # Normalise severity values
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
        if not l:
            return r
        if not r:
            return l
        return f"({l}) AND ({r})"

    if isinstance(node, OrExpr):
        l, r = translate(node.left), translate(node.right)
        return f"({l}) OR ({r})"

    if isinstance(node, NotExpr):
        inner = translate(node.operand)
        return f"NOT ({inner})"

    raise TypeError(f"Unknown node type: {type(node)}")


def to_filter(node: QueryNode, service: str) -> str:
    """Return a complete GCP Cloud Logging filter including service + time."""
    service_clause = f'resource.labels.service_name="{service}"'
    expr = translate(node)
    if not expr:
        return service_clause
    return f"{service_clause} AND ({expr})"
