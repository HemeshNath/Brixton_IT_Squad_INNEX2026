"""FastAPI entry point.

Run (from backend/):  ..\\.venv\\Scripts\\uvicorn app.main:app --host 0.0.0.0 --port 8000
API docs:             http://localhost:8000/docs
"""
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .api.v1 import router as v1_router
from .config import Settings, get_settings
from .checks.domain_age import DomainAgeClient
from .checks.mira import MiraModel, MiraService
from .checks.otx import OtxClient
from .checks.pipeline import Checkers
from .db import make_engine, make_sessionmaker
from .logging_setup import setup_logging

setup_logging()  # every log line is passed through mask_pii (no personal data in logs)


def make_mira_service(settings: Settings) -> MiraService:
    cache_dir = os.path.join(settings.hf_home, "hub") if settings.hf_home else None

    def loader() -> MiraModel:
        return MiraModel.load(settings.mira_model_id, settings.mira_revision, cache_dir=cache_dir,
                              local_only=settings.mira_local_only, not_sure_below=settings.mira_not_sure_below)

    return MiraService(loader, timeout=settings.mira_timeout_seconds, enabled=settings.mira_enabled)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.mira.start_loading(background=True)  # server answers at once; MIRA becomes ready later
        yield

    app = FastAPI(
        title=settings.app_name,
        version=settings.version,
        description="Checks SMS and links for scams (Nepal). All endpoints except /health need sign-in.",
        lifespan=lifespan,
    )
    app.state.settings = settings
    app.state.engine = make_engine(settings.database_url)
    app.state.sessionmaker = make_sessionmaker(app.state.engine)
    app.state.mira = make_mira_service(settings)  # Phase 6: MIRA v1 decision model
    sessions = app.state.sessionmaker
    app.state.checkers = Checkers(  # Phase 8: everything one check may use (None = that part is skipped)
        otx=OtxClient(settings.otx_api_key, sessions, timeout=settings.otx_timeout_seconds,
                      daily_limit=settings.otx_daily_limit, cache_hours=settings.otx_cache_hours)
        if settings.otx_api_key else None,
        ages=DomainAgeClient(sessions, timeout=settings.whois_timeout_seconds, cache_days=settings.domain_cache_days)
        if settings.whois_enabled else None,
        mira=app.state.mira,
        link_timeout=settings.link_checks_timeout_seconds,
    )

    @app.exception_handler(RequestValidationError)
    async def bad_input(request: Request, exc: RequestValidationError):
        """Invalid input -> 400 with a short readable message (the app shows `detail`)."""
        first = exc.errors()[0] if exc.errors() else {}
        field = ".".join(str(x) for x in first.get("loc", [])[1:]) or "input"
        return JSONResponse(status_code=400, content={"detail": f"Invalid {field}: {first.get('msg', 'bad value')}"})

    if settings.cors_origin_list:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origin_list,
            allow_methods=["GET", "POST", "DELETE"],
            allow_headers=["Authorization", "Content-Type"],
        )

    app.include_router(v1_router, prefix="/api/v1")
    return app


app = create_app()
