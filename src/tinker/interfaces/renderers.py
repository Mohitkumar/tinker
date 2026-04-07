"""Output renderers for CLI commands.

Three formats controlled by ``OutputFormat``:
  table      — Rich formatted table (default, human-readable)
  json       — single JSON array / object on stdout
  jsonlines  — one JSON object per line (streaming-friendly, pipeable to jq)

Usage
-----
    from tinker.interfaces.renderers import OutputFormat, render_anomalies

    render_anomalies(anomalies, OutputFormat.table, service="payments-api", since="1h")
    render_anomalies(anomalies, OutputFormat.jsonlines)

Adding a new render target
--------------------------
1. Add a ``render_<thing>(items, fmt, **ctx)`` function here.
2. Implement all three format branches (json / jsonlines / table).
3. Call it from the CLI command and the Slack command formatter.
"""

from __future__ import annotations

import json as _json
from enum import Enum
from typing import Any

from rich.console import Console
from rich.table import Table

from tinker.backends.base import Anomaly, LogEntry, MetricPoint, Trace

console = Console()

SEVERITY_COLORS: dict[str, str] = {
    "critical": "bold red",
    "high": "red",
    "medium": "yellow",
    "low": "green",
    "unknown": "white",
}

_LEVEL_STYLES: dict[str, str] = {
    "ERROR": "red",
    "CRITICAL": "bold red",
    "WARN": "yellow",
    "WARNING": "yellow",
    "INFO": "green",
    "DEBUG": "dim",
}


class OutputFormat(str, Enum):
    table = "table"
    json = "json"
    jsonlines = "jsonlines"


# ── Serialisers (shared between json + jsonlines) ─────────────────────────────

def _log_dict(e: LogEntry) -> dict[str, Any]:
    return {
        "timestamp": e.timestamp.isoformat(),
        "level": e.level,
        "service": e.service,
        "message": e.message,
        "trace_id": e.trace_id,
    }


def _metric_dict(p: MetricPoint) -> dict[str, Any]:
    return {
        "timestamp": p.timestamp.isoformat(),
        "value": p.value,
        "unit": p.unit,
    }


# ── Logs ──────────────────────────────────────────────────────────────────────

def render_logs(entries: list[LogEntry], fmt: OutputFormat) -> None:
    if fmt == OutputFormat.json:
        print(_json.dumps([_log_dict(e) for e in entries], default=str))
        return
    if fmt == OutputFormat.jsonlines:
        for e in entries:
            print(_json.dumps(_log_dict(e), default=str))
        return
    # table
    if not entries:
        console.print("[dim]No log entries found.[/dim]")
        return
    table = Table(show_header=True, header_style="bold magenta", show_lines=True)
    table.add_column("Timestamp", style="dim", width=20, no_wrap=True)
    table.add_column("Level", width=8, no_wrap=True)
    table.add_column("Message", overflow="fold")
    for e in entries:
        style = _LEVEL_STYLES.get(e.level.upper(), "white")
        table.add_row(
            e.timestamp.strftime("%Y-%m-%d %H:%M:%S"),
            f"[{style}]{e.level}[/{style}]",
            e.message,
        )
    console.print(table)


def render_log_entry(e: LogEntry, fmt: OutputFormat) -> None:
    """Render a single log entry — used for streaming tail."""
    if fmt in (OutputFormat.json, OutputFormat.jsonlines):
        print(_json.dumps(_log_dict(e), default=str))
        return
    style = _LEVEL_STYLES.get(e.level.upper(), "white")
    ts = e.timestamp.strftime("%H:%M:%S")
    console.print(f"[dim]{ts}[/dim]  [{style}]{e.level:<8}[/{style}]  {e.message}")


# ── Metrics ───────────────────────────────────────────────────────────────────

def render_metrics(points: list[MetricPoint], fmt: OutputFormat) -> None:
    if fmt == OutputFormat.json:
        print(_json.dumps([_metric_dict(p) for p in points], default=str))
        return
    if fmt == OutputFormat.jsonlines:
        for p in points:
            print(_json.dumps(_metric_dict(p), default=str))
        return
    if not points:
        console.print("[dim]No metric data found.[/dim]")
        return
    table = Table(show_header=True, header_style="bold magenta")
    table.add_column("Timestamp", style="dim")
    table.add_column("Value", justify="right")
    for p in points[-20:]:
        table.add_row(p.timestamp.strftime("%H:%M:%S"), f"{p.value:.4g}")
    console.print(table)


