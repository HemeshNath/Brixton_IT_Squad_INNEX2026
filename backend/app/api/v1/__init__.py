"""Version 1 API router (/api/v1): collects every endpoint module into one router."""
from fastapi import APIRouter

from . import health, me

router = APIRouter()
router.include_router(health.router)
router.include_router(me.router)
