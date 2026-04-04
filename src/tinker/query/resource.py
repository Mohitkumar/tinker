"""Resource type definitions and per-backend resolution maps.

A `resource` field in a Tinker query specifies what kind of infrastructure
resource to target. Each backend translates this to its native concept.

Usage in queries:
    resource:lambda          # AWS Lambda
    resource:ecs             # AWS ECS / Fargate
    resource:eks             # AWS EKS (Kubernetes)
    resource:ec2             # AWS EC2
    resource:apigw           # AWS API Gateway
    resource:rds             # AWS RDS / Aurora
    resource:gke             # GCP GKE
    resource:cloudrun        # GCP Cloud Run
    resource:appengine       # GCP App Engine
    resource:gce             # GCP Compute Engine
    resource:cloudfn         # GCP Cloud Functions
    resource:aks             # Azure AKS
    resource:appservice      # Azure App Service
    resource:vm              # Azure Virtual Machine
    resource:container       # Generic container (cross-cloud)
    resource:k8s             # Generic Kubernetes (cross-cloud)
    resource:host            # Generic VM / bare-metal
    resource:db              # Generic database

Cross-cloud aliases map to cloud-specific types at translation time based on
which backend is active. Unknown resource types are treated as a best-effort
pattern match so users are never blocked.
"""

from __future__ import annotations

# ── CloudWatch ────────────────────────────────────────────────────────────────
# Maps resource type → log group pattern (f-string with {service})

CW_LOG_GROUP: dict[str, str] = {
    "lambda":    "/aws/lambda/{service}",
    "ecs":       "/ecs/{service}",
    "fargate":   "/ecs/{service}",
    "eks":       "/aws/containerinsights/{service}/application",
    "ec2":       "/aws/ec2/{service}",
    "apigw":     "API-Gateway-Execution-Logs_{service}/prod",
    "rds":       "/aws/rds/instance/{service}/postgresql",
    "aurora":    "/aws/rds/cluster/{service}/postgresql",
    "codebuild": "/aws/codebuild/{service}",
    "stepfn":    "/aws/states/{service}",
    # Cross-cloud aliases → best guess for AWS
    "container": "/ecs/{service}",
    "k8s":       "/aws/containerinsights/{service}/application",
    "host":      "/aws/ec2/{service}",
    "db":        "/aws/rds/instance/{service}/postgresql",
}

# ── GCP ───────────────────────────────────────────────────────────────────────
# Maps resource type → (resource.type value, label key for service name)

GCP_RESOURCE: dict[str, tuple[str, str]] = {
    "cloudrun":   ("cloud_run_revision",  "service_name"),
    "gke":        ("k8s_container",       "container_name"),
    "appengine":  ("gae_app",             "module_id"),
    "gce":        ("gce_instance",        "instance_id"),
    "cloudfn":    ("cloud_function",      "function_name"),
    "dataflow":   ("dataflow_step",       "job_name"),
    # Cross-cloud aliases
    "lambda":     ("cloud_function",      "function_name"),
    "ecs":        ("cloud_run_revision",  "service_name"),
    "eks":        ("k8s_container",       "container_name"),
    "container":  ("cloud_run_revision",  "service_name"),
    "k8s":        ("k8s_container",       "container_name"),
    "host":       ("gce_instance",        "instance_id"),
    "db":         ("cloudsql_database",   "database_id"),
}

# ── Azure ─────────────────────────────────────────────────────────────────────
# Maps resource type → KQL table name

AZURE_TABLE: dict[str, str] = {
    "appservice":  "AppServiceConsoleLogs",
    "aks":         "ContainerLog",
    "vm":          "Syslog",
    "function":    "FunctionAppLogs",
    "apigw":       "ApiManagementGatewayLogs",
    "sql":         "AzureDiagnostics",
    "db":          "AzureDiagnostics",
    # Default app instrumentation
    "app":         "AppTraces",
    # Cross-cloud aliases
    "lambda":      "FunctionAppLogs",
    "ecs":         "ContainerLog",
    "eks":         "ContainerLog",
    "ec2":         "Syslog",
    "rds":         "AzureDiagnostics",
    "container":   "ContainerLog",
    "k8s":         "ContainerLog",
    "host":        "Syslog",
}