# ── Anomalies ─────────────────────────────────────────────────────────────────

def render_anomalies(
    anomalies: list[Anomaly],
    fmt: OutputFormat,
    service: str = "",
    since: str = "",
) -> None:
    if fmt == OutputFormat.json:
        print(_json.dumps([a.to_dict() for a in anomalies], indent=2, default=str))
        return
    if fmt == OutputFormat.jsonlines:
        for a in anomalies:
            print(_json.dumps(a.to_dict(), default=str))
        return
    if not anomalies:
        console.print(f"[dim]No anomalies detected for {service} in the last {since}.[/dim]")
        return
    table = Table(
        show_header=True,
        header_style="bold magenta",
        title=f"Anomalies — {service} (last {since})" if service else "Anomalies",
    )
    table.add_column("#", width=3, justify="right")
    table.add_column("Severity", width=9)
    table.add_column("Metric", width=20)
    table.add_column("Description")
    table.add_column("Patterns", width=8, justify="right")
    table.add_column("Traces", width=7, justify="right")
    for i, a in enumerate(anomalies, 1):
        sev_style = SEVERITY_COLORS.get(a.severity.lower(), "white")
        n_patterns = len((a.log_summary or {}).get("unique_patterns") or [])
        n_traces = len((a.log_summary or {}).get("stack_traces") or [])
        table.add_row(
            str(i),
            f"[{sev_style}]{a.severity.upper()}[/{sev_style}]",
            a.metric,
            a.description[:80],
            str(n_patterns) if n_patterns else "—",
            str(n_traces) if n_traces else "—",
        )
    console.print(table)
    if service:
        console.print(
            f"[dim]Run [bold]tinker investigate {service}[/bold] to explain and fix anomalies.[/dim]"
        )


# ── Watches ───────────────────────────────────────────────────────────────────

def render_watches(watches: list[dict], fmt: OutputFormat) -> None:
    if fmt == OutputFormat.json:
        print(_json.dumps(watches, indent=2, default=str))
        return
    if fmt == OutputFormat.jsonlines:
        for w in watches:
            print(_json.dumps(w, default=str))
        return
    if not watches:
        console.print("[dim]No watches on the server.[/dim]")
        return
    table = Table(show_header=True, header_style="bold magenta", title="Server Watches")
    table.add_column("ID", width=16)
    table.add_column("Service", width=20)
    table.add_column("Status", width=9)
    table.add_column("Notifier", width=12)
    table.add_column("Destination", width=16)
    table.add_column("Interval", width=10)
    table.add_column("Last Run")
    for w in watches:
        status = w.get("status", "?")
        scolor = "green" if status == "running" else "dim"
        table.add_row(
            w.get("watch_id", "?"),
            w.get("service", "?"),
            f"[{scolor}]{status}[/{scolor}]",
            w.get("notifier") or "—",
            w.get("destination") or "—",
            f"{w.get('interval_seconds', '?')}s",
            (w.get("last_run_at") or "never")[:19],
        )
    console.print(table)


# ── Traces ────────────────────────────────────────────────────────────────────

def render_traces(traces: list[Trace], fmt: OutputFormat, service: str = "") -> None:
    if fmt == OutputFormat.json:
        print(_json.dumps([t.to_dict() for t in traces], indent=2, default=str))
        return
    if fmt == OutputFormat.jsonlines:
        for t in traces:
            print(_json.dumps(t.to_dict(), default=str))
        return
    if not traces:
        console.print(f"[dim]No traces found{f' for {service}' if service else ''}.[/dim]")
        return
    table = Table(
        show_header=True, header_style="bold magenta",
        title=f"Traces — {service}" if service else "Traces",
        show_lines=True,
    )
    table.add_column("Trace ID", width=12, no_wrap=True)
    table.add_column("Operation", ratio=1, overflow="fold")
    table.add_column("Duration", width=10, justify="right", no_wrap=True)
    table.add_column("Spans", width=6, justify="right", no_wrap=True)
    table.add_column("Status", width=7, no_wrap=True)
    table.add_column("Started", width=10, no_wrap=True)
    for t in traces:
        status_style = "red" if t.status == "error" else "green"
        table.add_row(
            t.trace_id[:12],
            t.operation_name,
            f"{t.duration_ms:.0f}ms",
            str(t.span_count),
            f"[{status_style}]{t.status}[/{status_style}]",
            t.start_time.strftime("%H:%M:%S"),
        )
    console.print(table)
    console.print("[dim]Tip: check your tracing backend (Tempo / X-Ray / Cloud Trace) for the full waterfall.[/dim]")


