"""Translate a Tinker QueryNode to KQL for Azure Log Analytics.

resource:TYPE controls which KQL table is queried:
    resource:appservice → AppServiceConsoleLogs
    resource:aks        → ContainerLog
    resource:vm         → Syslog
    resource:function   → FunctionAppLogs
    resource:apigw      → ApiManagementGatewayLogs
    resource:sql / db   → AzureDiagnostics
    (no resource)       → AppTraces  (Application Insights default)
"""

from __future__ import annotations

from tinker.query.ast import AndExpr, FieldFilter, NotExpr, OrExpr, QueryNode, TextFilter
from tinker.query.resource import AZURE_TABLE

_SEVERITY_MAP: dict[str, str] = {
    "debug": "Verbose",
    "verbose": "Verbose",
    "info": "Information",
    "information": "Information",
    "warn": "Warning",
    "warning": "Warning",
    "error": "Error",
    "critical": "Critical",
    "fatal": "Critical",
}

# Per-table column names for common fields
_TABLE_FIELD_MAP: dict[str, dict[str, str]] = {
    "AppTraces": {"level": "SeverityLevel", "service": "AppRoleName", "message": "Message"},
    # ContainerLog has no structured level column — LogEntrySource is "stdout"/"stderr".
    # Level must be extracted from the JSON payload in LogEntry using parse_json().
    "ContainerLog": {"level": "_parsed_level", "service": "ContainerName", "message": "LogEntry"},
    "AppServiceConsoleLogs": {
        "level": "Level",
        "service": "ScmType",
        "message": "ResultDescription",
    },
    "Syslog": {"level": "SeverityLevel", "service": "Computer", "message": "SyslogMessage"},
    "FunctionAppLogs": {"level": "Level", "service": "FunctionName", "message": "Message"},
    "ApiManagementGatewayLogs": {
        "level": "IsRequestSuccess",
        "service": "ServiceName",
        "message": "ResponseBody",
    },
    "AzureDiagnostics": {"level": "Level", "service": "ResourceId", "message": "log_s"},
}

_DEFAULT_FIELD_MAP = {"level": "SeverityLevel", "service": "ServiceName", "message": "Message"}


def _get_field_map(table: str) -> dict[str, str]:
    return _TABLE_FIELD_MAP.get(table, _DEFAULT_FIELD_MAP)


def _kql_severity(v: str) -> str:
    return _SEVERITY_MAP.get(v.lower(), v)


def translate(node: QueryNode, field_map: dict[str, str]) -> str:
    """Return a KQL boolean expression for use in a `where` clause."""
    if isinstance(node, TextFilter):
        if node.text == "*":
            return ""
        msg_col = field_map.get("message", "Message")
        op = "==" if node.exact else "contains"
        return f'{msg_col} {op} "{node.text}"'

    if isinstance(node, FieldFilter):
        kql_field = field_map.get(node.field, node.field)

        if node.field == "level":
            values = [_kql_severity(v) for v in node.values]
            if kql_field == "_parsed_level":
                # ContainerLog has no level column — extract from JSON payload.
                # parse_json(LogEntry) returns a dynamic; check common field names.
                if len(values) == 1:
                    v = values[0]
                    return (
                        f'(parse_json(LogEntry).level =~ "{v}" '
                        f'or parse_json(LogEntry).severity =~ "{v}")'
                    )
                vals_str = ", ".join(f'"{v}"' for v in values)
                return (
                    f'(parse_json(LogEntry).level in~ ({vals_str}) '
                    f'or parse_json(LogEntry).severity in~ ({vals_str}))'
                )
            if len(values) == 1:
                return f'{kql_field} == "{values[0]}"'
            vals_str = ", ".join(f'"{v}"' for v in values)
            return f"{kql_field} in ({vals_str})"

        if len(node.values) == 1:
            return f'{kql_field} == "{node.values[0]}"'
        vals_str = ", ".join(f'"{v}"' for v in node.values)
        return f"{kql_field} in ({vals_str})"

    if isinstance(node, AndExpr):
        l, r = translate(node.left, field_map), translate(node.right, field_map)
        if not l:
            return r
        if not r:
            return l
        return f"({l}) and ({r})"

    if isinstance(node, OrExpr):
        l, r = translate(node.left, field_map), translate(node.right, field_map)
        return f"({l}) or ({r})"

    if isinstance(node, NotExpr):
        return f"not ({translate(node.operand, field_map)})"

    raise TypeError(f"Unknown node type: {type(node)}")


def to_kql_where(node: QueryNode, service: str, resource_type: str | None = None) -> str:
    """Return a complete KQL query with the correct table and service filter."""
    table = AZURE_TABLE.get(resource_type.lower(), "AppTraces") if resource_type else "AppTraces"
    field_map = _get_field_map(table)
    svc_col = field_map.get("service", "ServiceName")
    expr = translate(node, field_map)

    service_clause = f'{svc_col} == "{service}"'
    where_clause = f"{service_clause} and ({expr})" if expr else service_clause

    return f"{table}\n| where {where_clause}\n| order by TimeGenerated desc"
