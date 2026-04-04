"""Raw observability query endpoints — used by the CLI in server mode.

POST /api/v1/logs        — query log entries
POST /api/v1/metrics     — get metric time series
POST /api/v1/anomalies   — detect anomalies
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any

import structlog
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from tinker.backends import get_backend
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


class MetricsRequest(BaseModel):
    service: str
    metric: str
    start: datetime
    end: datetime


class AnomaliesRequest(BaseModel):
    service: str
    window_minutes: int = 10


# ── Routes ────────────────────────────────────────────────────────────────────

@router.post("/logs")
async def query_logs(
    req: LogsRequest,
    auth: Annotated[AuthContext, Depends(require_auth)],
) -> dict[str, Any]:
    backend = get_backend()
    entries = await backend.query_logs(req.service, req.query, req.start, req.end, req.limit)
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
    backend = get_backend()
    points = await backend.get_metrics(req.service, req.metric, req.start, req.end)
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
    backend = get_backend()
    anomalies = await backend.detect_anomalies(req.service, req.window_minutes)
    log.debug("query.anomalies", service=req.service, count=len(anomalies))
    return {
        "anomalies": [a.to_dict() for a in anomalies]
    }
