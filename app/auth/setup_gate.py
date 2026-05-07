"""Redirects all routes to /setup until the first admin user exists."""

from sqlalchemy import select
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import RedirectResponse

from app.db import AsyncSessionLocal
from app.models import User

SKIP_PREFIXES = ("/setup", "/static", "/photos", "/health")


class SetupGateMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if any(path == p or path.startswith(p + "/") for p in SKIP_PREFIXES):
            return await call_next(request)

        async with AsyncSessionLocal() as session:
            row = (
                await session.execute(
                    select(User.id).where(User.is_admin.is_(True)).limit(1)
                )
            ).first()
        if row is None:
            return RedirectResponse("/setup", status_code=303)

        return await call_next(request)
