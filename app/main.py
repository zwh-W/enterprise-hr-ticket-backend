from fastapi import FastAPI

from app.api.routers import audit_logs, auth, internal, tickets, users
from app.core.config import get_settings
from app.core.exceptions import register_exception_handlers
from app.core.logging import configure_logging
from app.middlewares.request_context import RequestContextMiddleware

settings = get_settings()
configure_logging()

app = FastAPI(
    title=settings.app_name,
    debug=settings.debug,
)

app.add_middleware(RequestContextMiddleware)
register_exception_handlers(app)

app.include_router(auth.router)
app.include_router(users.router)
app.include_router(tickets.router)
app.include_router(audit_logs.router)
app.include_router(internal.router)


@app.get("/health", tags=["health"])
def health_check():
    return {"status": "ok", "service": settings.app_name, "environment": settings.environment}
