"""Raw observability query endpoints — used by the CLI in server mode.

POST /api/v1/logs        — query log entries
POST /api/v1/metrics     — get metric time series
POST /api/v1/anomalies   — detect anomalies
POST /api/v1/traces      — fetch distributed traces
POST /api/v1/slo         — compute SLO / error budget from logs
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any

import structlog
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from tinker.backends import get_backend_for_service
from tinker.backends.base import ServiceNotFoundError
from tinker.server.auth import AuthContext, require_auth

log = structlog.get_logger(__name__)
router = APIRouter(prefix="/api/v1", tags=["query"])


# ── Request models ────────────────────────────────────────────────────────────

class LogsRequest(BaseModel):
    service: str
    query: str = "*"
    start: datetime
    end: datetime
    limit: int = 100
    resource_type: str | None = None


class MetricsRequest(BaseModel):
    service: str
    metric: str
    start: datetime
    end: datetime


class AnomaliesRequest(BaseModel):
    service: str
    window_minutes: int = 10


class TracesRequest(BaseModel):
    service: str
    since: str = "1h"
    limit: int = 20
    tags: dict[str, str] | None = None


class SLORequest(BaseModel):
    service: str
    target_pct: float = 99.9
    window: str = "30d"


# ── Routes ────────────────────────────────────────────────────────────────────

@router.post("/logs")
async def query_logs(
    req: LogsRequest,
    auth: Annotated[AuthContext, Depends(require_auth)],
) -> dict[str, Any]:
    backend = get_backend_for_service(req.service)
    try:
        entries = await backend.query_logs(req.service, req.query, req.start, req.end, req.limit, req.resource_type)
    except ServiceNotFoundError as exc:
        log.warning("query.logs.service_not_found", service=req.service)
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        log.error("query.logs.error", service=req.service, error=str(exc))
        raise HTTPException(status_code=502, detail=f"Backend error: {exc}")
    log.debug("query.logs", service=req.service, count=len(entries), actor=auth.subject)
    return {
        "entries": [
            {
                "timestamp": e.timestamp.isoformat(),
                "level": e.level,
                "message": e.message,
                "service": e.service,
                "trace_id": e.trace_id,
                "span_id": e.span_id,
                "extra": e.extra,
            }
            for e in entries
        ]
    }


@router.post("/metrics")
async def get_metrics(
    req: MetricsRequest,
    auth: Annotated[AuthContext, Depends(require_auth)],
) -> dict[str, Any]:
    backend = get_backend_for_service(req.service)
    try:
        points = await backend.get_metrics(req.service, req.metric, req.start, req.end)
    except ServiceNotFoundError as exc:
        log.warning("query.metrics.service_not_found", service=req.service)
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        log.error("query.metrics.error", service=req.service, metric=req.metric, error=str(exc))
        raise HTTPException(status_code=502, detail=f"Backend error: {exc}")
    log.debug("query.metrics", service=req.service, metric=req.metric, count=len(points))
    return {
        "points": [
            {
                "timestamp": p.timestamp.isoformat(),
                "value": p.value,
                "unit": p.unit,
                "dimensions": p.dimensions,
            }
            for p in points
        ]
    }


@router.post("/anomalies")
async def detect_anomalies(
    req: AnomaliesRequest,
    auth: Annotated[AuthContext, Depends(require_auth)],
) -> dict[str, Any]:
    backend = get_backend_for_service(req.service)
    try:
        anomalies = await backend.detect_anomalies(req.service, req.window_minutes)
    except ServiceNotFoundError as exc:
        log.warning("query.anomalies.service_not_found", service=req.service)
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        log.error("query.anomalies.error", service=req.service, error=str(exc))
        raise HTTPException(status_code=502, detail=f"Backend error: {exc}")
    log.debug("query.anomalies", service=req.service, count=len(anomalies))
    return {
        "anomalies": [a.to_dict() for a in anomalies]
    }


@router.post("/traces")
async def get_traces(
    req: TracesRequest,
    auth: Annotated[AuthContext, Depends(require_auth)],
) -> dict[str, Any]:
    backend = get_backend_for_service(req.service)
    try:
        traces = await backend.get_traces(req.service, since=req.since, limit=req.limit, tags=req.tags)
    except ServiceNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        log.error("query.traces.error", service=req.service, error=str(exc))
        raise HTTPException(status_code=502, detail=f"Backend error: {exc}")
    log.debug("query.traces", service=req.service, count=len(traces))
    return {"traces": [t.to_dict() for t in traces]}


@router.post("/slo")
async def compute_slo(
    req: SLORequest,
    auth: Annotated[AuthContext, Depends(require_auth)],
) -> dict[str, Any]:
    """Compute SLO availability and error budget from log-based error rate."""
    from datetime import timedelta
    backend = get_backend_for_service(req.service)

    # Parse window (supports d/h/m)
    unit = req.window[-1]
    value = int(req.window[:-1])
    delta = {"d": timedelta(days=value), "h": timedelta(hours=value), "m": timedelta(minutes=value)}.get(unit)
    if delta is None:
        raise HTTPException(status_code=422, detail=f"Unknown window unit '{unit}' — use d/h/m")

    from datetime import timezone
    end = datetime.now(timezone.utc)
    start = end - delta

    try:
        all_logs = await backend.query_logs(req.service, "*", start, end, limit=5000)
        error_logs = [e for e in all_logs if e.is_error()]
    except ServiceNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        log.error("query.slo.error", service=req.service, error=str(exc))
        raise HTTPException(status_code=502, detail=f"Backend error: {exc}")

    total = len(all_logs)
    errors = len(error_logs)
    availability = ((total - errors) / total * 100) if total > 0 else 100.0
    budget_total = (100 - req.target_pct) / 100 * total   # allowed error requests
    budget_used = errors
    budget_remaining_pct = max(0.0, (budget_total - budget_used) / budget_total * 100) if budget_total > 0 else 100.0

    # Burn rate: how many times faster than "sustainable" we're consuming the budget
    # Sustainable = consume 100% of budget over the full window
    window_hours = delta.total_seconds() / 3600
    burn_rate = (errors / budget_total) if budget_total > 0 else 0.0

    log.debug("query.slo", service=req.service, availability=availability, burn_rate=burn_rate)
    return {
        "service": req.service,
        "window": req.window,
        "target_pct": req.target_pct,
        "availability_pct": round(availability, 4),
        "total_requests": total,
        "error_count": errors,
        "budget_total": round(budget_total, 1),
        "budget_used": budget_used,
        "budget_remaining_pct": round(budget_remaining_pct, 1),
        "burn_rate": round(burn_rate, 2),
        "status": "ok" if availability >= req.target_pct else "breach",
    }
