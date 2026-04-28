from fastapi import APIRouter

from app.api.routes import items, login, private, users, utils
from app.api.routes.chat import messages_router, rooms_router, users_router, ws_router, bot_integration_router, uploads_router, model_router, memory_router, tasks_router, reminders_router, slack_router, github_router, audit_router, guardian_router, dashboard_router, spine_router, voice_router, skills_router, projects_router, workstation_router, mcp_router
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
api_router.include_router(github_router, prefix="/chat")    # GitHub bridge
api_router.include_router(audit_router, prefix="/chat")     # Audit log
api_router.include_router(guardian_router, prefix="/chat")  # Task Guardian room controls
api_router.include_router(dashboard_router, prefix="/chat") # Dashboard command center
api_router.include_router(spine_router, prefix="/chat")     # Guardian Spine inspection
api_router.include_router(voice_router, prefix="/chat")     # Voice (Whisper + TTS)
api_router.include_router(skills_router, prefix="/chat")    # Skill marketplace
api_router.include_router(projects_router, prefix="/chat")  # Project management
api_router.include_router(workstation_router, prefix="/chat") # Workstation overview
api_router.include_router(mcp_router, prefix="/chat")       # Unified MCP registry
api_router.include_router(ws_router, prefix="/chat")  # WebSocket under /chat

# Terminal router: now cross-platform (Windows uses pywinpty ConPTY, Unix uses pty/fcntl).
# Gated by WORKSTATION_LIVE_TERMINAL_ENABLED; defaults to true in desktop_launcher.py.
if settings.WORKSTATION_LIVE_TERMINAL_ENABLED:
    try:
        from app.api.routes.terminal import terminal_router as _terminal_router
        api_router.include_router(_terminal_router, prefix="/terminal")
    except Exception as _term_err:
        import logging as _logging
        _logging.getLogger(__name__).warning("Terminal router unavailable: %s", _term_err)

api_router.include_router(utils.router)
api_router.include_router(items.router)


if settings.ENVIRONMENT == "local":
    api_router.include_router(private.router)
