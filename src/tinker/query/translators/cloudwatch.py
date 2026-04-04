"""Translate a Tinker QueryNode to a CloudWatch Logs Insights query string.

resource:TYPE controls which log group is queried:
    resource:lambda  → /aws/lambda/{service}
    resource:ecs     → /ecs/{service}
    resource:eks     → /aws/containerinsights/{service}/application
    resource:ec2     → /aws/ec2/{service}
    resource:apigw   → API-Gateway-Execution-Logs_{service}/prod
    resource:rds     → /aws/rds/instance/{service}/postgresql
    (no resource)    → auto-discover via describe_log_groups
"""

from __future__ import annotations

import re

from tinker.query.ast import AndExpr, FieldFilter, NotExpr, OrExpr, QueryNode, TextFilter
from tinker.query.resource import CW_LOG_GROUP, extract_resource

# Map canonical Tinker field names → CloudWatch Insights field names
_FIELD_MAP: dict[str, str] = {
    "level":    "level",
    "service":  "service",
    "message":  "@message",
    "trace_id": "traceId",
    "span_id":  "spanId",
}


def _cw_field(name: str) -> str:
    return _FIELD_MAP.get(name, name)


def translate(node: QueryNode) -> str:
    """Return a CloudWatch Logs Insights filter expression (no leading `| filter`).

    resource:TYPE nodes are ignored here — they are consumed by resolve_log_groups().
    """
    if isinstance(node, TextFilter):
        if node.text == "*":
            return "1 = 1"
        escaped = node.text.replace("/", "\\/")
        if node.exact:
            return f"@message like /{re.escape(node.text)}/"
        return f"@message like /{escaped}/"

    if isinstance(node, FieldFilter):
        if node.field == "resource":
            return "1 = 1"   # consumed elsewhere
        field = _cw_field(node.field)
        if len(node.values) == 1:
            return f"{field} = '{node.values[0]}'"
        vals = ", ".join(f"'{v}'" for v in node.values)
        return f"{field} in [{vals}]"

    if isinstance(node, AndExpr):
        l, r = translate(node.left), translate(node.right)
        # Collapse trivially true clauses
        if l == "1 = 1": return r
        if r == "1 = 1": return l
        return f"({l}) AND ({r})"

    if isinstance(node, OrExpr):
        return f"({translate(node.left)}) OR ({translate(node.right)})"

    if isinstance(node, NotExpr):
        return f"NOT ({translate(node.operand)})"

    raise TypeError(f"Unknown node type: {type(node)}")


def resolve_log_groups(node: QueryNode, service: str) -> list[str]:
    """Return the list of log group name(s) to query for this service + resource.

    Returns an empty list when auto-discovery should be used (caller should
    call describe_log_groups with the service name as pattern).
    """
    resource_type, _ = extract_resource(node)
    if resource_type is None:
        return []   # signal: auto-discover

    pattern = CW_LOG_GROUP.get(resource_type)
    if pattern:
        return [pattern.format(service=service)]

    # Unknown resource type — treat as a literal log group prefix
    return [f"/{resource_type}/{service}"]


def to_insights_query(node: QueryNode, service: str) -> str:
    """Return a complete CloudWatch Logs Insights query string.

    The resource:TYPE node is stripped before building the filter expression
    since it controls log group selection, not the Insights filter itself.
    """
    _, stripped = extract_resource(node)
    filter_expr = translate(stripped)

    if filter_expr == "1 = 1":
        combined = "1 = 1"
    else:
        combined = filter_expr

    return (
        "fields @timestamp, @message, level, service, traceId\n"
        f"| filter {combined}\n"
        "| sort @timestamp desc"
    )
