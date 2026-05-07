"""Food edit + delete (custom foods only). Synced sources are managed by their
respective integrations and shouldn't be hand-edited — re-sync would clobber
the changes.
"""

from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Entry, Food, SavedMealItem


async def update_custom(
    session: AsyncSession,
    food: Food,
    *,
    name: str,
    brand: Optional[str],
    default_serving_g: Optional[float],
    default_serving_label: Optional[str],
    calories_per_100g: float,
    carbs_per_100g: float,
    fiber_per_100g: Optional[float] = None,
    protein_per_100g: Optional[float] = None,
    fat_per_100g: Optional[float] = None,
    sugar_per_100g: Optional[float] = None,
    sodium_per_100g: Optional[float] = None,
) -> Food:
    food.name = name.strip()
    food.brand = (brand or "").strip() or None
    food.default_serving_g = default_serving_g
    food.default_serving_label = (default_serving_label or "").strip() or None
    food.calories_per_100g = calories_per_100g
    food.carbs_per_100g = carbs_per_100g
    food.fiber_per_100g = fiber_per_100g
    food.protein_per_100g = protein_per_100g
    food.fat_per_100g = fat_per_100g
    food.sugar_per_100g = sugar_per_100g
    food.sodium_per_100g = sodium_per_100g
    await session.flush()
    return food


async def reference_counts(
    session: AsyncSession, food_id: int
) -> tuple[int, int]:
    """Returns (entries, saved_meal_items) — non-zero means delete should refuse."""
    entries = (
        await session.execute(
            select(func.count(Entry.id)).where(Entry.food_id == food_id)
        )
    ).scalar_one()
    items = (
        await session.execute(
            select(func.count(SavedMealItem.id)).where(SavedMealItem.food_id == food_id)
        )
    ).scalar_one()
    return entries, items


async def delete_custom(
    session: AsyncSession, food: Food
) -> tuple[bool, str]:
    """Delete a custom food, refusing if it's referenced. Favorites cascade
    automatically via FK ondelete=CASCADE.
    """
    if food.source != "custom":
        return False, "Only custom foods can be deleted."
    entries, items = await reference_counts(session, food.id)
    if entries:
        return False, (
            f"Can't delete — used in {entries} entr{'y' if entries == 1 else 'ies'}. "
            "Delete those entries first."
        )
    if items:
        return False, (
            f"Can't delete — used in {items} saved-meal item{'' if items == 1 else 's'}. "
            "Remove from saved meals first."
        )
    await session.delete(food)
    return True, "Deleted."
