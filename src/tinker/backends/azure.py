"""Azure observability backend.

Covers:
  - Azure Monitor Logs / Log Analytics  (KQL queries)
  - Azure Monitor Metrics               (REST API)
  - Application Insights                (dependency + exception traces)

Authentication
--------------
No long-lived credentials needed when running on Azure.
The SDK picks up credentials automatically via DefaultAzureCredential, which
checks (in order):

  1. EnvironmentCredential  (AZURE_CLIENT_ID + AZURE_CLIENT_SECRET + AZURE_TENANT_ID)
  2. WorkloadIdentityCredential  (AKS Workload Identity / OIDC federation)
  3. ManagedIdentityCredential   (Container Apps, AKS, VMs — preferred for prod)
  4. AzureCliCredential          (local dev: `az login`)

Required RBAC roles on the workspace / subscription:
  - Monitoring Reader
  - Log Analytics Reader

Required environment variables
-------------------------------
  AZURE_LOG_ANALYTICS_WORKSPACE_ID   (required)
  AZURE_SUBSCRIPTION_ID              (required for metrics)
  AZURE_RESOURCE_GROUP               (required for metrics)
  AZURE_TENANT_ID                    (only for EnvironmentCredential)
  AZURE_CLIENT_ID                    (only for EnvironmentCredential or pod identity)
  AZURE_CLIENT_SECRET                (only for EnvironmentCredential — avoid in prod)
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any

import structlog

from tinker.backends.base import (
    Anomaly,
    LogEntry,
    MetricPoint,
    ObservabilityBackend,
    Trace,
    TraceSpan,
)
from tinker.backends.sanitize import sanitize_log_content

log = structlog.get_logger(__name__)


class AzureBackend(ObservabilityBackend):
    """Observability backend for Azure Monitor Logs + Metrics."""

    def __init__(self, config: dict | None = None) -> None:
        from azure.identity import DefaultAzureCredential
        from azure.monitor.query import LogsQueryClient, MetricsQueryClient

        cfg = config or {}
        self._workspace_id: str = cfg.get("workspace_id") or ""
        self._subscription_id: str = cfg.get("subscription_id") or ""
        self._resource_group: str = cfg.get("resource_group") or ""

        credential = DefaultAzureCredential()
        self._logs_client = LogsQueryClient(credential)
        self._metrics_client = MetricsQueryClient(credential)

    # ── Logs via Log Analytics (KQL) ─────────────────────────────────────────

    async def query_logs(
        self,
        service: str,
        query: str,
        start: datetime,
        end: datetime,
        limit: int = 100,
        resource_type: str | None = None,
    ) -> list[LogEntry]:
        """Run a KQL query against the configured Log Analytics workspace.

        `query` is a Tinker unified query string (e.g. 'level:ERROR AND "timeout"').
        `resource_type` controls which KQL table is queried (aks, aca, appservice, etc.).
        Raw KQL (containing '|' or KQL keywords) is passed through unchanged.
        """
        from azure.monitor.query import LogsQueryStatus

        if any(kw in query for kw in ["|", "where ", "search ", "union "]):
            # Raw KQL — pass through
            kql = query
        else:
            from tinker.query import parse_query, translate_for

            ast = parse_query(query)
            kql = (
                translate_for("azure", ast, service=service, resource_type=resource_type)
                + f" | take {limit}"
            )

        log.debug("azure.query_logs", service=service, kql=kql)
        timespan = end - start

        try:
            result = await asyncio.to_thread(
                self._logs_client.query_workspace,
                workspace_id=self._workspace_id,
                query=kql,
                timespan=timespan,
            )
        except Exception as exc:
            log.error("azure.query_logs.failed", error=str(exc))
            raise

        if result.status != LogsQueryStatus.SUCCESS:
            log.warning("azure.query_logs.partial", status=result.status)

        entries: list[LogEntry] = []
        for table in result.tables or []:
            col_names = [c.name for c in table.columns]
            for row in table.rows:
                record = dict(zip(col_names, row))
                entries.append(self._parse_row(record, service))

        return entries

    def _parse_row(self, row: dict[str, Any], service: str) -> LogEntry:
        ts_raw = row.get("TimeGenerated") or row.get("timestamp")
        if isinstance(ts_raw, datetime):
            ts = ts_raw if ts_raw.tzinfo else ts_raw.replace(tzinfo=timezone.utc)
        else:
            ts = datetime.now(timezone.utc)

        # Normalise severity across AppTraces, AppExceptions, AzureDiagnostics
        severity_map: dict[Any, str] = {
            "Verbose": "DEBUG",
            "Information": "INFO",
            "Warning": "WARN",
            "Error": "ERROR",
            "Critical": "CRITICAL",
            0: "VERBOSE",
            1: "INFO",
            2: "WARN",
            3: "ERROR",
            4: "CRITICAL",
        }
        raw_level = row.get("SeverityLevel") or row.get("Level")
        level: str

        if raw_level:
            level = severity_map.get(raw_level, str(raw_level).upper())
        elif "LogEntry" in row:
            # ContainerLog table: no level column — try to parse JSON from the
            # raw log line (apps writing structured JSON to stdout on AKS).
            import json as _json

            log_entry_text = str(row.get("LogEntry", ""))
            try:
                parsed = _json.loads(log_entry_text)
                payload_level = parsed.get("level") or parsed.get("severity") or "INFO"
                level = severity_map.get(payload_level, str(payload_level).upper())
            except (_json.JSONDecodeError, TypeError):
                # Plain-text log line — scan for known level keywords
                import re as _re

                m = _re.search(
                    r"\b(CRITICAL|FATAL|ERROR|WARN(?:ING)?|DEBUG|INFO)\b",
                    log_entry_text,
                    _re.IGNORECASE,
                )
                kw_map = {
                    "CRITICAL": "CRITICAL", "FATAL": "CRITICAL", "ERROR": "ERROR",
                    "WARN": "WARN", "WARNING": "WARN", "DEBUG": "DEBUG", "INFO": "INFO",
                }
                level = kw_map.get(m.group(1).upper(), "INFO") if m else "INFO"
        else:
            level = "INFO"

        message = str(
            row.get("Message")
            or row.get("LogEntry")
            or row.get("RenderedDescription")
            or row.get("ResultDescription")
            or ""
        )

        return LogEntry(
            timestamp=ts,
            message=sanitize_log_content(message),
            level=level,
            service=str(row.get("AppRoleName", service)),
            trace_id=str(row.get("OperationId", "")),
            span_id=str(row.get("Id", "")),
        )

    # ── Metrics via Azure Monitor ─────────────────────────────────────────────

    async def get_metrics(
        self,
        service: str,
        metric_name: str,
        start: datetime,
        end: datetime,
        dimensions: dict[str, str] | None = None,
        resource_type: str | None = None,
    ) -> list[MetricPoint]:
        """Fetch Azure Monitor metrics for a resource.

        The `service` parameter is interpreted as the resource URI:
          /subscriptions/{sub}/resourceGroups/{rg}/providers/Microsoft.Web/sites/{app}
        Or pass just the app name and we build the URI from config.
        """
        from azure.monitor.query import MetricAggregationType

        log.debug("azure.get_metrics", service=service, metric=metric_name)

        if not service.startswith("/subscriptions"):
            resource_uri = (
                f"/subscriptions/{self._subscription_id}"
                f"/resourceGroups/{self._resource_group}"
                f"/providers/Microsoft.Web/sites/{service}"
            )
        else:
            resource_uri = service

        try:
            result = await asyncio.to_thread(
                self._metrics_client.query_resource,
                resource_uri=resource_uri,
                metric_names=[metric_name],
                timespan=(start, end),
                granularity=timedelta(minutes=1),
                aggregations=[MetricAggregationType.AVERAGE],
            )
        except Exception as exc:
            log.error("azure.get_metrics.failed", error=str(exc))
            raise

        points: list[MetricPoint] = []
        for metric in result.metrics:
            for ts in metric.timeseries:
                for dp in ts.data:
                    if dp.timestamp and dp.average is not None:
                        pts = dp.timestamp
                        if pts.tzinfo is None:
                            pts = pts.replace(tzinfo=timezone.utc)
                        points.append(
                            MetricPoint(
                                timestamp=pts,
                                value=dp.average,
                                unit=metric.unit or "",
                            )
                        )
        return points

    # ── Traces via App Insights (KQL) ────────────────────────────────────────

    async def get_traces(
        self,
        service: str,
        since: str = "1h",
        limit: int = 20,
        tags: dict[str, str] | None = None,
    ) -> list[Trace]:
        """Fetch traces from Application Insights AppDependencies + AppRequests tables."""
        if not self._workspace_id:
            return []

        unit = since[-1]
        value = int(since[:-1])
        delta = {
            "m": timedelta(minutes=value),
            "h": timedelta(hours=value),
            "d": timedelta(days=value),
        }.get(unit, timedelta(hours=1))

        kql = f"""
