from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import require_user
from app.db import get_session
from app.models import Food, User
from app.models.entry import MEAL_TYPES
from app.services import nutrition
from app.services import saved_meals as svc

router = APIRouter(prefix="/saved-meals")
templates = Jinja2Templates(directory="templates")


@router.get("")
async def list_page(
    request: Request,
    db: AsyncSession = Depends(get_session),
    user: User = Depends(require_user),
):
    meals = await svc.list_for_user(db, user.id)
    return templates.TemplateResponse(
        request,
        "saved_meals/index.html",
        {"current_user": user, "meals": meals},
    )


@router.get("/new")
async def new_form(
    request: Request,
    user: User = Depends(require_user),
):
    return templates.TemplateResponse(
        request,
        "saved_meals/new.html",
        {"current_user": user, "meal_types": MEAL_TYPES},
    )


@router.post("")
async def create_submit(
    name: str = Form(...),
    default_meal_type: Optional[str] = Form(None),
    db: AsyncSession = Depends(get_session),
    user: User = Depends(require_user),
):
    if not name.strip():
        return RedirectResponse("/saved-meals/new", status_code=303)
    sm = await svc.create(
        db,
        user_id=user.id,
        name=name,
        default_meal_type=default_meal_type,
    )
    await db.commit()
    return RedirectResponse(f"/saved-meals/{sm.id}", status_code=303)


@router.get("/{saved_meal_id}")
async def detail_page(
    saved_meal_id: int,
    request: Request,
    db: AsyncSession = Depends(get_session),
    user: User = Depends(require_user),
):
    sm = await svc.get_for_user(db, user.id, saved_meal_id)
    if sm is None:
        raise HTTPException(404)
    items_with_foods = await svc.items_with_foods(db, sm)
    return templates.TemplateResponse(
        request,
        "saved_meals/detail.html",
        {
            "current_user": user,
            "meal": sm,
            "items": items_with_foods,
            "meal_types": MEAL_TYPES,
        },
    )


@router.post("/{saved_meal_id}/rename")
async def rename_submit(
    saved_meal_id: int,
    name: str = Form(...),
    default_meal_type: Optional[str] = Form(None),
    db: AsyncSession = Depends(get_session),
    user: User = Depends(require_user),
):
    sm = await svc.get_for_user(db, user.id, saved_meal_id)
    if sm is None:
        raise HTTPException(404)
    await svc.rename(db, sm, name=name, default_meal_type=default_meal_type)
    await db.commit()
    return RedirectResponse(f"/saved-meals/{sm.id}", status_code=303)


@router.post("/{saved_meal_id}/items")
async def add_item_submit(
    saved_meal_id: int,
    food_id: int = Form(...),
    amount_g: float = Form(..., gt=0),
    db: AsyncSession = Depends(get_session),
    user: User = Depends(require_user),
):
    sm = await svc.get_for_user(db, user.id, saved_meal_id)
    if sm is None:
        raise HTTPException(404)
    food = await db.get(Food, food_id)
    if food is None:
        raise HTTPException(400, "Food not found")
    await svc.add_item(db, sm, food_id=food_id, amount_g=amount_g)
    await db.commit()
    return RedirectResponse(f"/saved-meals/{sm.id}", status_code=303)


@router.post("/{saved_meal_id}/items/{item_id}/delete")
async def delete_item_submit(
    saved_meal_id: int,
    item_id: int,
    db: AsyncSession = Depends(get_session),
    user: User = Depends(require_user),
):
    sm = await svc.get_for_user(db, user.id, saved_meal_id)
    if sm is None:
        raise HTTPException(404)
    await svc.remove_item(db, sm, item_id)
    await db.commit()
    return RedirectResponse(f"/saved-meals/{sm.id}", status_code=303)


@router.post("/{saved_meal_id}/log")
async def log_submit(
    saved_meal_id: int,
    meal_type: Optional[str] = Form(None),
    db: AsyncSession = Depends(get_session),
    user: User = Depends(require_user),
):
    sm = await svc.get_for_user(db, user.id, saved_meal_id)
    if sm is None:
        raise HTTPException(404)
    if not sm.items:
        return RedirectResponse(f"/saved-meals/{sm.id}", status_code=303)
    await svc.log_as_entries(db, sm, user=user, meal_type=meal_type)
    await db.commit()
    return RedirectResponse("/today", status_code=303)


@router.post("/{saved_meal_id}/delete")
async def delete_submit(
    saved_meal_id: int,
    db: AsyncSession = Depends(get_session),
    user: User = Depends(require_user),
):
    sm = await svc.get_for_user(db, user.id, saved_meal_id)
    if sm is None:
        raise HTTPException(404)
    await svc.delete(db, sm)
    await db.commit()
    return RedirectResponse("/saved-meals", status_code=303)


@router.post("/from-day")
async def from_day_submit(
    name: str = Form(...),
    day: str = Form(...),
    meal_type: Optional[str] = Form(None),
    db: AsyncSession = Depends(get_session),
    user: User = Depends(require_user),
):
    try:
        target = date.fromisoformat(day)
    except ValueError:
        raise HTTPException(400, "Invalid day")
    if not name.strip():
        return RedirectResponse(f"/today?day={day}", status_code=303)
    if meal_type == "":
        meal_type = None
    sm = await svc.create_from_day(
        db,
        user=user,
        day=target,
        meal_type=meal_type,
        name=name,
    )
    await db.commit()
    if sm is None:
        return RedirectResponse(f"/today?day={day}", status_code=303)
    return RedirectResponse(f"/saved-meals/{sm.id}", status_code=303)


# Helper to power the "add item" food picker on the detail page
@router.get("/{saved_meal_id}/item-search")
async def item_search(
    saved_meal_id: int,
    request: Request,
    q: str = Query("", min_length=0),
    db: AsyncSession = Depends(get_session),
    user: User = Depends(require_user),
):
    sm = await svc.get_for_user(db, user.id, saved_meal_id)
    if sm is None:
        raise HTTPException(404)
    rows = await nutrition.search_local(db, q)
    return templates.TemplateResponse(
        request,
        "saved_meals/_item_search.html",
        {"meal": sm, "results": rows, "q": q},
    )
