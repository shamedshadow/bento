from datetime import date, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Query, Request
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import require_user
from app.db import get_session
from app.models import Entry, Food, User
from app.services import logging as log_svc

router = APIRouter()
templates = Jinja2Templates(directory="templates")


_METRIC_KEY = {
    "calories": "calories",
    "net_carbs": "net_carbs",
    "total_carbs": "carbs",
    "protein": "protein",
}

_MEAL_LABELS = {
    "breakfast": "Breakfast",
    "lunch": "Lunch",
    "dinner": "Dinner",
    "snack": "Snacks",
    None: "Other",
}


async def _build_dashboard_context(
    request: Request, db: AsyncSession, user: User, day_str: Optional[str]
) -> dict:
    today = log_svc.user_today(user)
    target = date.fromisoformat(day_str) if day_str else today
    is_today = target == today

    pairs = await log_svc.list_entries_with_foods(db, user, target)
    tz = log_svc._user_tz(user)
    grouped: dict[Optional[str], list[tuple[Entry, Food, dict, str]]] = {}
    for entry, food in pairs:
        # %-I/%-l (no leading-zero hour) isn't portable to Windows; strip after.
        local_dt = entry.logged_at.replace(tzinfo=timezone.utc).astimezone(tz)
        local_time = local_dt.strftime("%I:%M %p").lstrip("0")
        grouped.setdefault(entry.meal_type, []).append(
            (entry, food, log_svc.compute_nutrients(food, entry.amount_g), local_time)
        )
    totals = log_svc.daily_totals(pairs)
    primary_total = totals.get(_METRIC_KEY.get(user.primary_metric, "calories"))
    primary_pct = (
        min(1.0, max(0.0, (primary_total or 0.0) / max(1, user.daily_target_primary)))
        if primary_total is not None
        else 0.0
    )

    context: dict = {
        "current_user": user,
        "day": target,
        "is_today": is_today,
        "prev_day": (target.toordinal() - 1),
        "next_day": (target.toordinal() + 1),
        "prev_day_iso": date.fromordinal(target.toordinal() - 1).isoformat(),
        "next_day_iso": date.fromordinal(target.toordinal() + 1).isoformat(),
        "grouped": grouped,
        "totals": totals,
        "primary_total": primary_total,
        "primary_metric": user.primary_metric,
        "primary_metric_label": user.primary_metric.replace("_", " "),
        "primary_target": user.daily_target_primary,
        "primary_pct": primary_pct,
        "meal_order": ["breakfast", "lunch", "dinner", "snack", None],
        "meal_labels": _MEAL_LABELS,
    }

    return context


async def _render_dashboard(
    request: Request, db: AsyncSession, user: User, day_str: Optional[str]
):
    ctx = await _build_dashboard_context(request, db, user, day_str)
    template = (
        "_dashboard_body.html"
        if request.headers.get("HX-Request")
        else "home.html"
    )
    return templates.TemplateResponse(request, template, ctx)


@router.get("/")
async def home(
    request: Request,
    day: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_session),
    user: User = Depends(require_user),
):
    return await _render_dashboard(request, db, user, day)


@router.get("/today")
async def today(
    request: Request,
    day: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_session),
    user: User = Depends(require_user),
):
    return await _render_dashboard(request, db, user, day)
