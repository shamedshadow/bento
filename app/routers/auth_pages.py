from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import magic_links, pins, sessions
from app.auth.deps import get_current_user
from app.config import settings
from app.db import get_session
from app.models import User
from app.models.user import PRIMARY_METRICS

router = APIRouter()
templates = Jinja2Templates(directory="templates")


def _set_session_cookie(response, token: str) -> None:
    response.set_cookie(
        key=sessions.SESSION_COOKIE_NAME,
        value=token,
        max_age=sessions.cookie_max_age_seconds(),
        httponly=True,
        samesite="lax",
        secure=settings.cookie_secure,
        path="/",
    )


def _clear_session_cookie(response) -> None:
    response.delete_cookie(
        key=sessions.SESSION_COOKIE_NAME,
        path="/",
        secure=settings.cookie_secure,
        httponly=True,
        samesite="lax",
    )


# ----- First-run admin setup -------------------------------------------------


@router.get("/setup")
async def setup_form(
    request: Request,
    db: AsyncSession = Depends(get_session),
):
    # The SetupGateMiddleware only redirects to /setup when no admin exists. If
    # someone navigates here after setup is complete, send them home.
    has_admin = (
        await db.execute(select(User.id).where(User.is_admin.is_(True)).limit(1))
    ).first()
    if has_admin is not None:
        return RedirectResponse("/", status_code=303)

    return templates.TemplateResponse(
        request, "auth/setup.html", {"metrics": PRIMARY_METRICS, "error": None}
    )


@router.post("/setup")
async def setup_submit(
    request: Request,
    name: str = Form(...),
    email: str = Form(...),
    primary_metric: str = Form(...),
    daily_target_primary: int = Form(...),
    pin: str = Form(...),
    pin_confirm: str = Form(...),
    db: AsyncSession = Depends(get_session),
):
    has_admin = (
        await db.execute(select(User.id).where(User.is_admin.is_(True)).limit(1))
    ).first()
    if has_admin is not None:
        return RedirectResponse("/", status_code=303)

    error = _validate_setup(name, email, primary_metric, daily_target_primary, pin, pin_confirm)
    if error:
        return templates.TemplateResponse(
            request,
            "auth/setup.html",
            {"metrics": PRIMARY_METRICS, "error": error},
            status_code=400,
        )

    user = User(
        email=email.strip().lower(),
        name=name.strip(),
        is_admin=True,
        is_active=True,
        primary_metric=primary_metric,
        daily_target_primary=int(daily_target_primary),
        pin_hash=pins.hash_pin(pin),
        pin_set_at=datetime.now(timezone.utc).replace(tzinfo=None),
    )
    db.add(user)
    await db.flush()

    sess = await sessions.create_session(db, user)
    await db.commit()

    response = RedirectResponse("/", status_code=303)
    _set_session_cookie(response, sess.token)
    return response


def _validate_setup(
    name: str, email: str, metric: str, target: int, pin: str, pin_confirm: str
) -> str | None:
    if not name.strip():
        return "Name is required."
    if "@" not in email or len(email) < 3:
        return "Enter a valid email address."
    if metric not in PRIMARY_METRICS:
        return "Pick a valid primary metric."
    if not isinstance(target, int) or target <= 0:
        return "Daily target must be a positive number."
    if not pins.is_valid_pin(pin):
        return "PIN must be 4–6 digits."
    if pin != pin_confirm:
        return "PINs don't match."
    return None


# ----- Login (PIN) -----------------------------------------------------------


@router.get("/auth/login")
async def login_picker(
    request: Request,
    db: AsyncSession = Depends(get_session),
):
    if getattr(request.state, "current_user", None) is not None:
        return RedirectResponse("/", status_code=303)
    users = (
        await db.execute(
            select(User)
            .where(User.is_active.is_(True), User.pin_hash.is_not(None))
            .order_by(User.name)
        )
    ).scalars().all()
    return templates.TemplateResponse(
        request, "auth/login.html", {"users": users}
    )


@router.get("/auth/login/{user_id}")
async def login_pin_form(
    user_id: int,
    request: Request,
    db: AsyncSession = Depends(get_session),
):
    user = await _loadable_login_user(db, user_id)
    if user is None:
        return RedirectResponse("/auth/login", status_code=303)

    locked_for = pins.lockout_seconds_remaining(user)
    return templates.TemplateResponse(
        request,
        "auth/login_pin.html",
        {"user": user, "error": None, "locked_for": locked_for},
    )


