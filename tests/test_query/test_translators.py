"""Tests for all backend translators."""

import pytest

from tinker.query import parse_query, translate_for


SVC = "payments-api"


# ── CloudWatch ────────────────────────────────────────────────────────────────

class TestCloudWatch:
    def _t(self, q: str) -> str:
        return translate_for("cloudwatch", parse_query(q), service=SVC)

    def test_wildcard(self):
        out = self._t("*")
        assert "fields" in out
        assert "filter" in out

    def test_level_error(self):
        out = self._t("level:ERROR")
        assert "level = 'ERROR'" in out

    def test_text_filter(self):
        out = self._t('"timeout"')
        assert "timeout" in out

    def test_and(self):
        out = self._t('level:ERROR AND "timeout"')
        assert "level = 'ERROR'" in out
        assert "timeout" in out

    def test_multi_value(self):
        out = self._t("level:(ERROR OR WARN)")
        assert "ERROR" in out
        assert "WARN" in out

    def test_not(self):
        out = self._t('NOT "health"')
        assert "NOT" in out
        assert "health" in out


# ── Loki / Grafana ────────────────────────────────────────────────────────────

class TestLoki:
    def _t(self, q: str) -> str:
        return translate_for("grafana", parse_query(q), service=SVC)

    def test_wildcard(self):
        out = self._t("*")
        assert f'service="{SVC}"' in out

    def test_level_in_stream(self):
        out = self._t("level:ERROR")
        # level:ERROR is promoted to stream selector
        assert 'level="ERROR"' in out
        assert f'service="{SVC}"' in out

    def test_text_line_filter(self):
        out = self._t('"timeout"')
        assert "|=" in out
        assert "timeout" in out

    def test_not_text(self):
        out = self._t('NOT "health"')
        assert "!=" in out

    def test_multi_level(self):
        out = self._t("level:(ERROR OR WARN)")
        assert "ERROR|WARN" in out or "WARN|ERROR" in out

    def test_level_and_text(self):
        out = self._t('level:ERROR AND "database"')
        assert 'level="ERROR"' in out
        assert "database" in out


# ── GCP ───────────────────────────────────────────────────────────────────────

class TestGCP:
    def _t(self, q: str) -> str:
        return translate_for("gcp", parse_query(q), service=SVC)

    def test_wildcard(self):
        out = self._t("*")
        assert SVC in out

    def test_level_mapped_to_severity(self):
        out = self._t("level:ERROR")
        assert 'severity="ERROR"' in out

    def test_warn_mapped(self):
        out = self._t("level:WARN")
        assert "WARNING" in out

    def test_text_filter(self):
        out = self._t('"timeout"')
        assert "timeout" in out
        assert "textPayload" in out

    def test_and(self):
        out = self._t('level:ERROR AND "timeout"')
        assert "ERROR" in out
        assert "timeout" in out


# ── Azure KQL ─────────────────────────────────────────────────────────────────

class TestAzure:
    def _t(self, q: str) -> str:
        return translate_for("azure", parse_query(q), service=SVC)

    def test_wildcard(self):
        out = self._t("*")
        assert SVC in out
        assert "AppTraces" in out

    def test_level_to_severity(self):
        out = self._t("level:ERROR")
        assert "Error" in out
        assert "SeverityLevel" in out

    def test_warn_mapped(self):
        out = self._t("level:WARN")
        assert "Warning" in out

    def test_text(self):
        out = self._t('"timeout"')
        assert "timeout" in out
        assert "Message" in out

    def test_kql_structure(self):
        out = self._t("level:ERROR")
        assert "AppTraces" in out
        assert "| where" in out
        assert "| order by" in out


# ── Datadog ───────────────────────────────────────────────────────────────────

class TestDatadog:
    def _t(self, q: str) -> str:
        return translate_for("datadog", parse_query(q), service=SVC)

    def test_wildcard(self):
        out = self._t("*")
        assert f"service:{SVC}" in out

    def test_level_to_status(self):
        out = self._t("level:ERROR")
        assert "status:error" in out
        assert f"service:{SVC}" in out

    def test_text(self):
        out = self._t('"timeout"')
        assert '"timeout"' in out

    def test_not(self):
        out = self._t('NOT "health"')
        assert "-" in out
        assert "health" in out

    def test_multi_level(self):
        out = self._t("level:(ERROR OR WARN)")
        assert "error" in out
        assert "warn" in out


# ── Elasticsearch ─────────────────────────────────────────────────────────────

class TestElastic:
    def _t(self, q: str) -> dict:
        return translate_for("elastic", parse_query(q), service=SVC)

    def test_wildcard(self):
        out = self._t("*")
        assert "bool" in out
        assert any("service.name" in str(c) for c in out["bool"]["must"])

    def test_level(self):
        out = self._t("level:ERROR")
        must = out["bool"]["must"]
        assert any("log.level" in str(c) for c in must)

    def test_text(self):
        out = self._t('"timeout"')
        must = out["bool"]["must"]
        assert any("message" in str(c) for c in must)

    def test_and_flattened(self):
        out = self._t('level:ERROR AND "timeout"')
        # Both conditions in the same must list (flattened)
        must = out["bool"]["must"]
        assert len(must) >= 2

    def test_or(self):
        out = self._t("level:ERROR OR level:WARN")
        # One of the must clauses should be a bool.should
        must = out["bool"]["must"]
        assert any("should" in str(c) for c in must)

    def test_not(self):
        out = self._t('NOT "health"')
        must = out["bool"]["must"]
        assert any("must_not" in str(c) for c in must)


