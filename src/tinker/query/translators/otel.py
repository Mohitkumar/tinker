"""Translate a Tinker QueryNode to an OpenSearch/Elasticsearch DSL dict
using OpenTelemetry semantic conventions.

OTel log field mapping:
  severity_text                     → log level  (INFO / ERROR / WARN / DEBUG)
  body                              → message text
  resource.attributes.service.name  → service identifier
  trace_id                          → trace correlation
  span_id                           → span correlation

Apps that do not use the OTel SDK may also write to attributes.level or
attributes.severity — these are covered by a should clause alongside
severity_text.
"""

from __future__ import annotations

from typing import Any

from tinker.query.ast import AndExpr, FieldFilter, NotExpr, OrExpr, QueryNode, TextFilter

_FIELD_MAP: dict[str, str] = {
    "level": "severity_text",
    "service": "resource.attributes.service.name",
    "message": "body",
    "trace_id": "trace_id",
    "span_id": "span_id",
}

# OTel severity_text values are uppercase. Also cover apps that write
# attributes.level / attributes.severity when not using the OTel SDK.
_LEVEL_FIELDS = ("severity_text", "attributes.level", "attributes.severity")


def _otel_field(name: str) -> str:
    return _FIELD_MAP.get(name, name)


def translate(node: QueryNode) -> dict[str, Any]:
    """Return an Elasticsearch query DSL dict using OTel field conventions."""
    if isinstance(node, TextFilter):
        if node.text == "*":
            return {"match_all": {}}
        return {"match": {"body": node.text}}

    if isinstance(node, FieldFilter):
        if node.field == "level":
            # OTel severity_text is uppercase; attributes.level/severity may be
            # mixed case depending on the logging library.  Emit a should that
            # covers all three fields in both lower and upper case.
            values_upper = [v.upper() for v in node.values]
            values_lower = [v.lower() for v in node.values]
            clauses: list[dict[str, Any]] = []
            for f in _LEVEL_FIELDS:
                # primary OTel field uses uppercase; attribute fields may be lowercase
                vals = values_upper if f == "severity_text" else values_lower
                if len(vals) == 1:
                    clauses.append({"term": {f: vals[0]}})
                else:
                    clauses.append({"terms": {f: vals}})
            return {"bool": {"should": clauses, "minimum_should_match": 1}}

        field = _otel_field(node.field)
        if len(node.values) == 1:
            return {"term": {field: node.values[0]}}
        return {"terms": {field: node.values}}

    if isinstance(node, AndExpr):
        left = translate(node.left)
        right = translate(node.right)
        must: list[dict[str, Any]] = []
        for clause in (left, right):
            if "bool" in clause and "must" in clause["bool"] and len(clause["bool"]) == 1:
                must.extend(clause["bool"]["must"])
            else:
                must.append(clause)
        return {"bool": {"must": must}}

    if isinstance(node, OrExpr):
        return {
            "bool": {
                "should": [translate(node.left), translate(node.right)],
                "minimum_should_match": 1,
            }
        }

    if isinstance(node, NotExpr):
        return {"bool": {"must_not": [translate(node.operand)]}}

    raise TypeError(f"Unknown node type: {type(node)}")


def to_query(node: QueryNode, service: str) -> dict[str, Any]:
    """Return a complete OTel/OpenSearch query dict with service filter."""
    service_clause: dict[str, Any] = {
        "term": {"resource.attributes.service.name": service}
    }
    expr = translate(node)

    if expr == {"match_all": {}}:
        return {"bool": {"must": [service_clause]}}

    if "bool" in expr and "must" in expr["bool"] and len(expr["bool"]) == 1:
        must_clauses: list[dict[str, Any]] = expr["bool"]["must"]
    else:
        must_clauses = [expr]

    return {"bool": {"must": [service_clause, *must_clauses]}}
