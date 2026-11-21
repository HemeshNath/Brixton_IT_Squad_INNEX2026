"""GET /api/v1/health – public status check: server up, app version, whether MIRA is loaded."""
from fastapi import APIRouter, Request
from pydantic import BaseModel

router = APIRouter(tags=["system"])


class HealthOut(BaseModel):
    status: str
    version: str
    mira_loaded: bool
    mira_status: str  # disabled | not_started | loading | ready | failed
    model_version: str | None


@router.get("/health", response_model=HealthOut)
def health(request: Request) -> HealthOut:
    """Public. Tells the app the server is up and whether MIRA is loaded."""
    mira = request.app.state.mira
    return HealthOut(
        status="ok",
        version=request.app.state.settings.version,
        mira_loaded=bool(mira and mira.ready),
        mira_status=mira.status if mira else "disabled",
        model_version=mira.version if mira else None,
    )
