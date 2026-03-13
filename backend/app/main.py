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

# Bridge services are optional integrations. They are skipped in V1_LOCAL_MODE
# (standalone local install) to avoid importing heavy optional dependencies and
# to prevent bridge import errors from blocking startup.
# The hosted server (V1_LOCAL_MODE=False, the default) loads them as before.
if not settings.V1_LOCAL_MODE:
    from app.services.telegram_bridge import telegram_polling_loop
    from app.services.discord_bridge import discord_bot_task
    from app.services.whatsapp_bridge import register_whatsapp_bridge


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

# WhatsApp webhook routes mounted here (before uvicorn starts serving).
# Skipped in V1_LOCAL_MODE — no bridge tokens expected for local installs.
if not settings.V1_LOCAL_MODE:
    register_whatsapp_bridge(app, get_db)


@app.on_event("startup")
async def _start_background_guardians() -> None:
    if not getattr(app.state, "reminder_scheduler_task", None):
        app.state.reminder_scheduler_task = asyncio.create_task(reminder_scheduler())
    if not getattr(app.state, "task_guardian_scheduler_task", None):
        app.state.task_guardian_scheduler_task = asyncio.create_task(task_guardian_scheduler(get_db))
    # Bridge tasks only start when not in V1_LOCAL_MODE.
    if not settings.V1_LOCAL_MODE:
        if not getattr(app.state, "telegram_poller_task", None):
            app.state.telegram_poller_task = asyncio.create_task(telegram_polling_loop(get_db))
        if not getattr(app.state, "discord_bot_task", None):
            app.state.discord_bot_task = asyncio.create_task(discord_bot_task(get_db))

    # Load custom agents persisted in DB into the runtime registry
    try:
        from app.api.routes.chat.agents import load_db_agents_into_registry
        db = next(get_db())
        load_db_agents_into_registry(db)
        db.close()
    except Exception:
        pass

    # Initialize Guardian Vault DB (creates tables if not present)
    try:
        from app.services.guardian.vault import init_vault_db
        init_vault_db()
    except Exception as exc:
        import logging as _logging
        _logging.getLogger(__name__).warning("Guardian Vault init warning: %s", exc)

    # Start terminal session idle-cleanup loop
    if settings.WORKSTATION_LIVE_TERMINAL_ENABLED:
        from app.services.terminal_service import terminal_manager as _tm
        await _tm.start()


@app.on_event("shutdown")
async def _stop_background_guardians() -> None:
    cancel_attrs = ["reminder_scheduler_task", "task_guardian_scheduler_task"]
    if not settings.V1_LOCAL_MODE:
        cancel_attrs += ["telegram_poller_task", "discord_bot_task"]
    for attr in cancel_attrs:
        task = getattr(app.state, attr, None)
        if task:
            task.cancel()

    # Shutdown terminal sessions cleanly
    try:
        from app.services.terminal_service import terminal_manager as _tm
        await _tm.stop()
    except Exception:
        pass
