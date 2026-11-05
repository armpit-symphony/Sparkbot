from fastapi import APIRouter

from app.api.routes import items, lima, login, private, users, utils
from app.api.routes.chat import (
    audit_router,
    bot_integration_router,
    dashboard_router,
    github_router,
    guardian_router,
    mcp_router,
    memory_router,
    messages_router,
    model_router,
    projects_router,
    reminders_router,
    robotics_router,
    rooms_router,
    seats_router,
    security_router,
    skills_router,
    slack_router,
    spine_router,
    tasks_router,
    uploads_router,
    users_router,
    voice_router,
    workstation_router,
    ws_router,
)
from app.core.config import settings

api_router = APIRouter()
api_router.include_router(login.router)
api_router.include_router(users.router)
api_router.include_router(lima.router)
api_router.include_router(users_router, prefix="/chat")
api_router.include_router(rooms_router, prefix="/chat")
api_router.include_router(messages_router, prefix="/chat")
api_router.include_router(bot_integration_router, prefix="/chat")  # Bot integration
api_router.include_router(seats_router, prefix="/chat")  # Roundtable seats (outside agents / guests)
api_router.include_router(uploads_router, prefix="/chat")  # File uploads
api_router.include_router(model_router, prefix="/chat")  # Model switching
api_router.include_router(memory_router, prefix="/chat")  # User memory
api_router.include_router(tasks_router, prefix="/chat")  # Task management
api_router.include_router(reminders_router, prefix="/chat")  # Proactive reminders
api_router.include_router(slack_router, prefix="/chat")  # Slack bridge
api_router.include_router(github_router, prefix="/chat")  # GitHub bridge
api_router.include_router(audit_router, prefix="/chat")  # Audit log
api_router.include_router(
    guardian_router, prefix="/chat"
)  # Task Guardian room controls
api_router.include_router(dashboard_router, prefix="/chat")  # Dashboard command center
api_router.include_router(spine_router, prefix="/chat")  # Guardian Spine inspection
api_router.include_router(voice_router, prefix="/chat")  # Voice (Whisper + TTS)
api_router.include_router(skills_router, prefix="/chat")  # Skill marketplace
api_router.include_router(projects_router, prefix="/chat")  # Project management
api_router.include_router(workstation_router, prefix="/chat")  # Workstation overview
api_router.include_router(mcp_router, prefix="/chat")  # Unified MCP registry
api_router.include_router(
    robotics_router, prefix="/chat"
)  # LIMA Robo OS command bridge
api_router.include_router(
    security_router, prefix="/chat"
)  # Operator security posture and hardening
api_router.include_router(ws_router, prefix="/chat")  # WebSocket under /chat

# Terminal router: mounted even when disabled so clients receive a clear 403
# instead of a broken/missing feature. The raw PTY is still gated by
# WORKSTATION_LIVE_TERMINAL_ENABLED, which defaults to false for public v1.
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