# ── Loki ──────────────────────────────────────────────────────────────────────
# Maps resource type → extra stream selector labels to add

LOKI_LABELS: dict[str, dict[str, str]] = {
    "lambda":   {"resource": "lambda"},
    "ecs":      {"resource": "container"},
    "fargate":  {"resource": "container"},
    "eks":      {"resource": "container"},
    "k8s":      {"resource": "container"},
    "ec2":      {"resource": "host"},
    "host":     {"resource": "host"},
    "apigw":    {"resource": "apigw"},
    "rds":      {"resource": "db"},
    "db":       {"resource": "db"},
    "container":{"resource": "container"},
    "cloudrun": {"resource": "container"},
    "gke":      {"resource": "container"},
    "aks":      {"resource": "container"},
    "appservice": {"resource": "container"},
    "vm":       {"resource": "host"},
    "gce":      {"resource": "host"},
}

# ── Elastic ───────────────────────────────────────────────────────────────────
# Maps resource type → Elasticsearch index pattern

ELASTIC_INDEX: dict[str, str] = {
    "lambda":    "lambda-*",
    "ecs":       "ecs-*",
    "fargate":   "ecs-*",
    "eks":       "kubernetes-*",
    "k8s":       "kubernetes-*",
    "ec2":       "syslog-*",
    "host":      "syslog-*",
    "apigw":     "apigw-*",
    "rds":       "rds-*",
    "db":        "rds-*",
    "container": "ecs-*",
    "cloudrun":  "ecs-*",
    "gke":       "kubernetes-*",
    "aks":       "kubernetes-*",
    "appservice":"appservice-*",
    "vm":        "syslog-*",
    "gce":       "syslog-*",
}

DEFAULT_ELASTIC_INDEX = "logs-*"

# ── Helpers ───────────────────────────────────────────────────────────────────

def extract_resource(node: "QueryNode") -> tuple[str | None, "QueryNode"]:  # type: ignore[name-defined]
    """Walk the AST, extract the first `resource:TYPE` FieldFilter value,
    and return (resource_type, remaining_node_without_resource_filter).

    Returns (None, original_node) if no resource field is present.
    """
    from tinker.query.ast import AndExpr, FieldFilter, TextFilter

    resource: str | None = None
    remaining = _strip_resource(node)
    resource = _find_resource(node)
    return resource, remaining


def _find_resource(node: "QueryNode") -> str | None:  # type: ignore[name-defined]
    from tinker.query.ast import AndExpr, FieldFilter
    if isinstance(node, FieldFilter) and node.field == "resource":
        return node.single.lower()
    if isinstance(node, AndExpr):
        return _find_resource(node.left) or _find_resource(node.right)
    return None


def _strip_resource(node: "QueryNode") -> "QueryNode":  # type: ignore[name-defined]
    """Return a copy of the AST with all resource:TYPE nodes removed."""
    from tinker.query.ast import AndExpr, FieldFilter, TextFilter, OrExpr, NotExpr
    if isinstance(node, FieldFilter) and node.field == "resource":
        return TextFilter(text="*", exact=False)
    if isinstance(node, AndExpr):
        left  = _strip_resource(node.left)
        right = _strip_resource(node.right)
        # Collapse `* AND X` → X and `X AND *` → X
        if isinstance(left, TextFilter)  and left.text == "*":  return right
        if isinstance(right, TextFilter) and right.text == "*": return left
        return AndExpr(left, right)
    if isinstance(node, OrExpr):
        return OrExpr(_strip_resource(node.left), _strip_resource(node.right))
    if isinstance(node, NotExpr):
        return NotExpr(_strip_resource(node.operand))
    return node
