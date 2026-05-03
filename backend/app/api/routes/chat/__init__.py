"""Chat API routes."""
from app.api.routes.chat.messages import router as messages_router
from app.api.routes.chat.rooms import router as rooms_router
from app.api.routes.chat.users import router as users_router
from app.api.routes.chat.websocket import ws_router
from app.api.routes.chat.bot_integration import router as bot_integration_router
from app.api.routes.chat.uploads import router as uploads_router
from app.api.routes.chat.model import router as model_router
from app.api.routes.chat.memory import router as memory_router
from app.api.routes.chat.tasks import router as tasks_router
from app.api.routes.chat.reminders import router as reminders_router
from app.api.routes.chat.slack import router as slack_router
from app.api.routes.chat.github import router as github_router
from app.api.routes.chat.audit import router as audit_router
from app.api.routes.chat.guardian import router as guardian_router
from app.api.routes.chat.dashboard import router as dashboard_router
from app.api.routes.chat.spine import router as spine_router
from app.api.routes.chat.voice import router as voice_router
from app.api.routes.chat.skills import router as skills_router
from app.api.routes.chat.projects import router as projects_router
from app.api.routes.chat.workstation import router as workstation_router
from app.api.routes.chat.mcp import router as mcp_router
from app.api.routes.chat.robotics import router as robotics_router

__all__ = ["messages_router", "rooms_router", "users_router", "ws_router", "bot_integration_router", "uploads_router", "model_router", "memory_router", "tasks_router", "reminders_router", "slack_router", "github_router", "audit_router", "guardian_router", "dashboard_router", "spine_router", "voice_router", "skills_router", "projects_router", "workstation_router", "mcp_router", "robotics_router"]
