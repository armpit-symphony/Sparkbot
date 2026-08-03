from fastapi import FastAPI

from app.api.capabilities import router as capabilities_router
from app.api.health import router as health_router
from app.api.command_center import router as command_center_router
from app.core.settings import settings

app = FastAPI(title=settings.project_name)
app.include_router(health_router)
app.include_router(capabilities_router)
app.include_router(command_center_router)
