# handlers/__init__.py
from .common import router as common_router
from .user import router as user_router
from .payment import router as payment_router
from .admin import router as admin_router

__all__ = [
    'common_router',
    'user_router',
    'payment_router',
    'admin_router'
]