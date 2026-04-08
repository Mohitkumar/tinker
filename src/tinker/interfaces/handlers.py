"""Shared command handlers — the canonical implementation of every Tinker command.

Both the CLI and the Slack bot call these functions.
They accept a RemoteClient and return typed data — no rendering, no output, no Slack.

Adding a new command
--------------------
1. Add a handler function here.
2. Wire it in cli.py (Typer command + renderer call).
3. Wire it in slack_bot.py (Bolt slash command + Slack block formatting).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, AsyncGenerator

if TYPE_CHECKING:
    from tinker.backends.base import Anomaly, LogEntry, MetricPoint, Trace
    from tinker.client.remote import RemoteClient


# ── Time parsing ──────────────────────────────────────────────────────────────


def parse_since(since: str) -> tuple[datetime, int]:
    """Parse a since string into ``(start_datetime, window_minutes)``.

    Supported units: ``m`` (minutes), ``h`` (hours), ``d`` (days).
    Examples: ``"30m"``, ``"2h"``, ``"1d"``
    """
    unit = since[-1]
    try:
        value = int(since[:-1])
    except ValueError:
        raise ValueError(f"Invalid since value '{since}' — expected e.g. '30m', '2h', '1d'")
    match unit:
        case "m":
            return datetime.now(timezone.utc) - timedelta(minutes=value), value
        case "h":
            return datetime.now(timezone.utc) - timedelta(hours=value), value * 60
        case "d":
            return datetime.now(timezone.utc) - timedelta(days=value), value * 1440
        case _:
            raise ValueError(f"Unknown time unit '{unit}' in '{since}' — use m/h/d")


# ── Logs ──────────────────────────────────────────────────────────────────────


async def get_logs(
    client: RemoteClient,
    service: str,
    query: str = "*",
    since: str = "30m",
    limit: int = 50,
    resource: str | None = None,
) -> list[LogEntry]:
    start, _ = parse_since(since)
    end = datetime.now(timezone.utc)
    return await client.query_logs(service, query, start, end, limit, resource_type=resource)


async def stream_logs(
    client: RemoteClient,
    service: str,
    query: str = "*",
    poll: float = 2.0,
    resource: str | None = None,
) -> AsyncGenerator[LogEntry, None]:
    async for entry in client.tail_logs(service, query, poll_interval=poll, resource_type=resource):
        yield entry


# ── Metrics ───────────────────────────────────────────────────────────────────


async def get_metrics(
    client: RemoteClient,
    service: str,
    metric: str,
    since: str = "1h",
    resource: str | None = None,
) -> list[MetricPoint]:
    start, _ = parse_since(since)
    end = datetime.now(timezone.utc)
    return await client.get_metrics(service, metric, start, end, resource_type=resource)


# ── Anomalies ─────────────────────────────────────────────────────────────────


async def get_anomalies(
    client: RemoteClient,
    service: str,
    since: str = "1h",
    severity: str | None = None,
    resource: str | None = None,
) -> list[Anomaly]:
    _, window = parse_since(since)
    anomalies = await client.detect_anomalies(service, window_minutes=window)
    if severity:
        anomalies = [a for a in anomalies if a.severity.lower() == severity.lower()]
    return anomalies


# ── Watches ───────────────────────────────────────────────────────────────────


async def start_watch(
    client: RemoteClient,
    service: str,
    notifier: str | None = None,
    destination: str | None = None,
    interval: int = 60,
) -> dict:
    return await client.create_watch(
        service=service,
        notifier=notifier,
        destination=destination,
        interval_seconds=interval,
    )


async def get_watches(client: RemoteClient) -> list[dict]:
    return await client.list_watches()


async def stop_watch(client: RemoteClient, watch_id: str) -> None:
    await client.stop_watch(watch_id)


async def delete_watch(client: RemoteClient, watch_id: str) -> None:
    await client.delete_watch(watch_id)


# ── Traces ────────────────────────────────────────────────────────────────────


async def get_traces(
    client: RemoteClient,
    service: str,
    since: str = "1h",
    limit: int = 20,
    tags: dict[str, str] | None = None,
) -> list[Trace]:
    return await client.get_traces(service, since=since, limit=limit, tags=tags)


# ── Diff (client-side comparison of two time windows) ────────────────────────


async def get_diff(
    client: RemoteClient,
    service: str,
    baseline: str = "2h",
    compare: str = "1h",
) -> dict:
    """Compare error count and anomaly severity between two windows.

    baseline — the reference window (older period, e.g. "2h" = 2 h ago to 1 h ago)
    compare  — the current window  (e.g. "1h" = last 1 h)
    """
    now = datetime.now(timezone.utc)

    def _window(since: str) -> tuple[datetime, datetime, int]:
        unit = since[-1]
        value = int(since[:-1])
        delta = {
            "m": timedelta(minutes=value),
            "h": timedelta(hours=value),
            "d": timedelta(days=value),
        }[unit]
        return now - delta, now, int(delta.total_seconds() / 60)

    compare_start, compare_end, compare_window = _window(compare)
    baseline_start, baseline_end, baseline_window = _window(baseline)
    # Shift baseline window to end at compare_start so windows don't overlap
    baseline_duration = baseline_end - baseline_start
    baseline_end = compare_start
    baseline_start = baseline_end - baseline_duration

    import asyncio as _asyncio

    (b_logs, c_logs, b_anomalies, c_anomalies) = await _asyncio.gather(
        client.query_logs(
            service, "level:ERROR OR level:CRITICAL", baseline_start, baseline_end, limit=1000
        ),
        client.query_logs(
            service, "level:ERROR OR level:CRITICAL", compare_start, compare_end, limit=1000
        ),
        client.detect_anomalies(service, window_minutes=baseline_window),
        client.detect_anomalies(service, window_minutes=compare_window),
    )

    def _sev_score(anomalies) -> int:
        scores = {"low": 1, "medium": 2, "high": 3, "critical": 4}
        return sum(scores.get(a.severity.lower(), 0) for a in anomalies)

    return {
        "service": service,
        "baseline": {
            "window": baseline,
            "start": baseline_start.isoformat(),
            "end": baseline_end.isoformat(),
            "error_count": len(b_logs),
            "anomaly_count": len(b_anomalies),
            "severity_score": _sev_score(b_anomalies),
        },
        "compare": {
            "window": compare,
            "start": compare_start.isoformat(),
            "end": compare_end.isoformat(),
            "error_count": len(c_logs),
            "anomaly_count": len(c_anomalies),
            "severity_score": _sev_score(c_anomalies),
        },
        "delta_errors": len(c_logs) - len(b_logs),
        "delta_anomalies": len(c_anomalies) - len(b_anomalies),
        "delta_severity": _sev_score(c_anomalies) - _sev_score(b_anomalies),
        "new_anomalies": [
            a.to_dict() for a in c_anomalies if not any(b.metric == a.metric for b in b_anomalies)
        ],
        "resolved_anomalies": [
            a.to_dict() for a in b_anomalies if not any(c.metric == a.metric for c in c_anomalies)
        ],
    }


# ── SLO ───────────────────────────────────────────────────────────────────────


async def get_slo(
    client: RemoteClient,
    service: str,
    target_pct: float = 99.9,
    window: str = "30d",
) -> dict:
    return await client.get_slo(service, target_pct=target_pct, window=window)


# ── Deploys ───────────────────────────────────────────────────────────────────


async def get_deploys(
    client: RemoteClient, service: str, since: str = "7d", limit: int = 10
) -> dict:
    return await client.get_deploys(service, since=since, limit=limit)


async def correlate_deploys(client: RemoteClient, service: str, since: str = "7d") -> dict:
    return await client.correlate_deploys(service, since=since)


# ── Alerts ────────────────────────────────────────────────────────────────────


async def create_alert(
    client: RemoteClient,
    service: str,
    metric: str,
    operator: str,
    threshold: float,
    severity: str = "medium",
    notifier: str | None = None,
    destination: str | None = None,
) -> dict:
    return await client.create_alert(
        service, metric, operator, threshold, severity, notifier, destination
    )


async def get_alerts(client: RemoteClient) -> list[dict]:
    return await client.list_alerts()


async def delete_alert(client: RemoteClient, alert_id: str) -> dict:
    return await client.delete_alert(alert_id)


async def mute_alert(client: RemoteClient, alert_id: str, duration: str = "1h") -> dict:
    return await client.mute_alert(alert_id, duration=duration)
