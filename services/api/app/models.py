"""Импортирует модели всех модулей, чтобы Alembic видел таблицы."""

from app.modules.admin import models as admin_models
from app.modules.auth import models as auth_models
from app.modules.content import models as content_models
from app.modules.loyalty import models as loyalty_models
from app.modules.notifications import models as notifications_models
from app.modules.purchases import models as purchases_models
from app.modules.users import models as users_models

__all__ = [
    "auth_models",
    "users_models",
    "loyalty_models",
    "purchases_models",
    "content_models",
    "notifications_models",
    "admin_models",
]
