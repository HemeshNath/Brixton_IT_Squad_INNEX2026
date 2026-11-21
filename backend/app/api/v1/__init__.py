"""Version 1 API router (/api/v1): collects every endpoint module into one router."""
from fastapi import APIRouter

from . import checks, health, me

router = APIRouter()
router.include_router(health.router)
router.include_router(me.router)
router.include_router(checks.router)
