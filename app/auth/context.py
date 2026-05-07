"""Middleware that resolves the current user from the session cookie and
attaches them to `request.state`. Cheap on static/health paths via SKIP_PREFIXES.
"""

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from app.auth.sessions import SESSION_COOKIE_NAME, lookup_session
from app.db import AsyncSessionLocal

SKIP_PREFIXES = ("/static", "/photos", "/health")


class AuthContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        request.state.current_user = None

        if any(path == p or path.startswith(p + "/") for p in SKIP_PREFIXES):
            return await call_next(request)

        token = request.cookies.get(SESSION_COOKIE_NAME)
        if token:
            async with AsyncSessionLocal() as session:
                result = await lookup_session(session, token)
                if result is not None:
                    _, user = result
                    request.state.current_user = user
                await session.commit()

        return await call_next(request)
