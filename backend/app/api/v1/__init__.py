"""Version 1 API router (/api/v1): collects every endpoint module into one router."""
from fastapi import APIRouter

from . import (admin, admin_dashboard, admin_data, admin_keys_models, admin_lab, admin_settings, admin_users, checks,
               health, me)

router = APIRouter()
router.include_router(health.router)
router.include_router(me.router)
router.include_router(checks.router)
router.include_router(admin.router)
router.include_router(admin_dashboard.router)
router.include_router(admin_users.router)
router.include_router(admin_settings.router)
router.include_router(admin_keys_models.router)
router.include_router(admin_data.router)
router.include_router(admin_lab.router)
