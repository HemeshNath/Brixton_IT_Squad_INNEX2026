"""FastAPI entry point.

Run (from backend/):  ..\\.venv\\Scripts\\uvicorn app.main:app --host 0.0.0.0 --port 8000
API docs:             http://localhost:8000/docs
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles


class AdminStatic(StaticFiles):
    """The built admin app. "no-cache": browsers ask every time whether a file changed (unchanged files get a quick
    304 Not Modified), so after an update nobody keeps seeing the old admin panel."""

    def file_response(self, *args, **kwargs):
        response = super().file_response(*args, **kwargs)
        response.headers["Cache-Control"] = "no-cache"
        return response

from .api.v1 import router as v1_router
from .config import Settings, get_settings
from .checks.domain_age import DomainAgeClient
from .checks.mira import MiraService
from .checks.otx import OtxClient
from .checks.known_scams import KnownScamMemory
from .checks.pipeline import Checkers
from .checks.scam_classifier import ScamClassifier
from .db import make_engine, make_sessionmaker
from .logging_setup import setup_logging
from .monitoring import ErrorMiddleware, ErrorRecorder
from . import ai_models, api_keys, data_lists, live_settings

setup_logging()  # every log line is passed through mask_pii (no personal data in logs)


def make_mira_service(settings: Settings, sessions=None) -> MiraService:
    """MIRA for the version chosen in the admin panel (Phase 10A), else the .env model."""
    version = None
    if sessions is not None:
        try:
            with sessions() as db:
                version = ai_models.chosen_version(db, settings)
        except Exception:  # noqa: BLE001 - table not migrated yet: use .env
            version = None
    service = ai_models.make_service(settings, version or ai_models.default_version(settings))
    if not settings.use_original_mira:
        service.enabled, service.status = False, "disabled"  # replaced by the trained model: never loaded
    return service


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.mira.start_loading(background=True)  # server answers at once; MIRA becomes ready later
        app.state.classifier.start_loading(background=True)  # the owner's trained model (if the folder exists)
        yield

    app = FastAPI(
        title=settings.app_name,
        version=settings.version,
        description="Checks SMS and links for scams (Nepal). All endpoints except /health need sign-in.",
        lifespan=lifespan,
    )
    app.state.settings = settings
    app.state.errors = ErrorRecorder()  # Phase 10A: server errors for the admin dashboard
    app.add_middleware(ErrorMiddleware, recorder=app.state.errors)
    app.state.engine = make_engine(settings.database_url)
    app.state.sessionmaker = make_sessionmaker(app.state.engine)
    app.state.mira = make_mira_service(settings, app.state.sessionmaker)  # Phase 6 / 10A: MIRA decision model
    sessions = app.state.sessionmaker
    app.state.classifier = ScamClassifier(settings.classifier_dir, timeout=settings.classifier_timeout_seconds)
    app.state.checkers = Checkers(  # Phase 8: everything one check may use (None = that part is skipped)
        otx=OtxClient(settings.otx_api_key, sessions, timeout=settings.otx_timeout_seconds,
                      daily_limit=settings.otx_daily_limit, cache_hours=settings.otx_cache_hours,
                      save_in_background=True)
        if settings.otx_api_key else None,
        ages=DomainAgeClient(sessions, timeout=settings.whois_timeout_seconds, cache_days=settings.domain_cache_days,
                             whois_api_key=settings.whois_api_key, save_in_background=True)
        if settings.whois_enabled else None,
        mira=app.state.mira,
        classifier=app.state.classifier,
        known=KnownScamMemory(sessions),  # Phase 10: approved scams, matched by letter patterns
        link_timeout=settings.link_checks_timeout_seconds,
    )
    live_settings.load_on_start(app)  # Phase 10A: admin panel settings (newest saved version)
    api_keys.apply(app)  # Phase 10A: OTX / WHOIS keys saved in the admin panel
    data_lists.apply(app)  # Phase 10A: official / trusted / blocked lists changed in the admin panel

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

    # Web admin panel (Phase 10A): the built Flutter Web app, served at /admin when it has been built.
    if (settings.admin_web_dir / "index.html").exists():
        @app.get("/admin", include_in_schema=False)
        def admin_root():
            return RedirectResponse("/admin/")

        app.mount("/admin", AdminStatic(directory=settings.admin_web_dir, html=True), name="admin")
    return app


app = create_app()
