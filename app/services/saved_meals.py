"""Saved meals: create (manual or from a logged day), list, log out as entries."""

from datetime import date, datetime
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import Entry, Food, SavedMeal, SavedMealItem, User
from app.models.entry import MEAL_TYPES
from app.services import logging as log_svc


async def list_for_user(
    session: AsyncSession, user_id: int
) -> list[SavedMeal]:
    rows = (
        await session.execute(
            select(SavedMeal)
            .where(SavedMeal.user_id == user_id)
            .options(selectinload(SavedMeal.items))
            .order_by(SavedMeal.created_at.desc())
        )
    ).scalars().all()
    return list(rows)


async def get_for_user(
    session: AsyncSession, user_id: int, saved_meal_id: int
) -> Optional[SavedMeal]:
    row = (
        await session.execute(
            select(SavedMeal)
            .where(SavedMeal.id == saved_meal_id, SavedMeal.user_id == user_id)
            .options(selectinload(SavedMeal.items))
        )
    ).scalar_one_or_none()
    return row


async def create(
    session: AsyncSession,
    *,
    user_id: int,
    name: str,
    default_meal_type: Optional[str] = None,
) -> SavedMeal:
    sm = SavedMeal(
        user_id=user_id,
        name=name.strip(),
        default_meal_type=default_meal_type if default_meal_type in MEAL_TYPES else None,
    )
    session.add(sm)
    await session.flush()
    return sm


async def add_item(
    session: AsyncSession,
    saved_meal: SavedMeal,
    *,
    food_id: int,
    amount_g: float,
) -> SavedMealItem:
    next_order = max((it.display_order for it in saved_meal.items), default=-1) + 1
    item = SavedMealItem(
        saved_meal_id=saved_meal.id,
        food_id=food_id,
        amount_g=amount_g,
        display_order=next_order,
    )
    session.add(item)
    await session.flush()
    return item


async def remove_item(
    session: AsyncSession, saved_meal: SavedMeal, item_id: int
) -> bool:
    for it in saved_meal.items:
        if it.id == item_id:
            await session.delete(it)
            return True
    return False


async def rename(
    session: AsyncSession,
    saved_meal: SavedMeal,
    *,
    name: str,
    default_meal_type: Optional[str] = None,
) -> SavedMeal:
    saved_meal.name = name.strip()
    if default_meal_type is None or default_meal_type == "":
        saved_meal.default_meal_type = None
    elif default_meal_type in MEAL_TYPES:
        saved_meal.default_meal_type = default_meal_type
    await session.flush()
    return saved_meal


async def delete(session: AsyncSession, saved_meal: SavedMeal) -> None:
    await session.delete(saved_meal)


async def create_from_day(
    session: AsyncSession,
    *,
    user: User,
    day: date,
    meal_type: Optional[str],
    name: str,
) -> Optional[SavedMeal]:
    """Build a saved meal from the entries already logged on `day` for `meal_type`.
    `meal_type=None` captures un-categorised entries.
    """
    pairs = await log_svc.list_entries_with_foods(session, user, day)
    selected = [(e, f) for e, f in pairs if e.meal_type == meal_type]
    if not selected:
        return None

    sm = await create(
        session,
        user_id=user.id,
        name=name,
        default_meal_type=meal_type,
    )
    for idx, (entry, _food) in enumerate(selected):
        session.add(
            SavedMealItem(
                saved_meal_id=sm.id,
                food_id=entry.food_id,
                amount_g=entry.amount_g,
                display_order=idx,
            )
        )
    await session.flush()
    # Re-fetch with items eager-loaded
    return await get_for_user(session, user.id, sm.id)


async def log_as_entries(
    session: AsyncSession,
    saved_meal: SavedMeal,
    *,
    user: User,
    meal_type: Optional[str] = None,
    logged_at: Optional[datetime] = None,
) -> list[Entry]:
    """Create entries for each item in one transaction."""
    effective_meal = meal_type if meal_type in MEAL_TYPES else saved_meal.default_meal_type
    when = logged_at  # None means use create_entry's default (now)
    created: list[Entry] = []
    for item in saved_meal.items:
        e = await log_svc.create_entry(
            session,
            user_id=user.id,
            food_id=item.food_id,
            amount_g=item.amount_g,
            meal_type=effective_meal,
            logged_at=when,
        )
        created.append(e)
    return created


async def items_with_foods(
    session: AsyncSession, saved_meal: SavedMeal
) -> list[tuple[SavedMealItem, Food]]:
    if not saved_meal.items:
        return []
    food_ids = [it.food_id for it in saved_meal.items]
    foods = (
        await session.execute(select(Food).where(Food.id.in_(food_ids)))
    ).scalars().all()
    food_map = {f.id: f for f in foods}
    return [(it, food_map[it.food_id]) for it in saved_meal.items if it.food_id in food_map]
