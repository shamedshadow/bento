from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import require_user
from app.db import get_session
from app.models import Food, User
from app.services import nutrition

router = APIRouter()
templates = Jinja2Templates(directory="templates")


def _serialize(food: Food) -> dict:
    return {
        "id": food.id,
        "source": food.source,
        "source_id": food.source_id,
        "barcode": food.barcode,
        "name": food.name,
        "brand": food.brand,
        "default_serving_g": food.default_serving_g,
        "default_serving_label": food.default_serving_label,
        "calories_per_100g": food.calories_per_100g,
        "carbs_per_100g": food.carbs_per_100g,
        "fiber_per_100g": food.fiber_per_100g,
        "net_carbs_per_100g": food.net_carbs_per_100g,
        "protein_per_100g": food.protein_per_100g,
        "fat_per_100g": food.fat_per_100g,
        "sugar_per_100g": food.sugar_per_100g,
        "sodium_per_100g": food.sodium_per_100g,
    }


# ----- JSON API --------------------------------------------------------------


@router.get("/api/foods/lookup")
async def api_lookup(
    barcode: str = Query(..., min_length=4),
    db: AsyncSession = Depends(get_session),
    _: User = Depends(require_user),
):
    food = await nutrition.lookup_by_barcode(db, barcode)
    await db.commit()
    if food is None:
        raise HTTPException(status_code=404, detail="Not found")
    return _serialize(food)


@router.get("/api/foods/search")
async def api_search(
    q: str = Query("", min_length=0),
    db: AsyncSession = Depends(get_session),
    _: User = Depends(require_user),
):
    rows = await nutrition.search_local(db, q)
    return {"results": [_serialize(f) for f in rows]}


@router.post("/api/foods/custom")
async def api_create_custom(
    name: str = Form(...),
    calories_per_100g: float = Form(...),
    carbs_per_100g: float = Form(...),
    brand: str | None = Form(None),
    default_serving_g: float | None = Form(None),
    default_serving_label: str | None = Form(None),
    fiber_per_100g: float | None = Form(None),
    protein_per_100g: float | None = Form(None),
    fat_per_100g: float | None = Form(None),
    sugar_per_100g: float | None = Form(None),
    sodium_per_100g: float | None = Form(None),
    db: AsyncSession = Depends(get_session),
    user: User = Depends(require_user),
):
    food = await nutrition.create_custom_food(
        db,
        user_id=user.id,
        name=name,
        brand=brand,
        default_serving_g=default_serving_g,
        default_serving_label=default_serving_label,
        calories_per_100g=calories_per_100g,
        carbs_per_100g=carbs_per_100g,
        fiber_per_100g=fiber_per_100g,
        protein_per_100g=protein_per_100g,
        fat_per_100g=fat_per_100g,
        sugar_per_100g=sugar_per_100g,
        sodium_per_100g=sodium_per_100g,
    )
    await db.commit()
    return _serialize(food)


# ----- HTML pages ------------------------------------------------------------


@router.get("/foods")
async def foods_index(
    request: Request,
    user: User = Depends(require_user),
):
    return templates.TemplateResponse(
        request, "foods/index.html", {"current_user": user}
    )


@router.get("/foods/search-results")
async def foods_search_results(
    request: Request,
    q: str = Query("", min_length=0),
    db: AsyncSession = Depends(get_session),
    user: User = Depends(require_user),
):
    rows = await nutrition.search_local(db, q)
    return templates.TemplateResponse(
        request,
        "foods/_search_results.html",
        {"results": rows, "q": q},
    )


@router.get("/foods/scan")
async def foods_scan(
    request: Request,
    user: User = Depends(require_user),
):
    return templates.TemplateResponse(
        request, "foods/scan.html", {"current_user": user}
    )


@router.get("/foods/new")
async def foods_new(
    request: Request,
    user: User = Depends(require_user),
    barcode: str | None = Query(None),
):
    return templates.TemplateResponse(
        request,
        "foods/new.html",
        {"current_user": user, "error": None, "form": {"barcode": barcode}},
    )


@router.post("/foods/new")
async def foods_new_submit(
    request: Request,
    name: str = Form(...),
    calories_per_100g: float = Form(...),
    carbs_per_100g: float = Form(...),
    brand: str | None = Form(None),
    default_serving_g: float | None = Form(None),
    default_serving_label: str | None = Form(None),
    fiber_per_100g: float | None = Form(None),
    protein_per_100g: float | None = Form(None),
    fat_per_100g: float | None = Form(None),
    sugar_per_100g: float | None = Form(None),
    sodium_per_100g: float | None = Form(None),
    db: AsyncSession = Depends(get_session),
    user: User = Depends(require_user),
):
    food = await nutrition.create_custom_food(
        db,
        user_id=user.id,
        name=name,
        brand=brand,
        default_serving_g=default_serving_g,
        default_serving_label=default_serving_label,
        calories_per_100g=calories_per_100g,
        carbs_per_100g=carbs_per_100g,
        fiber_per_100g=fiber_per_100g,
        protein_per_100g=protein_per_100g,
        fat_per_100g=fat_per_100g,
        sugar_per_100g=sugar_per_100g,
        sodium_per_100g=sodium_per_100g,
    )
    await db.commit()
    return RedirectResponse(f"/foods/{food.id}", status_code=303)


@router.get("/foods/{food_id}")
async def foods_detail(
    food_id: int,
    request: Request,
    db: AsyncSession = Depends(get_session),
    user: User = Depends(require_user),
):
    food = await db.get(Food, food_id)
    if food is None:
        raise HTTPException(status_code=404)
    return templates.TemplateResponse(
        request, "foods/detail.html", {"food": food, "current_user": user}
    )
