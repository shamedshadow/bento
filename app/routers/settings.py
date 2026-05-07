from typing import Optional

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import require_user
from app.auth.sessions import SESSION_COOKIE_NAME
from app.config import settings as app_settings
from app.db import get_session
from app.models import User
from app.models.user import PRIMARY_METRICS
from app.services import discord as discord_svc
from app.services import settings as settings_svc

# Common IANA timezones — short list. Users can also free-type any IANA name.
COMMON_TIMEZONES = (
    "America/New_York",
    "America/Chicago",
    "America/Denver",
    "America/Los_Angeles",
    "America/Phoenix",
    "America/Anchorage",
    "Pacific/Honolulu",
    "UTC",
    "Europe/London",
    "Europe/Paris",
    "Europe/Berlin",
    "Asia/Tokyo",
    "Australia/Sydney",
)

router = APIRouter(prefix="/settings")
templates = Jinja2Templates(directory="templates")


def _flash(request: Request, key: str) -> Optional[str]:
    return request.query_params.get(key)


@router.get("")
async def settings_page(
    request: Request,
    db: AsyncSession = Depends(get_session),
    user: User = Depends(require_user),
):
    discord = await discord_svc.get_settings(db, user.id)
    meal_times = (
        ", ".join(discord_svc.deserialize_meal_times(discord.meal_reminders_times))
        if discord
        else ""
    )
    return templates.TemplateResponse(
        request,
        "settings.html",
        {
            "current_user": user,
            "discord": discord,
            "meal_times_csv": meal_times,
            "metrics": PRIMARY_METRICS,
            "timezones": COMMON_TIMEZONES,
            "saved": _flash(request, "saved"),
            "discord_msg": _flash(request, "discord_msg"),
            "discord_ok": _flash(request, "discord_ok") == "1",
            "danger_msg": _flash(request, "danger_msg"),
        },
    )


@router.post("/profile")
async def save_profile(
    name: str = Form(...),
    primary_metric: str = Form(...),
    daily_target_primary: int = Form(...),
    secondary_metric: Optional[str] = Form(None),
    secondary_target: Optional[int] = Form(None),
    secondary_target_type: Optional[str] = Form(None),
    timezone: str = Form("America/New_York"),
    db: AsyncSession = Depends(get_session),
    user: User = Depends(require_user),
):
    # `user` came from AuthContextMiddleware's session (already closed). Re-fetch
    # via this route's session so mutations are tracked and committed.
    attached = await db.get(User, user.id)
    settings_svc.update_profile(
        attached,
        name=name,
        primary_metric=primary_metric,
        daily_target_primary=daily_target_primary,
        secondary_metric=secondary_metric,
        secondary_target=secondary_target,
        secondary_target_type=secondary_target_type,
        timezone=timezone,
    )
    await db.commit()
    return RedirectResponse("/settings?saved=profile", status_code=303)


@router.post("/discord")
async def save_discord(
    webhook_url: Optional[str] = Form(None),
    meal_reminders_enabled: Optional[str] = Form(None),
    meal_reminders_times: Optional[str] = Form(None),
    eod_summary_enabled: Optional[str] = Form(None),
    eod_summary_time: str = Form("21:00"),
    weekly_summary_enabled: Optional[str] = Form(None),
    weekly_summary_day: int = Form(0),
    log_nudge_enabled: Optional[str] = Form(None),
    log_nudge_after_hours: int = Form(6),
    db: AsyncSession = Depends(get_session),
    user: User = Depends(require_user),
):
    cfg = await discord_svc.ensure_settings(db, user.id)
    new_url = (webhook_url or "").strip() or None

    # If URL changed and is non-empty, test it before persisting.
    msg = ""
    ok = True
    if new_url and new_url != cfg.webhook_url:
        ok, msg = await discord_svc.send_test(new_url, user)
        if not ok:
            return RedirectResponse(
                f"/settings?discord_ok=0&discord_msg={_quote(msg)}",
                status_code=303,
            )

    cfg.webhook_url = new_url
    cfg.meal_reminders_enabled = bool(meal_reminders_enabled)
    cfg.meal_reminders_times = discord_svc.serialize_meal_times(
        discord_svc.parse_meal_times(meal_reminders_times or "")
    )
    cfg.eod_summary_enabled = bool(eod_summary_enabled)
    if discord_svc._valid_hhmm(eod_summary_time):
        cfg.eod_summary_time = eod_summary_time
    cfg.weekly_summary_enabled = bool(weekly_summary_enabled)
    cfg.weekly_summary_day = max(0, min(6, int(weekly_summary_day)))
    cfg.log_nudge_enabled = bool(log_nudge_enabled)
    cfg.log_nudge_after_hours = max(1, min(24, int(log_nudge_after_hours)))
    # Re-enable if user is editing settings — they're saying "this works now."
    if cfg.webhook_url:
        cfg.auto_disabled = False
        cfg.consecutive_failures = 0

    await db.commit()

    flash = "Saved." if not msg else f"Saved. {msg}"
    return RedirectResponse(
        f"/settings?discord_ok=1&discord_msg={_quote(flash)}",
        status_code=303,
    )


@router.post("/test-webhook")
async def test_webhook(
    db: AsyncSession = Depends(get_session),
    user: User = Depends(require_user),
):
    cfg = await discord_svc.get_settings(db, user.id)
    if not cfg or not cfg.webhook_url:
        return RedirectResponse(
            "/settings?discord_ok=0&discord_msg=" + _quote("No webhook URL saved."),
            status_code=303,
        )
    ok, msg = await discord_svc.send_test(cfg.webhook_url, user)
    return RedirectResponse(
        f"/settings?discord_ok={'1' if ok else '0'}&discord_msg={_quote(msg)}",
        status_code=303,
    )


@router.post("/sign-out-everywhere")
async def sign_out_all(
    request: Request,
    db: AsyncSession = Depends(get_session),
    user: User = Depends(require_user),
):
    current = request.cookies.get(SESSION_COOKIE_NAME)
    n = await settings_svc.sign_out_everywhere(db, user.id, except_token=current)
    await db.commit()
    return RedirectResponse(
        f"/settings?danger_msg={_quote(f'Signed out {n} other session(s).')}",
        status_code=303,
    )


@router.post("/delete-all-entries")
async def delete_entries(
    confirm: Optional[str] = Form(None),
    db: AsyncSession = Depends(get_session),
    user: User = Depends(require_user),
):
    if confirm != "DELETE":
        return RedirectResponse(
            "/settings?danger_msg=" + _quote("Type DELETE to confirm."),
            status_code=303,
        )
    n = await settings_svc.delete_all_entries(db, user.id)
    await db.commit()
    return RedirectResponse(
        f"/settings?danger_msg={_quote(f'Deleted {n} entries.')}",
        status_code=303,
    )


def _quote(s: str) -> str:
    from urllib.parse import quote
    return quote(s)
