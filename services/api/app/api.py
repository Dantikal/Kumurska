from fastapi import APIRouter

from app.modules.admin.router import router as admin_router
from app.modules.auth.router import router as auth_router
from app.modules.content.router import router as content_router
from app.modules.loyalty.router import router as loyalty_router
from app.modules.notifications.router import router as notifications_router
from app.modules.purchases.router import router as purchases_router
from app.modules.users.router import router as users_router

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(auth_router)
api_router.include_router(users_router)
api_router.include_router(loyalty_router)
api_router.include_router(purchases_router)
api_router.include_router(content_router)
api_router.include_router(notifications_router)
api_router.include_router(admin_router)
