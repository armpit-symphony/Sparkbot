from fastapi import APIRouter

from app.api.routes import items, login, private, users, utils
from app.api.routes.chat import messages_router, rooms_router, users_router, ws_router, bot_integration_router
from app.core.config import settings

api_router = APIRouter()
api_router.include_router(login.router)
api_router.include_router(users.router)
api_router.include_router(users_router, prefix="/chat")
api_router.include_router(rooms_router, prefix="/chat")
api_router.include_router(messages_router, prefix="/chat")
api_router.include_router(bot_integration_router, prefix="/chat")  # Bot integration
api_router.include_router(ws_router, prefix="/chat")  # WebSocket under /chat
api_router.include_router(utils.router)
api_router.include_router(items.router)


if settings.ENVIRONMENT == "local":
    api_router.include_router(private.router)