# ── Resource type routing ──────────────────────────────────────────────────────

class TestResourceCloudWatch:
    """resource:TYPE controls CloudWatch log group selection, not the filter."""
    from tinker.query.translators.cloudwatch import resolve_log_groups

    def _resolve(self, q: str) -> list[str]:
        from tinker.query.translators.cloudwatch import resolve_log_groups
        return resolve_log_groups(parse_query(q), SVC)

    def _t(self, q: str) -> str:
        return translate_for("cloudwatch", parse_query(q), service=SVC)

    def test_lambda_log_group(self):
        assert self._resolve("resource:lambda") == [f"/aws/lambda/{SVC}"]

    def test_ecs_log_group(self):
        assert self._resolve("resource:ecs") == [f"/ecs/{SVC}"]

    def test_eks_log_group(self):
        assert self._resolve("resource:eks") == [f"/aws/containerinsights/{SVC}/application"]

    def test_ec2_log_group(self):
        assert self._resolve("resource:ec2") == [f"/aws/ec2/{SVC}"]

    def test_rds_log_group(self):
        assert self._resolve("resource:rds") == [f"/aws/rds/instance/{SVC}/postgresql"]

    def test_no_resource_auto_discover(self):
        # No resource:TYPE → empty list signals auto-discover
        assert self._resolve("level:ERROR") == []

    def test_resource_stripped_from_filter(self):
        out = self._t("resource:lambda AND level:ERROR")
        # resource:lambda should not appear as a filter clause
        assert "resource" not in out
        assert "lambda" not in out
        assert "level = 'ERROR'" in out


class TestResourceGCP:
    def _t(self, q: str) -> str:
        return translate_for("gcp", parse_query(q), service=SVC)

    def test_cloudrun(self):
        out = self._t("resource:cloudrun")
        assert 'resource.type="cloud_run_revision"' in out
        assert f'service_name="{SVC}"' in out

    def test_gke(self):
        out = self._t("resource:gke")
        assert 'resource.type="k8s_container"' in out
        assert f'container_name="{SVC}"' in out

    def test_gce(self):
        out = self._t("resource:gce")
        assert 'resource.type="gce_instance"' in out

    def test_resource_with_filter(self):
        out = self._t('resource:cloudrun AND level:ERROR')
        assert 'resource.type="cloud_run_revision"' in out
        assert 'severity="ERROR"' in out

    def test_unknown_resource_passthrough(self):
        out = self._t("resource:custom-type")
        assert SVC in out
        assert "custom-type" in out


class TestResourceAzure:
    def _t(self, q: str) -> str:
        return translate_for("azure", parse_query(q), service=SVC)

    def test_aks_uses_container_log(self):
        out = self._t("resource:aks")
        assert "ContainerLog" in out
        assert "AppTraces" not in out

    def test_vm_uses_syslog(self):
        out = self._t("resource:vm")
        assert "Syslog" in out

    def test_function_uses_function_app_logs(self):
        out = self._t("resource:function")
        assert "FunctionAppLogs" in out

    def test_appservice(self):
        out = self._t("resource:appservice")
        assert "AppServiceConsoleLogs" in out

    def test_default_app_traces(self):
        out = self._t("level:ERROR")
        assert "AppTraces" in out

    def test_resource_with_filter(self):
        out = self._t('resource:aks AND level:ERROR')
        assert "ContainerLog" in out
        # resource field should not appear as a where clause
        assert "resource" not in out.split("| where")[1]


class TestResourceLoki:
    def _t(self, q: str) -> str:
        return translate_for("grafana", parse_query(q), service=SVC)

    def test_ecs_adds_resource_label(self):
        out = self._t("resource:ecs")
        assert 'resource="container"' in out
        assert f'service="{SVC}"' in out

    def test_host_adds_resource_label(self):
        out = self._t("resource:ec2")
        assert 'resource="host"' in out

    def test_resource_with_level(self):
        out = self._t('resource:ecs AND level:ERROR')
        assert 'resource="container"' in out
        assert 'level="ERROR"' in out

    def test_no_resource_no_extra_labels(self):
        out = self._t("level:ERROR")
        assert "resource=" not in out


class TestResourceElastic:
    def _t(self, q: str) -> dict:
        return translate_for("elastic", parse_query(q), service=SVC)

    def _index(self, q: str) -> str:
        from tinker.query.translators.elastic import resolve_index
        return resolve_index(parse_query(q))

    def test_lambda_index(self):
        assert self._index("resource:lambda") == "lambda-*"

    def test_eks_index(self):
        assert self._index("resource:eks") == "kubernetes-*"

    def test_default_index(self):
        assert self._index("level:ERROR") == "logs-*"

    def test_resource_not_in_query(self):
        out = self._t("resource:lambda AND level:ERROR")
        # resource field should not produce a term filter
        assert "resource" not in str(out)


class TestResourceDatadog:
    def _t(self, q: str) -> str:
        return translate_for("datadog", parse_query(q), service=SVC)

    def test_resource_stripped(self):
        out = self._t("resource:ecs AND level:ERROR")
        assert "resource" not in out
        assert "status:error" in out
        assert f"service:{SVC}" in out

    def test_resource_only(self):
        out = self._t("resource:lambda")
        assert "resource" not in out
        assert f"service:{SVC}" in out