AppRequests
| where AppRoleName == "{service}"
| where TimeGenerated >= ago({value}{unit})
| summarize
    DurationMs = avg(DurationMs),
    SpanCount  = count(),
    HasError   = max(Success == false)
    by OperationId, Name
| order by TimeGenerated desc
| limit {limit}
"""
        try:
            from azure.monitor.query import LogsQueryStatus

            result = await asyncio.to_thread(
                self._logs_client.query_workspace,
                workspace_id=self._workspace_id,
                query=kql,
                timespan=delta,
            )
            if result.status != LogsQueryStatus.SUCCESS or not result.tables:
                return []
        except Exception as exc:
            log.warning("azure.get_traces.error", service=service, error=str(exc))
            return []

        traces: list[Trace] = []
        table = result.tables[0]
        cols = [c.name for c in table.columns]

        def _col(row, name: str, default=None):
            try:
                return row[cols.index(name)]
            except (ValueError, IndexError):
                return default

        for row in table.rows:
            try:
                op_id = str(_col(row, "OperationId") or "")
                op_name = str(_col(row, "Name") or "unknown")
                dur_ms = float(_col(row, "DurationMs") or 0)
                span_count = int(_col(row, "SpanCount") or 1)
                has_error = bool(_col(row, "HasError") or False)
                traces.append(
                    Trace(
                        trace_id=op_id[:16] if op_id else op_name[:16],
                        service=service,
                        operation_name=op_name,
                        start_time=datetime.now(timezone.utc),
                        duration_ms=dur_ms,
                        span_count=span_count,
                        status="error" if has_error else "ok",
                    )
                )
            except Exception:
                continue
        return traces

    # ── Anomaly detection ─────────────────────────────────────────────────────

    async def detect_anomalies(
        self,
        service: str,
        window_minutes: int = 10,
    ) -> list[Anomaly]:
        end = datetime.now(timezone.utc)
        start = end - timedelta(minutes=window_minutes)
        anomalies: list[Anomaly] = []

        # KQL: count exceptions in window
        kql = (
            f"AppExceptions"
            f" | where AppRoleName == '{service}'"
            f" | where TimeGenerated >= datetime({start.isoformat()})"
            f" | summarize ErrorCount=count()"
        )
        try:
            entries = await self.query_logs(service, kql, start, end, limit=1)
            # The summarize result comes back as a single row with ErrorCount
            error_count = int(entries[0].extra.get("ErrorCount", 0)) if entries else 0
            if error_count > 10:
                # Re-query to get actual log entries for summarisation
                err_logs = await self.query_logs(
                    service,
                    f"AppExceptions | where AppRoleName == '{service}'",
                    start,
                    end,
                    limit=200,
                )
                representative, summary = self._summarize_logs(err_logs, window_minutes)
                anomalies.append(
                    Anomaly(
                        service=service,
                        metric="exception_count",
                        description=f"{error_count} exceptions in {window_minutes}m",
                        severity="high" if error_count > 50 else "medium",
                        current_value=float(error_count),
                        threshold=10.0,
                        recent_logs=representative,
                        log_summary=summary,
                    )
                )
        except Exception:
            log.exception("azure.detect_anomalies.failed", service=service)

        return anomalies
