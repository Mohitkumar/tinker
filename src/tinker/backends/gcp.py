"""GCP Cloud Logging and Cloud Monitoring backend."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import structlog

from tinker.backends.base import (
    Anomaly,
    LogEntry,
    MetricPoint,
    ObservabilityBackend,
    Trace,
    TraceSpan,
)

log = structlog.get_logger(__name__)


class GCPBackend(ObservabilityBackend):
    """Observability backend backed by GCP Cloud Logging and Cloud Monitoring."""

    def __init__(self, config: dict | None = None) -> None:
        from google.cloud import logging as gcp_logging
        from google.cloud import monitoring_v3

        cfg = config or {}
        self._project = cfg.get("project_id") or ""
        self._logging_client = gcp_logging.Client(project=self._project)
        self._monitoring_client = monitoring_v3.MetricServiceClient()

    async def query_logs(
        self,
        service: str,
        query: str,
        start: datetime,
        end: datetime,
        limit: int = 100,
        resource_type: str | None = None,
    ) -> list[LogEntry]:
        import asyncio

        # Detect raw GCP filter syntax — pass it through unchanged rather than
        # re-translating it through the Tinkr query parser.
        # Heuristics: starts with a known GCP field prefix, or uses severity= / labels= style.
        _GCP_NATIVE = ("resource.", "labels.", "severity=", "logName=", "httpRequest.", "jsonPayload.", "textPayload=")
        is_native = query == "*" or any(query.startswith(p) or f" {p}" in query for p in _GCP_NATIVE)

        if query == "*":
            native_filter = (
                f'resource.labels.service_name="{service}" '
                f'AND timestamp>="{start.isoformat()}" '
                f'AND timestamp<="{end.isoformat()}"'
            )
        elif is_native:
            native_filter = (
                f'resource.labels.service_name="{service}" '
                f"AND ({query}) "
                f'AND timestamp>="{start.isoformat()}" '
                f'AND timestamp<="{end.isoformat()}"'
            )
        else:
            from tinker.query import parse_query, translate_for

            ast = parse_query(query)
            base = translate_for("gcp", ast, service=service, resource_type=resource_type)
            native_filter = (
                f'{base} AND timestamp>="{start.isoformat()}" AND timestamp<="{end.isoformat()}"'
            )
        filter_str = native_filter

        log.debug("gcp.query_logs", service=service, filter=filter_str)

        entries = await asyncio.to_thread(
            lambda: list(
                self._logging_client.list_entries(
                    filter_=filter_str,
                    page_size=limit,
                    order_by="timestamp desc",
                )
            )
        )

        return [e for e in (self._parse_entry(x) for x in entries) if e is not None]

    @staticmethod
    def _message_from_http_request(http) -> str:
        """Build a readable log message from a GCP httpRequest object or dict."""
        if not http:
            return ""
        if isinstance(http, dict):
            method = http.get("requestMethod", "")
            url = http.get("requestUrl", "")
            status = http.get("status", "")
            latency_raw = http.get("latency", "")
            latency_ms: float | None = None
            if latency_raw:
                try:
                    latency_ms = float(str(latency_raw).rstrip("s")) * 1000
                except (ValueError, TypeError):
                    pass
        else:
            # Proto message (google.cloud.logging_v2.types.HttpRequest)
            method = getattr(http, "request_method", "") or ""
            url = getattr(http, "request_url", "") or ""
            status = getattr(http, "status", "") or ""
            latency_proto = getattr(http, "latency", None)
            latency_ms = None
            if latency_proto is not None:
                try:
                    latency_ms = (latency_proto.seconds + latency_proto.nanos / 1e9) * 1000
                except (AttributeError, TypeError):
                    pass

        parts = [str(p) for p in [method, url] if p]
        if status:
            parts.append(f"→ {status}")
        if latency_ms is not None:
            parts.append(f"({latency_ms:.0f}ms)")
        return " ".join(parts)

    # Log name fragments that indicate internal GCP plumbing — skip these entirely.
    _SKIP_LOG_FRAGMENTS = (
        "cloudaudit.googleapis.com",
    )

    # Log name fragments that indicate Cloud Run HTTP request logs.
    _HTTP_REQUEST_LOG_FRAGMENTS = (
        "run.googleapis.com%2Frequests",
        "run.googleapis.com/requests",
    )

    def _parse_entry(self, entry: object) -> "LogEntry | None":
        from google.cloud.logging import StructEntry, TextEntry

        log_name: str = str(getattr(entry, "log_name", "") or "")

        # Drop internal GCP audit/system-event logs — not useful to users
        if any(f in log_name for f in self._SKIP_LOG_FRAGMENTS):
            return None

        ts = getattr(entry, "timestamp", datetime.now(timezone.utc))
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)

        severity = str(getattr(entry, "severity", "INFO"))
        trace = str(getattr(entry, "trace", ""))

        # Cloud Run request logs — message lives in httpRequest, not in payload
        if any(f in log_name for f in self._HTTP_REQUEST_LOG_FRAGMENTS):
            message = self._message_from_http_request(getattr(entry, "http_request", None))
        elif isinstance(entry, StructEntry):
            payload = entry.payload or {}
            message = payload.get("message", "")
            if not message and payload:
                message = str(payload)
        elif isinstance(entry, TextEntry):
            # varlog/system and similar text-payload logs
            message = entry.payload or ""
        else:
            payload_val = getattr(entry, "payload", None)
            message = str(payload_val) if payload_val else ""
            # Final fallback: try httpRequest if still empty
            if not message:
                message = self._message_from_http_request(getattr(entry, "http_request", None))

        return LogEntry(
            timestamp=ts,
            message=message,
            level=severity,
            trace_id=trace.split("/")[-1] if trace else "",
        )

    async def get_metrics(
        self,
        service: str,
        metric_name: str,
        start: datetime,
        end: datetime,
        dimensions: dict[str, str] | None = None,
        resource_type: str | None = None,
    ) -> list[MetricPoint]:
        import asyncio

        from google.cloud.monitoring_v3 import TimeInterval
        from google.protobuf.timestamp_pb2 import Timestamp

        log.debug("gcp.get_metrics", service=service, metric=metric_name)

        interval = TimeInterval(
            start_time=Timestamp(seconds=int(start.timestamp())),
            end_time=Timestamp(seconds=int(end.timestamp())),
        )
        project_name = f"projects/{self._project}"
        filter_str = (
            f'metric.type="custom.googleapis.com/{metric_name}" '
            f'AND resource.labels.service_name="{service}"'
        )

        results = await asyncio.to_thread(
            lambda: list(
                self._monitoring_client.list_time_series(
                    request={
                        "name": project_name,
                        "filter": filter_str,
                        "interval": interval,
                        "view": "FULL",
                    }
                )
            )
        )

        points: list[MetricPoint] = []
        for ts in results:
            for point in ts.points:
                pts = point.interval.start_time
                points.append(
                    MetricPoint(
                        timestamp=datetime.fromtimestamp(pts.seconds, tz=timezone.utc),
                        value=point.value.double_value,
                        unit=ts.metric_kind.name,
                    )
                )
        return points

    # ── Traces via Cloud Trace ────────────────────────────────────────────────

    async def get_traces(
        self,
        service: str,
        since: str = "1h",
        limit: int = 20,
        tags: dict[str, str] | None = None,
    ) -> list[Trace]:
        """Fetch recent traces from GCP Cloud Trace."""
        import asyncio

        unit = since[-1]
        value = int(since[:-1])
        delta = {
            "m": timedelta(minutes=value),
            "h": timedelta(hours=value),
            "d": timedelta(days=value),
        }.get(unit, timedelta(hours=1))
        start = datetime.now(timezone.utc) - delta

        try:
            from google.cloud import trace_v2

            client = trace_v2.TraceServiceClient()
            project_name = f"projects/{self._project}"

            filter_str = f'span:"{service}" AND +start_time>="{start.isoformat()}"'
            if tags:
                for k, v in tags.items():
                    filter_str += f' AND label:"{k}:{v}"'

            raw_traces = await asyncio.to_thread(
                lambda: list(
                    client.list_traces(
                        request={"parent": project_name, "filter": filter_str, "page_size": limit}
                    )
                )
            )
        except Exception as exc:
            log.warning("gcp.get_traces.error", service=service, error=str(exc))
            return []

        traces: list[Trace] = []
        for t in raw_traces[:limit]:
            spans = []
            start_time = None
            end_time = None
            has_error = False

            for s in t.spans:
                try:
                    s_start = s.start_time.ToDatetime(tzinfo=timezone.utc)
                    s_end = s.end_time.ToDatetime(tzinfo=timezone.utc)
                    dur_ms = (s_end - s_start).total_seconds() * 1000
                    if start_time is None or s_start < start_time:
                        start_time = s_start
                    if end_time is None or s_end > end_time:
                        end_time = s_end
                    if s.status and s.status.code != 0:
                        has_error = True
                    spans.append(
                        TraceSpan(
                            span_id=s.span_id,
                            operation_name=s.display_name.value
                            if hasattr(s.display_name, "value")
                            else str(s.display_name),
                            service=service,
                            start_time=s_start,
                            duration_ms=dur_ms,
                            status="error" if (s.status and s.status.code != 0) else "ok",
                            parent_span_id=s.parent_span_id or "",
                        )
                    )
                except Exception:
                    continue

            root_op = spans[0].operation_name if spans else "unknown"
            total_ms = (
                (end_time - start_time).total_seconds() * 1000 if start_time and end_time else 0.0
            )
            traces.append(
                Trace(
                    trace_id=t.name.split("/")[-1],
                    service=service,
                    operation_name=root_op,
                    start_time=start_time or datetime.now(timezone.utc),
                    duration_ms=total_ms,
                    span_count=len(spans),
                    status="error" if has_error else "ok",
                    spans=spans,
                )
            )

        return traces

    async def detect_anomalies(
        self,
        service: str,
        window_minutes: int = 10,
    ) -> list[Anomaly]:
        end = datetime.now(timezone.utc)
        start = end - timedelta(minutes=window_minutes)
        anomalies: list[Anomaly] = []

        error_logs = await self.query_logs(
            service, "level:ERROR", start, end, limit=200
        )
        if len(error_logs) > 10:
            representative, summary = self._summarize_logs(error_logs, window_minutes)
            anomalies.append(
                Anomaly(
                    service=service,
                    metric="error_count",
                    description=f"High error rate: {len(error_logs)} errors in {window_minutes}m",
                    severity="high",
                    current_value=float(len(error_logs)),
                    threshold=10.0,
                    recent_logs=representative,
                    log_summary=summary,
                )
            )

        return anomalies
