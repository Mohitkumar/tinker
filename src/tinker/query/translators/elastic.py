"""Translate a Tinker QueryNode to an Elasticsearch/OpenSearch query DSL dict.

Returns a Python dict that can be passed directly as the `query` key in an
Elasticsearch search request body.

Examples:
    level:ERROR
      → {"bool": {"must": [
            {"term": {"log.level": "error"}},
            {"term": {"service.name": "payments-api"}}
        ]}}

    level:(ERROR OR WARN) AND "timeout"
      → {"bool": {"must": [
            {"terms": {"log.level": ["error", "warn"]}},
            {"match": {"message": "timeout"}},
            {"term": {"service.name": "payments-api"}}
        ]}}
"""

from __future__ import annotations

from typing import Any

from tinker.query.ast import AndExpr, FieldFilter, NotExpr, OrExpr, QueryNode, TextFilter
from tinker.query.resource import DEFAULT_ELASTIC_INDEX, ELASTIC_INDEX

_FIELD_MAP: dict[str, str] = {
    "level": "log.level",
    "service": "service.name",
    "message": "message",
    "trace_id": "trace.id",
    "span_id": "span.id",
}

# Apps that write flat JSON (not ECS) often put the log level under a root
# field rather than the nested log.level.  We cover all common variants with a
# should so that level:ERROR matches regardless of which field the app uses.
_LEVEL_FIELDS = ("log.level", "level", "severity")


def _es_field(name: str) -> str:
    return _FIELD_MAP.get(name, name)


def translate(node: QueryNode) -> dict[str, Any]:
    """Return an Elasticsearch query DSL dict for the given AST node."""
    if isinstance(node, TextFilter):
        if node.text == "*":
            return {"match_all": {}}
        return {"match": {"message": node.text}}

    if isinstance(node, FieldFilter):
        if node.field == "level":
            # Cover ECS (log.level), flat (level), and alternative (severity).
            # Apps write lowercase; Filebeat may write uppercase — use lowercase
            # and rely on the index mapping being keyword/case-folded.
            values = [v.lower() for v in node.values]
            clauses: list[dict[str, Any]] = []
            for f in _LEVEL_FIELDS:
                if len(values) == 1:
                    clauses.append({"term": {f: values[0]}})
                else:
                    clauses.append({"terms": {f: values}})
            return {"bool": {"should": clauses, "minimum_should_match": 1}}

        field = _es_field(node.field)
        if len(node.values) == 1:
            return {"term": {field: node.values[0]}}
        return {"terms": {field: node.values}}

    if isinstance(node, AndExpr):
        left = translate(node.left)
        right = translate(node.right)
        # Flatten nested bool musts
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


def resolve_index(resource_type: str | None) -> str:
    """Return the Elasticsearch index pattern for the given resource type."""
    if resource_type:
        return ELASTIC_INDEX.get(resource_type.lower(), DEFAULT_ELASTIC_INDEX)
    return DEFAULT_ELASTIC_INDEX


def to_query(node: QueryNode, service: str, resource_type: str | None = None) -> dict[str, Any]:
    """Return a complete Elasticsearch query dict with the service filter applied."""
    service_clause: dict[str, Any] = {"term": {"service.name": service}}
    expr = translate(node)

    if expr == {"match_all": {}}:
        return {"bool": {"must": [service_clause]}}

    if "bool" in expr and "must" in expr["bool"] and len(expr["bool"]) == 1:
        must_clauses: list[dict[str, Any]] = expr["bool"]["must"]
    else:
        must_clauses = [expr]

    return {"bool": {"must": [service_clause, *must_clauses]}}
