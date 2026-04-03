"""Translate a Tinker QueryNode to a CloudWatch Logs Insights query string.

CloudWatch Logs Insights syntax:
    fields @timestamp, @message, level
    | filter level = 'ERROR'
    | filter @message like /timeout/

We produce only the filter clause(s) — the caller prepends
`fields @timestamp, @message, level, service | ` if needed.
"""

from __future__ import annotations

import re

from tinker.query.ast import AndExpr, FieldFilter, NotExpr, OrExpr, QueryNode, TextFilter

# Map canonical Tinker field names → CloudWatch field names
_FIELD_MAP: dict[str, str] = {
    "level": "level",
    "service": "service",
    "message": "@message",
    "trace_id": "traceId",
    "span_id": "spanId",
}


def _cw_field(name: str) -> str:
    return _FIELD_MAP.get(name, name)


def translate(node: QueryNode) -> str:
    """Return a CloudWatch Logs Insights filter expression (no leading `| filter`)."""
    if isinstance(node, TextFilter):
        if node.text == "*":
            return "1 = 1"
        escaped = node.text.replace("/", "\\/")
        if node.exact:
            return f'@message like /{re.escape(node.text)}/'
        return f"@message like /{escaped}/"

    if isinstance(node, FieldFilter):
        field = _cw_field(node.field)
        if len(node.values) == 1:
            return f"{field} = '{node.values[0]}'"
        vals = ", ".join(f"'{v}'" for v in node.values)
        return f"{field} in [{vals}]"

    if isinstance(node, AndExpr):
        return f"({translate(node.left)}) AND ({translate(node.right)})"

    if isinstance(node, OrExpr):
        return f"({translate(node.left)}) OR ({translate(node.right)})"

    if isinstance(node, NotExpr):
        return f"NOT ({translate(node.operand)})"

    raise TypeError(f"Unknown node type: {type(node)}")


def to_insights_query(node: QueryNode, service: str) -> str:
    """Return a complete CloudWatch Logs Insights query string."""
    filter_expr = translate(node)
    service_clause = f"service = '{service}'"
    if filter_expr == "1 = 1":
        combined = service_clause
    else:
        combined = f"({service_clause}) AND ({filter_expr})"
    return (
        "fields @timestamp, @message, level, service, traceId\n"
        f"| filter {combined}\n"
        "| sort @timestamp desc"
    )


