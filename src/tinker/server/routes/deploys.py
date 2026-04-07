"""Deploy tracking routes.

GET  /api/v1/deploys/{service}           — list recent commits/releases for a service
GET  /api/v1/deploys/{service}/correlate — cross-correlate deploys with anomaly timeline
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Annotated, Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query

from tinker.server.auth import AuthContext, require_auth

log = structlog.get_logger(__name__)
router = APIRouter(prefix="/api/v1/deploys", tags=["deploys"])


def _github_client():
    """Return a configured PyGithub client, or raise HTTPException if not configured."""
    try:
        from tinker import toml_config as tc
        cfg = tc.get()
        github_cfg = getattr(cfg, "github", None)
        token = getattr(github_cfg, "token", None) if github_cfg else None
        repo_name = getattr(github_cfg, "repo", None) if github_cfg else None
        if not token or not repo_name:
            raise HTTPException(
                status_code=503,
                detail="GitHub not configured — set github.token and github.repo in config.toml",
            )
        from github import Github
        return Github(token), repo_name
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"GitHub init error: {exc}")


@router.get("/{service}")
async def list_deploys(
    service: str,
    auth: Annotated[AuthContext, Depends(require_auth)],
    limit: int = Query(default=10, le=50),
    since: str = Query(default="7d"),
) -> dict[str, Any]:
    """List recent commits (as a proxy for deploys) for the service."""
    gh, repo_name = _github_client()

    unit = since[-1]
    value = int(since[:-1])
    delta = {"d": timedelta(days=value), "h": timedelta(hours=value), "m": timedelta(minutes=value)}.get(unit)
    if not delta:
        raise HTTPException(status_code=422, detail=f"Unknown since unit '{unit}'")
    since_dt = datetime.now(timezone.utc) - delta

    try:
        repo = gh.get_repo(repo_name)
        # Try service-specific path first, fall back to whole repo
        try:
            commits = list(repo.get_commits(path=service, since=since_dt)[:limit])
        except Exception:
            commits = list(repo.get_commits(since=since_dt)[:limit])

        deploys = [
            {
                "sha": c.sha[:8],
                "full_sha": c.sha,
                "message": c.commit.message.splitlines()[0][:120],
                "author": c.commit.author.name if c.commit.author else "unknown",
                "timestamp": c.commit.author.date.isoformat() if c.commit.author else "",
                "url": c.html_url,
            }
            for c in commits
        ]
    except HTTPException:
        raise
    except Exception as exc:
        log.error("deploys.list.error", service=service, error=str(exc))
        raise HTTPException(status_code=502, detail=f"GitHub error: {exc}")

    log.info("deploys.listed", service=service, count=len(deploys))
    return {"service": service, "since": since, "deploys": deploys}


@router.get("/{service}/correlate")
async def correlate_deploys(
    service: str,
    auth: Annotated[AuthContext, Depends(require_auth)],
    since: str = Query(default="7d"),
    window_minutes: int = Query(default=30),
) -> dict[str, Any]:
    """Cross-correlate recent deploys with anomaly spikes."""
    from tinker.backends import get_backend_for_service
    from tinker.backends.base import ServiceNotFoundError

    gh, repo_name = _github_client()

    unit = since[-1]
    value = int(since[:-1])
    delta = {"d": timedelta(days=value), "h": timedelta(hours=value), "m": timedelta(minutes=value)}.get(unit)
    if not delta:
        raise HTTPException(status_code=422, detail=f"Unknown since unit '{unit}'")
    since_dt = datetime.now(timezone.utc) - delta

    # Fetch deploys
    try:
        repo = gh.get_repo(repo_name)
        try:
            commits = list(repo.get_commits(path=service, since=since_dt)[:20])
        except Exception:
            commits = list(repo.get_commits(since=since_dt)[:20])
        deploys = [
            {
                "sha": c.sha[:8],
                "message": c.commit.message.splitlines()[0][:120],
                "author": c.commit.author.name if c.commit.author else "unknown",
                "timestamp": c.commit.author.date.isoformat() if c.commit.author else "",
            }
            for c in commits
        ]
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"GitHub error: {exc}")

    # Fetch anomalies for the same window
    try:
        backend = get_backend_for_service(service)
        anomalies = await backend.detect_anomalies(service, window_minutes=window_minutes)
        anomaly_list = [a.to_dict() for a in anomalies]
    except ServiceNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        log.warning("deploys.correlate.anomaly_error", service=service, error=str(exc))
        anomaly_list = []

    # Tag each deploy with whether anomalies exist near it (within 30 min)
    correlated = []
    for d in deploys:
        ts_str = d.get("timestamp", "")
        try:
            deploy_ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            deploy_ts = None

        nearby_anomalies = []
        if deploy_ts:
            for a in anomaly_list:
                try:
                    a_ts = datetime.fromisoformat(a["detected_at"].replace("Z", "+00:00"))
                    if abs((a_ts - deploy_ts).total_seconds()) <= 1800:
                        nearby_anomalies.append(a["description"][:80])
                except Exception:
                    pass

        correlated.append({**d, "anomalies_nearby": nearby_anomalies})

    log.info("deploys.correlated", service=service, deploys=len(deploys), anomalies=len(anomaly_list))
    return {
        "service": service,
        "since": since,
        "total_anomalies": len(anomaly_list),
        "deploys": correlated,
    }
