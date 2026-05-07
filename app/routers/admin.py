import sqlite3
import tempfile
from datetime import date
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.background import BackgroundTask

from app.auth import magic_links
from app.auth.deps import require_admin
from app.config import settings as app_settings
from app.db import get_session
from app.models import Entry, Food, MagicLink, User
from app.models.user import PRIMARY_METRICS
from app.services import mealie as mealie_svc

router = APIRouter(prefix="/admin")
templates = Jinja2Templates(directory="templates")


def _build_magic_url(request: Request, token: str) -> str:
    base = str(request.base_url).rstrip("/")
    return f"{base}/auth/magic/{token}"


def _quote(s: str) -> str:
    from urllib.parse import quote
    return quote(s)


@router.get("")
async def admin_hub(
    request: Request,
    db: AsyncSession = Depends(get_session),
    admin: User = Depends(require_admin),
):
    mealie = await mealie_svc.get_or_create_settings(db)
    await db.commit()
    return templates.TemplateResponse(
        request,
        "admin/index.html",
        {"current_user": admin, "mealie": mealie},
    )


@router.get("/users")
async def list_users(
    request: Request,
    flash_link_for_user: int | None = None,
    msg: str | None = None,
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
            "flash_msg": msg,
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


@router.get("/backup")
async def download_backup(
    admin: User = Depends(require_admin),
):
    """Stream a consistent SQLite snapshot via the backup API."""
    url = app_settings.database_url
    marker = "sqlite+aiosqlite:///"
    if not url.startswith(marker):
        raise HTTPException(500, "Backup only supported for SQLite databases.")
    src_path = Path(url[len(marker):]).resolve()
    if not src_path.exists():
        raise HTTPException(500, f"DB file not found at {src_path}.")

    # Use SQLite's online backup API rather than a raw file copy so a write
    # mid-stream can't corrupt the snapshot.
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    tmp_path = tmp.name
    src = sqlite3.connect(str(src_path))
    dst = sqlite3.connect(tmp_path)
    try:
        src.backup(dst)
    finally:
        src.close()
        dst.close()

    def _cleanup(path: str) -> None:
        try:
            Path(path).unlink(missing_ok=True)
        except Exception:
            pass

    filename = f"bento-{date.today().isoformat()}.db"
    return FileResponse(
        tmp_path,
        media_type="application/octet-stream",
        filename=filename,
        background=BackgroundTask(_cleanup, tmp_path),
    )


@router.get("/mealie")
async def mealie_page(
    request: Request,
    db: AsyncSession = Depends(get_session),
    admin: User = Depends(require_admin),
):
    cfg = await mealie_svc.get_or_create_settings(db)
    await db.commit()
    return templates.TemplateResponse(
        request,
        "admin/mealie.html",
        {
            "current_user": admin,
            "mealie": cfg,
            "mealie_msg": request.query_params.get("mealie_msg"),
            "mealie_ok": request.query_params.get("mealie_ok") == "1",
        },
    )


@router.post("/mealie")
async def save_mealie(
    url: Optional[str] = Form(None),
    api_token: Optional[str] = Form(None),
    db: AsyncSession = Depends(get_session),
    admin: User = Depends(require_admin),
):
    cfg = await mealie_svc.get_or_create_settings(db)
    new_url = (url or "").strip().rstrip("/")
    new_token = (api_token or "").strip()

    if not new_url and not new_token:
        cfg.url = None
        cfg.api_token = None
        await db.commit()
        return RedirectResponse(
            "/admin/mealie?mealie_ok=1&mealie_msg=" + _quote("Cleared."),
            status_code=303,
        )

    if not new_url or not new_token:
        return RedirectResponse(
            "/admin/mealie?mealie_ok=0&mealie_msg="
            + _quote("Both URL and API token are required."),
            status_code=303,
        )

    if new_url != cfg.url or new_token != cfg.api_token:
        ok, msg = await mealie_svc.test_connection(new_url, new_token)
        if not ok:
            return RedirectResponse(
                f"/admin/mealie?mealie_ok=0&mealie_msg={_quote(msg)}",
                status_code=303,
            )

    cfg.url = new_url
    cfg.api_token = new_token
    await db.commit()
    return RedirectResponse(
        "/admin/mealie?mealie_ok=1&mealie_msg=" + _quote("Saved."),
        status_code=303,
    )


@router.post("/mealie/sync")
async def sync_mealie(
    db: AsyncSession = Depends(get_session),
    admin: User = Depends(require_admin),
):
    cfg = await mealie_svc.get_or_create_settings(db)
    if not cfg.url or not cfg.api_token:
        return RedirectResponse(
            "/admin/mealie?mealie_ok=0&mealie_msg="
            + _quote("Configure Mealie first."),
            status_code=303,
        )
    result = await mealie_svc.sync(db, cfg)
    await db.commit()
    if "error" in result:
        return RedirectResponse(
            f"/admin/mealie?mealie_ok=0&mealie_msg={_quote(result['error'])}",
            status_code=303,
        )
    msg = (
        f"{result['imported']} new, {result['updated']} updated, "
        f"{result['skipped']} skipped (of {result['total']} recipes)"
    )
    return RedirectResponse(
        f"/admin/mealie?mealie_ok=1&mealie_msg={_quote(msg)}",
        status_code=303,
    )


@router.post("/users/{user_id}/delete")
async def delete_user(
    user_id: int,
    confirm: str = Form(""),
    db: AsyncSession = Depends(get_session),
    admin: User = Depends(require_admin),
):
    target = await db.get(User, user_id)
    if target is None:
        raise HTTPException(404)

    # Safeguards.
    if target.id == admin.id:
        return _redirect_with_msg("You can't delete your own account from here.")
    if target.is_admin:
        admin_count = (
            await db.execute(
                select(User).where(User.is_admin.is_(True), User.is_active.is_(True))
            )
        ).scalars().all()
        if len([u for u in admin_count if u.id != target.id]) == 0:
            return _redirect_with_msg("Refusing to delete the last admin.")
    if confirm != "DELETE":
        return _redirect_with_msg("Type DELETE to confirm.")

    # Foods this user created stay, but lose their owner reference (nullable column).
    await db.execute(
        update(Food)
        .where(Food.created_by_user_id == target.id)
        .values(created_by_user_id=None)
    )
    # Entries don't cascade (intentional: keeps data lifecycle explicit).
    await db.execute(delete(Entry).where(Entry.user_id == target.id))
    # The remaining children (sessions, favorites, magic_links, saved_meals,
    # saved_meal_items, discord_settings, reminder_log) cascade via FKs.
    await db.delete(target)
    await db.commit()

    return _redirect_with_msg(f"Deleted user '{target.name}'.")


def _redirect_with_msg(msg: str) -> RedirectResponse:
    return RedirectResponse(f"/admin/users?msg={_quote(msg)}", status_code=303)
