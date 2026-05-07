"""Middleware that resolves the current user from the session cookie and
attaches them to `request.state`. Cheap on static/health paths via SKIP_PREFIXES.
"""

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from app.auth.sessions import SESSION_COOKIE_NAME, lookup_session
from app.db import AsyncSessionLocal
from app.version import BENTO_VERSION, GIT_SHA

SKIP_PREFIXES = ("/static", "/photos", "/health")


class AuthContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        request.state.current_user = None
        # Templates read these to render the version footer in the gear menu.
        request.state.bento_version = BENTO_VERSION
        request.state.bento_git_sha = GIT_SHA

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
