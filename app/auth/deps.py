"""FastAPI dependencies for auth-gated routes."""

from typing import Optional

from fastapi import Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse

from app.models import User


async def get_current_user(request: Request) -> Optional[User]:
    return getattr(request.state, "current_user", None)


async def require_user(
    request: Request,
    user: Optional[User] = Depends(get_current_user),
) -> User:
    if user is None:
        if request.headers.get("HX-Request"):
            raise HTTPException(
                status_code=401, headers={"HX-Redirect": "/auth/login"}
            )
        # FastAPI handles dependency-raised HTTPException; for redirect we
        # raise a 307 with Location so the browser follows it.
        raise HTTPException(
            status_code=status.HTTP_307_TEMPORARY_REDIRECT,
            headers={"Location": "/auth/login"},
        )
    return user


async def require_admin(user: User = Depends(require_user)) -> User:
    if not user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Admin only"
        )
    return user


def redirect_to(url: str) -> RedirectResponse:
    return RedirectResponse(url, status_code=303)
