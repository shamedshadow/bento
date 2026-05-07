from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import magic_links
from app.auth.deps import require_admin
from app.db import get_session
from app.models import MagicLink, User
from app.models.user import PRIMARY_METRICS

router = APIRouter(prefix="/admin")
templates = Jinja2Templates(directory="templates")


def _build_magic_url(request: Request, token: str) -> str:
    base = str(request.base_url).rstrip("/")
    return f"{base}/auth/magic/{token}"


@router.get("/users")
async def list_users(
    request: Request,
    flash_link_for_user: int | None = None,
    db: AsyncSession = Depends(get_session),
    admin: User = Depends(require_admin),
):
    users = (
        await db.execute(select(User).order_by(User.is_admin.desc(), User.name))
    ).scalars().all()

    pending_links: dict[int, str] = {}
    for u in users:
        if u.pin_hash is None:
            link = (
                await db.execute(
                    select(MagicLink)
                    .where(MagicLink.user_id == u.id, MagicLink.used_at.is_(None))
                    .order_by(MagicLink.created_at.desc())
                    .limit(1)
                )
            ).scalar_one_or_none()
            if link is not None:
                pending_links[u.id] = _build_magic_url(request, link.token)

    return templates.TemplateResponse(
        request,
        "admin/users.html",
        {
            "users": users,
            "pending_links": pending_links,
            "metrics": PRIMARY_METRICS,
            "current_user": admin,
            "flash_link_for_user": flash_link_for_user,
        },
    )


@router.post("/users")
async def create_user(
    request: Request,
    name: str = Form(...),
    email: str = Form(...),
    primary_metric: str = Form(...),
    daily_target_primary: int = Form(...),
    db: AsyncSession = Depends(get_session),
    admin: User = Depends(require_admin),
):
    email_norm = email.strip().lower()
    name_norm = name.strip()
    if not name_norm or "@" not in email_norm or primary_metric not in PRIMARY_METRICS:
        return RedirectResponse("/admin/users", status_code=303)

    existing = (
        await db.execute(select(User).where(User.email == email_norm))
    ).scalar_one_or_none()
    if existing is not None:
        return RedirectResponse("/admin/users", status_code=303)

    user = User(
        email=email_norm,
        name=name_norm,
        primary_metric=primary_metric,
        daily_target_primary=int(daily_target_primary),
        is_admin=False,
        is_active=True,
    )
    db.add(user)
    await db.flush()

    await magic_links.create_magic_link(db, user)
    await db.commit()

    return RedirectResponse(
        f"/admin/users?flash_link_for_user={user.id}", status_code=303
    )


@router.post("/users/{user_id}/regenerate-link")
async def regenerate_link(
    user_id: int,
    db: AsyncSession = Depends(get_session),
    admin: User = Depends(require_admin),
):
    user = await db.get(User, user_id)
    if user is None or user.pin_hash is not None:
        return RedirectResponse("/admin/users", status_code=303)

    await magic_links.create_magic_link(db, user)
    await db.commit()
    return RedirectResponse(
        f"/admin/users?flash_link_for_user={user.id}", status_code=303
    )
