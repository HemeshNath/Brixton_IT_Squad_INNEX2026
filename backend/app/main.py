"""FastAPI entry point.

Run (from backend/):  ..\\.venv\\Scripts\\uvicorn app.main:app --host 0.0.0.0 --port 8000
API docs:             http://localhost:8000/docs
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api.v1 import router as v1_router
from .config import Settings, get_settings
from .db import make_engine, make_sessionmaker
from .logging_setup import setup_logging

setup_logging()  # every log line is passed through mask_pii (no personal data in logs)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    app = FastAPI(
        title=settings.app_name,
        version=settings.version,
        description="Checks SMS and links for scams (Nepal). All endpoints except /health need sign-in.",
    )
    app.state.settings = settings
    app.state.engine = make_engine(settings.database_url)
    app.state.sessionmaker = make_sessionmaker(app.state.engine)
    app.state.mira = None  # loaded at startup in Phase 4

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
