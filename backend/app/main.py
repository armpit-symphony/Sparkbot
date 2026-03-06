import sentry_sdk
import asyncio
from fastapi import FastAPI
from fastapi.routing import APIRoute
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.cors import CORSMiddleware

from app.api.main import api_router
from app.api.deps import get_db
from app.api.routes.chat.reminders import reminder_scheduler
from app.core.config import settings
from app.services.guardian.task_guardian import task_guardian_scheduler
from app.services.telegram_bridge import telegram_polling_loop


def custom_generate_unique_id(route: APIRoute) -> str:
    return f"{route.tags[0]}-{route.name}"


if settings.SENTRY_DSN and settings.ENVIRONMENT != "local":
    sentry_sdk.init(dsn=str(settings.SENTRY_DSN), enable_tracing=True)

app = FastAPI(
    title=settings.PROJECT_NAME,
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    generate_unique_id_function=custom_generate_unique_id,
)

class _SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        if (
            request.url.scheme == "https"
            or request.headers.get("x-forwarded-proto") == "https"
        ):
            response.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self' 'unsafe-inline'; "
            "style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; "
            "connect-src 'self' wss: https:; font-src 'self' data:; "
            "frame-ancestors 'none'; object-src 'none'; base-uri 'self'"
        )
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        return response


# Set all CORS enabled origins
if settings.all_cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.all_cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "Accept"],
    )

app.add_middleware(_SecurityHeadersMiddleware)

app.include_router(api_router, prefix=settings.API_V1_STR)


@app.on_event("startup")
async def _start_background_guardians() -> None:
    if not getattr(app.state, "reminder_scheduler_task", None):
        app.state.reminder_scheduler_task = asyncio.create_task(reminder_scheduler())
    if not getattr(app.state, "task_guardian_scheduler_task", None):
        app.state.task_guardian_scheduler_task = asyncio.create_task(task_guardian_scheduler(get_db))
    if not getattr(app.state, "telegram_poller_task", None):
        app.state.telegram_poller_task = asyncio.create_task(telegram_polling_loop(get_db))


@app.on_event("shutdown")
async def _stop_background_guardians() -> None:
    for attr in ("reminder_scheduler_task", "task_guardian_scheduler_task", "telegram_poller_task"):
        task = getattr(app.state, attr, None)
        if task:
            task.cancel()
