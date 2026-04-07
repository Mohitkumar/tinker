"""Alert rule management routes.

POST   /api/v1/alerts              — create an alert rule
GET    /api/v1/alerts              — list all alert rules
DELETE /api/v1/alerts/{alert_id}   — delete an alert rule
POST   /api/v1/alerts/{alert_id}/mute — mute an alert for a duration

Alert rules are threshold-based; they are evaluated during the watch loop
when detect_anomalies() runs. If a metric value (current_value) in any
returned anomaly crosses the rule's threshold, the configured notifier fires.
"""

from __future__ import annotations

from typing import Annotated, Any

import structlog
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from tinker.server.auth import AuthContext, require_auth
from tinker.store.db import TinkerDB

log = structlog.get_logger(__name__)
router = APIRouter(prefix="/api/v1/alerts", tags=["alerts"])

_VALID_OPERATORS = {"gt", "lt", "gte", "lte"}
_VALID_SEVERITIES = {"low", "medium", "high", "critical"}


class CreateAlertRequest(BaseModel):
    service: str
    metric: str
    operator: str           # gt | lt | gte | lte
    threshold: float
    severity: str = "medium"
    notifier: str | None = None
    destination: str | None = None


class MuteRequest(BaseModel):
    duration: str = "1h"    # e.g. 30m, 2h, 1d


@router.post("", status_code=201)
async def create_alert(
    req: CreateAlertRequest,
    auth: Annotated[AuthContext, Depends(require_auth)],
) -> dict[str, Any]:
    if req.operator not in _VALID_OPERATORS:
        raise HTTPException(status_code=422, detail=f"operator must be one of {_VALID_OPERATORS}")
    if req.severity not in _VALID_SEVERITIES:
        raise HTTPException(status_code=422, detail=f"severity must be one of {_VALID_SEVERITIES}")
    db = TinkerDB()
    try:
        rule = db.create_alert(
            service=req.service,
            metric=req.metric,
            operator=req.operator,
            threshold=req.threshold,
            severity=req.severity,
            notifier=req.notifier,
            destination=req.destination,
        )
    finally:
        db.close()
    log.info("alert.created", alert_id=rule["alert_id"], service=req.service, actor=auth.subject)
    return rule


@router.get("")
async def list_alerts(
    auth: Annotated[AuthContext, Depends(require_auth)],
) -> dict[str, Any]:
    db = TinkerDB()
    try:
        rules = db.list_alerts()
    finally:
        db.close()
    return {"alerts": rules}


@router.delete("/{alert_id}")
async def delete_alert(
    alert_id: str,
    auth: Annotated[AuthContext, Depends(require_auth)],
) -> dict[str, Any]:
    db = TinkerDB()
    try:
        ok = db.delete_alert(alert_id)
    finally:
        db.close()
    if not ok:
        raise HTTPException(status_code=404, detail=f"Alert {alert_id!r} not found")
    log.info("alert.deleted", alert_id=alert_id, actor=auth.subject)
    return {"status": "deleted", "alert_id": alert_id}


@router.post("/{alert_id}/mute")
async def mute_alert(
    alert_id: str,
    req: MuteRequest,
    auth: Annotated[AuthContext, Depends(require_auth)],
) -> dict[str, Any]:
    from datetime import timedelta, datetime, timezone
    unit = req.duration[-1]
    value = int(req.duration[:-1])
    delta = {"m": timedelta(minutes=value), "h": timedelta(hours=value), "d": timedelta(days=value)}.get(unit)
    if not delta:
        raise HTTPException(status_code=422, detail=f"Unknown duration unit '{unit}' — use m/h/d")
    muted_until = (datetime.now(timezone.utc) + delta).isoformat()

    db = TinkerDB()
    try:
        ok = db.mute_alert(alert_id, muted_until)
    finally:
        db.close()
    if not ok:
        raise HTTPException(status_code=404, detail=f"Alert {alert_id!r} not found")
    log.info("alert.muted", alert_id=alert_id, until=muted_until, actor=auth.subject)
    return {"status": "muted", "alert_id": alert_id, "muted_until": muted_until}
