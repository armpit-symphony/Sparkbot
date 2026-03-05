from fastapi import APIRouter

from app.api.routes import items, login, private, users, utils
from app.api.routes.chat import messages_router, rooms_router, users_router, ws_router, bot_integration_router, uploads_router, model_router, memory_router, tasks_router, reminders_router, slack_router, audit_router
from app.core.config import settings

api_router = APIRouter()
api_router.include_router(login.router)
api_router.include_router(users.router)
api_router.include_router(users_router, prefix="/chat")
api_router.include_router(rooms_router, prefix="/chat")
api_router.include_router(messages_router, prefix="/chat")
api_router.include_router(bot_integration_router, prefix="/chat")  # Bot integration
api_router.include_router(uploads_router, prefix="/chat")  # File uploads
api_router.include_router(model_router, prefix="/chat")    # Model switching
api_router.include_router(memory_router, prefix="/chat")   # User memory
api_router.include_router(tasks_router, prefix="/chat")    # Task management
api_router.include_router(reminders_router, prefix="/chat") # Proactive reminders
api_router.include_router(slack_router, prefix="/chat")     # Slack bridge
api_router.include_router(audit_router, prefix="/chat")     # Audit log
api_router.include_router(ws_router, prefix="/chat")  # WebSocket under /chat
api_router.include_router(utils.router)
api_router.include_router(items.router)


if settings.ENVIRONMENT == "local":
    api_router.include_router(private.router)
