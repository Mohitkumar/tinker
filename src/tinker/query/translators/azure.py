"""Translate a Tinker QueryNode to KQL (Kusto Query Language) for Azure Log Analytics.

KQL is a pipe-based language. We generate a `where` clause that can be appended
to the caller's base table query.

Examples:
    level:ERROR
      → where SeverityLevel == "Error" and ServiceName == "payments-api"

    level:(ERROR OR WARN) AND "timeout"
      → where SeverityLevel in ("Error", "Warning") and ServiceName == "..."
          and Message contains "timeout"

Azure Log Analytics severity names differ from the standard:
    ERROR   → Error
    WARN    → Warning
    INFO    → Information
    DEBUG   → Verbose
    CRITICAL→ Critical
"""

from __future__ import annotations

from tinker.query.ast import AndExpr, FieldFilter, NotExpr, OrExpr, QueryNode, TextFilter

_SEVERITY_MAP: dict[str, str] = {
    "debug":    "Verbose",
    "verbose":  "Verbose",
    "info":     "Information",
    "information": "Information",
    "warn":     "Warning",
    "warning":  "Warning",
    "error":    "Error",
    "critical": "Critical",
    "fatal":    "Critical",
}

_FIELD_MAP: dict[str, str] = {
    "level":    "SeverityLevel",
    "service":  "ServiceName",
    "message":  "Message",
    "trace_id": "OperationId",
    "span_id":  "Id",
}


def _kql_field(name: str) -> str:
    return _FIELD_MAP.get(name, name)


def _kql_severity(v: str) -> str:
    return _SEVERITY_MAP.get(v.lower(), v)


def translate(node: QueryNode) -> str:
    """Return a KQL boolean expression suitable for use in a `where` clause."""
    if isinstance(node, TextFilter):
        if node.text == "*":
            return ""
        op = "==" if node.exact else "contains"
        return f'Message {op} "{node.text}"'

    if isinstance(node, FieldFilter):
        field = _kql_field(node.field)
        values = (
            [_kql_severity(v) for v in node.values]
            if node.field == "level"
            else node.values
        )
        if len(values) == 1:
            return f'{field} == "{values[0]}"'
        vals_str = ", ".join(f'"{v}"' for v in values)
        return f"{field} in ({vals_str})"

    if isinstance(node, AndExpr):
        l, r = translate(node.left), translate(node.right)
        if not l:
            return r
        if not r:
            return l
        return f"({l}) and ({r})"

    if isinstance(node, OrExpr):
        l, r = translate(node.left), translate(node.right)
        return f"({l}) or ({r})"

    if isinstance(node, NotExpr):
        inner = translate(node.operand)
        return f"not ({inner})"

    raise TypeError(f"Unknown node type: {type(node)}")


def to_kql_where(node: QueryNode, service: str, table: str = "AppTraces") -> str:
    """Return a complete KQL query string with table, service filter, and where clause."""
    expr = translate(node)
    service_clause = f'ServiceName == "{service}"'
    if not expr:
        where_clause = service_clause
    else:
        where_clause = f"{service_clause} and ({expr})"
    return (
        f"{table}\n"
        f"| where {where_clause}\n"
        "| order by TimeGenerated desc"
    )
