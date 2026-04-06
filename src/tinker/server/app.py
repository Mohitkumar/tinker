"""Tinker Agent Server — FastAPI application factory."""

from __future__ import annotations

from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from tinker import __version__

log = structlog.get_logger(__name__)


@asynccontextmanager
async def _lifespan(app: FastAPI):
    from tinker.notifiers import NotifierRegistry
    from tinker.watches import WatchManager
    from tinker.server.routes.watches import set_manager
    from tinker import toml_config as tc
    from tinker.agent.llm import _init_langfuse

    # toml_config.get() calls _load_env_file_into_environ() which injects
    # ~/.tinker/.env into os.environ — Langfuse keys must be available before
    # _init_langfuse() checks for them.
    cfg = tc.get()
    _init_langfuse()
    notifiers = cfg.get_notifiers()
    if notifiers:
        registry.build_from_toml(notifiers)
        log.info("notifiers.loaded", count=len(registry))
    else:
        log.info("notifiers.none_configured — watches will fall back to legacy Slack settings")

    manager = WatchManager(registry=registry)
    set_manager(manager)
    await manager.start()
    yield
    await manager.stop()


def create_app() -> FastAPI:
    app = FastAPI(
        lifespan=_lifespan,
        title="Tinker Agent Server",
        description="AI-powered observability and incident response agent",
        version=__version__,
        docs_url="/docs",
        redoc_url=None,
    )

    # ── CORS (tighten origins for production) ─────────────────────────────────
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── Request logging ───────────────────────────────────────────────────────
    @app.middleware("http")
    async def log_requests(request: Request, call_next):
        response = await call_next(request)
        log.info(
            "http.request",
            method=request.method,
            path=request.url.path,
            status=response.status_code,
        )
        return response

    # ── Global error handler ──────────────────────────────────────────────────
    @app.exception_handler(Exception)
    async def unhandled_exception(request: Request, exc: Exception):
        log.exception("http.unhandled_error", path=request.url.path)
        return JSONResponse(status_code=500, content={"detail": "Internal server error"})

    # ── Routes ────────────────────────────────────────────────────────────────
    from tinker.server.routes.agent import router as agent_router
    from tinker.server.routes.mcp import router as mcp_router
    from tinker.server.routes.query import router as query_router
    from tinker.server.routes.watches import router as watches_router

    app.include_router(agent_router)
    app.include_router(query_router)
    app.include_router(mcp_router)
    app.include_router(watches_router)

    # ── Slack bot (mounted as ASGI sub-app) ───────────────────────────────────
    try:
        from tinker import toml_config as tc
        slack = tc.get().slack
        if not slack.bot_token or not slack.signing_secret:
            raise RuntimeError("slack.bot_token and slack.signing_secret must be set in config.toml [slack]")
        from tinker.interfaces.slack_bot import build_app as build_bolt_app
        from slack_bolt.adapter.fastapi.async_handler import AsyncSlackRequestHandler
        slack_handler = AsyncSlackRequestHandler(build_bolt_app())
        app.mount("/slack", slack_handler)
        log.info("slack.mounted")
    except Exception:
        log.warning("slack.not_configured")

    # ── Health ────────────────────────────────────────────────────────────────
    @app.get("/health", tags=["ops"])
    async def health():
        from tinker import toml_config as tc
        cfg = tc.get()
        active = cfg.active_profile or (next(iter(cfg.profiles)) if cfg.profiles else None)
        return {
            "status": "ok",
            "version": __version__,
            "active_profile": active,
            "profiles": {name: p.backend for name, p in cfg.profiles.items()},
        }

    return app


def main() -> None:
    import uvicorn
    from tinker import toml_config as tc

    toml = tc.get()
    host = toml.server.host
    port = toml.server.port
    log_level = toml.server.log_level

    uvicorn.run(
        "tinker.server.app:create_app",
        factory=True,
        host=host,
        port=port,
        log_level=log_level,
    )
