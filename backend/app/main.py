"""
The FastAPI application.

    /api/v1/...        the learner API (the public website)
    /api/v1/crm/...    the CRM API (the team's dashboard)
    /api/health        liveness: the process answers
    /api/ready         readiness: database, models and background jobs
    /api/docs          interactive API documentation (OpenAPI at /api/openapi.json)

Run it with one worker (``python -m app.cli serve`` or ``uvicorn app.main:app``): the background jobs run inside the
process, and two workers would run every job twice.
"""

from __future__ import annotations

import logging
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app import __version__, db
from app.api.crm import router as crm_router
from app.api.learner import router as learner_router
from app.core.config import get_settings
from app.core.errors import AppError
from app.core.logging import setup_logging

log = logging.getLogger("app")

SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Cache-Control": "no-store",
}


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    setup_logging(settings.log_level, settings.log_path)
    db.init_db()
    from app.services import team

    team.ensure_owner(settings.crm_owner_email, settings.crm_owner_name)
    if not settings.jwt_secret:
        log.info("JWT_SECRET is not set: using a random signing secret kept in the database")
    from app.jobs import scheduler

    scheduler.start()
    log.info(
        "X Education CRM %s ready (%s mode) on %s: website API /api/v1, CRM API /api/v1/crm, docs /api/docs",
        __version__,
        "demo" if settings.demo_mode else "live",
        settings.api_url,
    )
    try:
        yield
    finally:
        scheduler.stop()


def _first_error(exc: RequestValidationError) -> str:
    errors = exc.errors()
    if not errors:
        return "The request is not valid."
    e = errors[0]
    where = ".".join(str(p) for p in e.get("loc", []) if p not in ("body", "query", "path"))
    return f"{where}: {e.get('msg')}" if where else str(e.get("msg"))


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="X Education CRM API",
        version=__version__,
        lifespan=lifespan,
        docs_url="/api/docs",
        redoc_url=None,
        openapi_url="/api/openapi.json",
        description="The learner website's API (/api/v1) and the CRM team's API (/api/v1/crm).",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
        expose_headers=["X-Request-ID", "Content-Disposition"],
    )

    @app.middleware("http")
    async def request_context(request: Request, call_next):
        rid = request.headers.get("X-Request-ID") or uuid.uuid4().hex[:16]
        started = time.perf_counter()
        response = await call_next(request)
        ms = (time.perf_counter() - started) * 1000
        response.headers["X-Request-ID"] = rid
        for k, v in SECURITY_HEADERS.items():
            response.headers.setdefault(k, v)
        if response.status_code >= 500:
            log.error(
                "%s %s -> %d in %.0f ms (request %s)", request.method, request.url.path, response.status_code, ms, rid
            )
        elif ms > 2000:
            log.warning("Slow request: %s %s took %.0f ms (request %s)", request.method, request.url.path, ms, rid)
        return response

    @app.exception_handler(AppError)
    async def app_error(_: Request, exc: AppError):
        return JSONResponse({"detail": exc.message}, status_code=exc.status_code)

    @app.exception_handler(RequestValidationError)
    async def validation_error(_: Request, exc: RequestValidationError):
        return JSONResponse({"detail": _first_error(exc), "errors": exc.errors()}, status_code=422)

    @app.exception_handler(Exception)
    async def unexpected(request: Request, exc: Exception):
        log.exception("Unhandled error on %s %s", request.method, request.url.path)
        return JSONResponse({"detail": "Something went wrong on the server. The error was logged."}, status_code=500)

    @app.get("/api/health", tags=["Health"], summary="The process answers")
    def health():
        return {"status": "ok", "version": __version__, "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")}

    @app.get("/api/ready", tags=["Health"], summary="Database, models and background jobs")
    def ready():
        from app.jobs import scheduler
        from app.ml import nba
        from app.ml.predict import model_info

        checks = {"database": db.schema_version() is not None}
        info = model_info()
        checks["lead_model"] = bool(info.get("loaded"))
        checks["uplift_model"] = nba.model_version() != "prior"
        jobs = scheduler.jobs()
        checks["background_jobs"] = bool(jobs) or not settings.scheduler_enabled
        ok = all(checks.values())
        return JSONResponse(
            {
                "status": "ready" if ok else "not_ready",
                "checks": checks,
                "schema": db.schema_version(),
                "lead_model": info.get("version"),
                "uplift_model": nba.model_version(),
                "jobs": jobs,
            },
            status_code=200 if ok else 503,
        )

    app.include_router(learner_router, prefix="/api/v1")
    app.include_router(crm_router, prefix="/api/v1")
    return app


app = create_app()
