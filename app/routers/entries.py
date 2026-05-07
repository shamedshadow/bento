from datetime import date, datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import require_user
from app.db import get_session
from app.models import Entry, Food, User
from app.models.entry import MEAL_TYPES
from app.services import logging as logsvc

router = APIRouter()
templates = Jinja2Templates(directory="templates")


def _parse_logged_at(value: Optional[str]) -> Optional[datetime]:
    """Parse the HTML <input type='datetime-local'> value (no tz, user-local)."""
    if not value:
        return None
    try:
        # datetime-local sends "YYYY-MM-DDTHH:MM" (no seconds, no tz)
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _localize_to_utc_naive(local_dt: datetime, user: User) -> datetime:
    tz = logsvc._user_tz(user)
    return local_dt.replace(tzinfo=tz).astimezone(timezone.utc).replace(tzinfo=None)


def _utc_to_local(naive_utc: datetime, user: User) -> datetime:
    return naive_utc.replace(tzinfo=timezone.utc).astimezone(logsvc._user_tz(user))


# ----- JSON API --------------------------------------------------------------


def _serialize_entry(entry: Entry, food: Food, user: User) -> dict:
    n = logsvc.compute_nutrients(food, entry.amount_g)
    return {
        "id": entry.id,
        "food_id": food.id,
        "food_name": food.name,
        "food_brand": food.brand,
        "amount_g": entry.amount_g,
        "meal_type": entry.meal_type,
        "notes": entry.notes,
        "logged_at": _utc_to_local(entry.logged_at, user).isoformat(),
        "nutrients": n,
    }


@router.post("/api/entries")
async def api_create_entry(
    food_id: int = Form(...),
    amount_g: float = Form(..., gt=0),
    meal_type: Optional[str] = Form(None),
    notes: Optional[str] = Form(None),
    logged_at: Optional[str] = Form(None),
    db: AsyncSession = Depends(get_session),
    user: User = Depends(require_user),
):
    food = await db.get(Food, food_id)
    if food is None:
        raise HTTPException(404, "Food not found")
    if meal_type and meal_type not in MEAL_TYPES:
        raise HTTPException(400, "Invalid meal_type")

    parsed = _parse_logged_at(logged_at)
    logged_at_utc = (
        _localize_to_utc_naive(parsed, user) if parsed else None
    )

    entry = await logsvc.create_entry(
        db,
        user_id=user.id,
        food_id=food.id,
        amount_g=amount_g,
        meal_type=meal_type,
        notes=notes,
        logged_at=logged_at_utc,
    )
    await db.commit()
    return _serialize_entry(entry, food, user)


@router.get("/api/entries")
async def api_list_entries(
    day: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_session),
    user: User = Depends(require_user),
):
    target = date.fromisoformat(day) if day else logsvc.user_today(user)
    pairs = await logsvc.list_entries_with_foods(db, user, target)
    return {
        "day": target.isoformat(),
        "entries": [_serialize_entry(e, f, user) for e, f in pairs],
        "totals": logsvc.daily_totals(pairs),
    }


@router.delete("/api/entries/{entry_id}")
async def api_delete_entry(
    entry_id: int,
    db: AsyncSession = Depends(get_session),
    user: User = Depends(require_user),
):
    entry = await db.get(Entry, entry_id)
    if entry is None or entry.user_id != user.id:
        raise HTTPException(404)
    await logsvc.delete_entry(db, entry)
    await db.commit()
    return {"deleted": entry_id}


# ----- HTML pages ------------------------------------------------------------


@router.get("/foods/{food_id}/log")
async def log_dialog(
    food_id: int,
    request: Request,
    db: AsyncSession = Depends(get_session),
    user: User = Depends(require_user),
):
    food = await db.get(Food, food_id)
    if food is None:
        raise HTTPException(404)
    now_local = _utc_to_local(datetime.now(timezone.utc).replace(tzinfo=None), user)
    return templates.TemplateResponse(
        request,
        "entries/log_dialog.html",
        {
            "food": food,
            "current_user": user,
            "default_amount_g": food.default_serving_g or 100.0,
            "now_local": now_local.strftime("%Y-%m-%dT%H:%M"),
            "meal_types": MEAL_TYPES,
            "error": None,
        },
    )


@router.post("/foods/{food_id}/log")
async def log_submit(
    food_id: int,
    request: Request,
    amount_g: float = Form(..., gt=0),
    meal_type: Optional[str] = Form(None),
    notes: Optional[str] = Form(None),
    logged_at: Optional[str] = Form(None),
    db: AsyncSession = Depends(get_session),
    user: User = Depends(require_user),
):
    food = await db.get(Food, food_id)
    if food is None:
        raise HTTPException(404)
    if meal_type and meal_type not in MEAL_TYPES:
        meal_type = None

    parsed = _parse_logged_at(logged_at)
    logged_at_utc = (
        _localize_to_utc_naive(parsed, user) if parsed else None
    )

    await logsvc.create_entry(
        db,
        user_id=user.id,
        food_id=food.id,
        amount_g=amount_g,
        meal_type=meal_type,
        notes=notes,
        logged_at=logged_at_utc,
    )
    await db.commit()
    return RedirectResponse("/today", status_code=303)


@router.get("/entries/{entry_id}/edit")
async def edit_entry_form(
    entry_id: int,
    request: Request,
    db: AsyncSession = Depends(get_session),
    user: User = Depends(require_user),
):
    entry = await db.get(Entry, entry_id)
    if entry is None or entry.user_id != user.id:
        raise HTTPException(404)
    food = await db.get(Food, entry.food_id)
    logged_local = _utc_to_local(entry.logged_at, user).strftime("%Y-%m-%dT%H:%M")
    return templates.TemplateResponse(
        request,
        "entries/edit.html",
        {
            "entry": entry,
            "food": food,
            "current_user": user,
            "logged_at_local": logged_local,
            "meal_types": MEAL_TYPES,
        },
    )


@router.post("/entries/{entry_id}/edit")
async def edit_entry_submit(
    entry_id: int,
    amount_g: float = Form(..., gt=0),
    meal_type: Optional[str] = Form(None),
    notes: Optional[str] = Form(None),
    logged_at: Optional[str] = Form(None),
    db: AsyncSession = Depends(get_session),
    user: User = Depends(require_user),
):
    entry = await db.get(Entry, entry_id)
    if entry is None or entry.user_id != user.id:
        raise HTTPException(404)
    if meal_type and meal_type not in MEAL_TYPES:
        meal_type = None
    parsed = _parse_logged_at(logged_at)
    logged_at_utc = (
        _localize_to_utc_naive(parsed, user) if parsed else entry.logged_at
    )
    await logsvc.update_entry(
        db,
        entry,
        amount_g=amount_g,
        meal_type=meal_type,
        notes=notes,
        logged_at=logged_at_utc,
    )
    await db.commit()
    return RedirectResponse("/today", status_code=303)


@router.post("/entries/{entry_id}/delete")
async def delete_entry_submit(
    entry_id: int,
    db: AsyncSession = Depends(get_session),
    user: User = Depends(require_user),
):
    entry = await db.get(Entry, entry_id)
    if entry is None or entry.user_id != user.id:
        raise HTTPException(404)
    await logsvc.delete_entry(db, entry)
    await db.commit()
    return RedirectResponse("/today", status_code=303)