@router.post("/auth/login/{user_id}")
async def login_pin_submit(
    user_id: int,
    request: Request,
    pin: str = Form(...),
    db: AsyncSession = Depends(get_session),
):
    user = await _loadable_login_user(db, user_id)
    if user is None:
        return RedirectResponse("/auth/login", status_code=303)

    if pins.is_locked(user):
        return templates.TemplateResponse(
            request,
            "auth/login_pin.html",
            {
                "user": user,
                "error": "Too many attempts. Try again shortly.",
                "locked_for": pins.lockout_seconds_remaining(user),
            },
            status_code=429,
        )

    if not pins.is_valid_pin(pin) or user.pin_hash is None or not pins.verify_pin(pin, user.pin_hash):
        pins.record_failure(user)
        await db.commit()
        return templates.TemplateResponse(
            request,
            "auth/login_pin.html",
            {
                "user": user,
                "error": "Incorrect PIN.",
                "locked_for": pins.lockout_seconds_remaining(user),
            },
            status_code=401,
        )

    pins.record_success(user)
    sess = await sessions.create_session(db, user)
    await db.commit()

    response = RedirectResponse("/", status_code=303)
    _set_session_cookie(response, sess.token)
    return response


async def _loadable_login_user(db: AsyncSession, user_id: int) -> User | None:
    user = await db.get(User, user_id)
    if user is None or not user.is_active or user.pin_hash is None:
        return None
    return user


# ----- Magic link landing (PIN setup) ---------------------------------------


@router.get("/auth/magic/{token}")
async def magic_landing(
    token: str,
    request: Request,
    db: AsyncSession = Depends(get_session),
):
    link = await magic_links.find_valid_link(db, token)
    if link is None:
        return templates.TemplateResponse(
            request, "auth/magic_invalid.html", status_code=410
        )
    user = await db.get(User, link.user_id)
    if user is None or not user.is_active:
        return templates.TemplateResponse(
            request, "auth/magic_invalid.html", status_code=410
        )

    return templates.TemplateResponse(
        request,
        "auth/magic_landing.html",
        {"user": user, "token": token, "error": None},
    )


@router.post("/auth/magic/{token}")
async def magic_set_pin(
    token: str,
    request: Request,
    pin: str = Form(...),
    pin_confirm: str = Form(...),
    db: AsyncSession = Depends(get_session),
):
    link = await magic_links.find_valid_link(db, token)
    if link is None:
        return templates.TemplateResponse(
            request, "auth/magic_invalid.html", status_code=410
        )
    user = await db.get(User, link.user_id)
    if user is None or not user.is_active:
        return templates.TemplateResponse(
            request, "auth/magic_invalid.html", status_code=410
        )

    if not pins.is_valid_pin(pin):
        return templates.TemplateResponse(
            request,
            "auth/magic_landing.html",
            {"user": user, "token": token, "error": "PIN must be 4–6 digits."},
            status_code=400,
        )
    if pin != pin_confirm:
        return templates.TemplateResponse(
            request,
            "auth/magic_landing.html",
            {"user": user, "token": token, "error": "PINs don't match."},
            status_code=400,
        )

    user.pin_hash = pins.hash_pin(pin)
    user.pin_set_at = datetime.now(timezone.utc).replace(tzinfo=None)
    pins.record_success(user)
    await magic_links.consume_link(db, link)

    sess = await sessions.create_session(db, user)
    await db.commit()

    response = RedirectResponse("/", status_code=303)
    _set_session_cookie(response, sess.token)
    return response


# ----- Logout ----------------------------------------------------------------


@router.post("/auth/logout")
async def logout(
    request: Request,
    db: AsyncSession = Depends(get_session),
    user: User | None = Depends(get_current_user),
):
    token = request.cookies.get(sessions.SESSION_COOKIE_NAME)
    if token:
        await sessions.destroy_session(db, token)
        await db.commit()
    response = RedirectResponse("/auth/login", status_code=303)
    _clear_session_cookie(response)
    return response
