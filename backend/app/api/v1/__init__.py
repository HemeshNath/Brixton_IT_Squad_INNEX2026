"""Version 1 API router (/api/v1): collects every endpoint module into one router."""
from fastapi import APIRouter

from . import (admin, admin_ads, admin_dashboard, admin_data, admin_keys_models, admin_lab, admin_settings, admin_trends,
               admin_users, app_control, checks, health, me)

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
router.include_router(admin_trends.router)  # A8
router.include_router(admin_ads.admin_router)  # A9 (panel)
router.include_router(admin_ads.router)  # A9 (phone)
router.include_router(app_control.admin_router)  # A10 (panel)
router.include_router(app_control.router)  # A10 (phone)
