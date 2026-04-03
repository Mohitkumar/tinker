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
        assert SVC in out

    def test_level_error(self):
        out = self._t("level:ERROR")
        assert "level = 'ERROR'" in out
        assert SVC in out

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
        assert f'service_name="{SVC}"' in out

    def test_level_in_stream(self):
        out = self._t("level:ERROR")
        # level:ERROR is promoted to stream selector
        assert 'level="ERROR"' in out
        assert f'service_name="{SVC}"' in out

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