# ── Diff ──────────────────────────────────────────────────────────────────────

def render_diff(diff: dict, fmt: OutputFormat) -> None:
    if fmt == OutputFormat.json:
        print(_json.dumps(diff, indent=2, default=str))
        return
    if fmt == OutputFormat.jsonlines:
        print(_json.dumps(diff, default=str))
        return

    baseline = diff.get("baseline", {})
    compare = diff.get("compare", {})
    delta_errors = diff.get("delta_errors", 0)
    delta_anomalies = diff.get("delta_anomalies", 0)
    delta_sev = diff.get("delta_severity", 0)

    def _arrow(n: int) -> str:
        if n > 0:
            return f"[red]▲ +{n}[/red]"
        if n < 0:
            return f"[green]▼ {n}[/green]"
        return "[dim]═  0[/dim]"

    table = Table(
        show_header=True, header_style="bold magenta",
        title=f"Window Diff — {diff.get('service', '')}", show_lines=True,
    )
    table.add_column("Metric", width=20)
    table.add_column(f"Baseline ({baseline.get('window', '?')})", justify="right", width=20)
    table.add_column(f"Now ({compare.get('window', '?')})", justify="right", width=16)
    table.add_column("Delta", justify="right", width=12)
    table.add_row("Error count",    str(baseline.get("error_count", 0)),    str(compare.get("error_count", 0)),    _arrow(delta_errors))
    table.add_row("Anomaly count",  str(baseline.get("anomaly_count", 0)),  str(compare.get("anomaly_count", 0)),  _arrow(delta_anomalies))
    table.add_row("Severity score", str(baseline.get("severity_score", 0)), str(compare.get("severity_score", 0)), _arrow(delta_sev))
    console.print(table)

    new_anomalies = diff.get("new_anomalies", [])
    resolved = diff.get("resolved_anomalies", [])
    if new_anomalies:
        console.print(f"\n[red bold]New anomalies ({len(new_anomalies)}):[/red bold]")
        for a in new_anomalies:
            console.print(f"  [red]•[/red] [{SEVERITY_COLORS.get(a.get('severity','').lower(),'white')}]{a.get('severity','?').upper()}[/] {a.get('metric','?')} — {a.get('description','')[:80]}")
    if resolved:
        console.print(f"\n[green bold]Resolved ({len(resolved)}):[/green bold]")
        for a in resolved:
            console.print(f"  [green]✓[/green] {a.get('metric','?')} — {a.get('description','')[:80]}")
    if not new_anomalies and not resolved:
        console.print("\n[dim]No new or resolved anomalies between windows.[/dim]")


# ── SLO ───────────────────────────────────────────────────────────────────────

def render_slo(slo: dict, fmt: OutputFormat) -> None:
    if fmt == OutputFormat.json:
        print(_json.dumps(slo, indent=2, default=str))
        return
    if fmt == OutputFormat.jsonlines:
        print(_json.dumps(slo, default=str))
        return

    status = slo.get("status", "unknown")
    avail = slo.get("availability_pct", 0.0)
    target = slo.get("target_pct", 99.9)
    budget_rem = slo.get("budget_remaining_pct", 0.0)
    burn_rate = slo.get("burn_rate", 0.0)

    status_style = "green" if status == "ok" else "bold red"
    status_label = "✓ MEETING SLO" if status == "ok" else "✗ SLO BREACH"

    table = Table(
        show_header=False, show_lines=True,
        title=f"SLO — {slo.get('service', '')} (window: {slo.get('window', '?')})",
    )
    table.add_column("Metric", width=22, style="bold")
    table.add_column("Value")
    table.add_row("Status",           f"[{status_style}]{status_label}[/{status_style}]")
    table.add_row("Availability",     f"{avail:.4f}%  (target: {target}%)")
    table.add_row("Total requests",   str(slo.get("total_requests", 0)))
    table.add_row("Error count",      str(slo.get("error_count", 0)))
    table.add_row("Error budget used", f"{slo.get('budget_used', 0)} / {slo.get('budget_total', 0):.0f} requests")
    table.add_row("Budget remaining", f"{budget_rem:.1f}%")
    burn_style = "bold red" if burn_rate > 2 else "yellow" if burn_rate > 1 else "green"
    table.add_row("Burn rate", f"[{burn_style}]{burn_rate:.2f}×[/{burn_style}]  (>1 = consuming budget faster than sustainable)")
    console.print(table)


# ── Deploys ───────────────────────────────────────────────────────────────────

def render_deploys(data: dict, fmt: OutputFormat, correlate: bool = False) -> None:
    deploys = data.get("deploys", [])
    if fmt == OutputFormat.json:
        print(_json.dumps(data, indent=2, default=str))
        return
    if fmt == OutputFormat.jsonlines:
        for d in deploys:
            print(_json.dumps(d, default=str))
        return
    if not deploys:
        console.print(f"[dim]No deploys found for {data.get('service', '?')} in {data.get('since', '?')}.[/dim]")
        return

    title = f"Deploys — {data.get('service', '')} ({data.get('since', '?')})"
    if correlate:
        title += f"  |  {data.get('total_anomalies', 0)} anomaly(ies) in window"

    table = Table(show_header=True, header_style="bold magenta", title=title, show_lines=True)
    table.add_column("SHA", width=9, no_wrap=True)
    table.add_column("Message", ratio=1, overflow="fold")
    table.add_column("Author", width=16, no_wrap=True)
    table.add_column("Time", width=20, no_wrap=True)
    if correlate:
        table.add_column("Nearby Anomalies", overflow="fold")

    for d in deploys:
        sha     = d.get("sha", "?")
        msg     = d.get("message", "")
        author  = (d.get("author") or "?")[:15]
        ts      = (d.get("timestamp") or "")[:19].replace("T", " ")
        nearby  = d.get("anomalies_nearby", [])
        if correlate:
            nearby_str = ("\n".join(f"• {n}" for n in nearby[:3])) if nearby else "[dim]none[/dim]"
            sha_style  = "red bold" if nearby else "white"
            table.add_row(f"[{sha_style}]{sha}[/{sha_style}]", msg, author, ts, nearby_str)
        else:
            table.add_row(sha, msg, author, ts)
    console.print(table)


# ── Alerts ────────────────────────────────────────────────────────────────────

def render_alerts(alerts: list[dict], fmt: OutputFormat) -> None:
    if fmt == OutputFormat.json:
        print(_json.dumps(alerts, indent=2, default=str))
        return
    if fmt == OutputFormat.jsonlines:
        for a in alerts:
            print(_json.dumps(a, default=str))
        return
    if not alerts:
        console.print("[dim]No alert rules configured.[/dim]")
        return
    table = Table(show_header=True, header_style="bold magenta", title="Alert Rules")
    table.add_column("ID", width=14)
    table.add_column("Service", width=18)
    table.add_column("Metric", width=18)
    table.add_column("Condition", width=14)
    table.add_column("Severity", width=9)
    table.add_column("Notifier", width=12)
    table.add_column("Muted Until", width=20)
    for a in alerts:
        sev = a.get("severity", "medium")
        sev_style = SEVERITY_COLORS.get(sev.lower(), "white")
        op_symbols = {"gt": ">", "lt": "<", "gte": "≥", "lte": "≤"}
        op = op_symbols.get(a.get("operator", ""), a.get("operator", "?"))
        muted = (a.get("muted_until") or "—")[:19]
        table.add_row(
            a.get("alert_id", "?"),
            a.get("service", "?"),
            a.get("metric", "?"),
            f"{op} {a.get('threshold', '?')}",
            f"[{sev_style}]{sev.upper()}[/{sev_style}]",
            a.get("notifier") or "—",
            muted,
        )
    console.print(table)
