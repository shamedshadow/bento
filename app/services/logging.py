"""Entry creation, querying, and totals computation."""

from datetime import date, datetime, time, timedelta, timezone
from typing import Optional
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Entry, Food, User


def _now_utc_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _user_tz(user: User) -> ZoneInfo:
    try:
        return ZoneInfo(user.timezone or "UTC")
    except Exception:
        return ZoneInfo("UTC")


def user_today(user: User, now_utc: Optional[datetime] = None) -> date:
    """Today in the user's local timezone."""
    now_utc = now_utc or datetime.now(timezone.utc)
    return now_utc.astimezone(_user_tz(user)).date()


def local_day_bounds_utc(
    user: User, day: date
) -> tuple[datetime, datetime]:
    """[start, end) of `day` in user-local time, returned as naive UTC."""
    tz = _user_tz(user)
    start_local = datetime.combine(day, time.min, tzinfo=tz)
    end_local = start_local + timedelta(days=1)
    start_utc = start_local.astimezone(timezone.utc).replace(tzinfo=None)
    end_utc = end_local.astimezone(timezone.utc).replace(tzinfo=None)
    return start_utc, end_utc


async def create_entry(
    session: AsyncSession,
    *,
    user_id: int,
    food_id: int,
    amount_g: float,
    meal_type: Optional[str] = None,
    notes: Optional[str] = None,
    logged_at: Optional[datetime] = None,
) -> Entry:
    entry = Entry(
        user_id=user_id,
        food_id=food_id,
        amount_g=amount_g,
        meal_type=meal_type,
        notes=(notes or "").strip() or None,
        logged_at=logged_at or _now_utc_naive(),
    )
    session.add(entry)
    await session.flush()
    return entry


async def list_entries_with_foods(
    session: AsyncSession, user: User, day: date
) -> list[tuple[Entry, Food]]:
    start, end = local_day_bounds_utc(user, day)
    rows = (
        await session.execute(
            select(Entry, Food)
            .join(Food, Food.id == Entry.food_id)
            .where(
                Entry.user_id == user.id,
                Entry.logged_at >= start,
                Entry.logged_at < end,
            )
            .order_by(Entry.logged_at)
        )
    ).all()
    return [(r[0], r[1]) for r in rows]


def compute_nutrients(food: Food, amount_g: float) -> dict:
    """Per-100g values × amount_g/100. Net carbs computed at display time."""
    factor = amount_g / 100.0

    def _scale(v: Optional[float]) -> Optional[float]:
        return None if v is None else v * factor

    carbs = _scale(food.carbs_per_100g)
    fiber = _scale(food.fiber_per_100g)
    net_carbs = None
    if carbs is not None:
        net_carbs = max(0.0, carbs - (fiber or 0.0))

    return {
        "calories": _scale(food.calories_per_100g),
        "carbs": carbs,
        "fiber": fiber,
        "net_carbs": net_carbs,
        "protein": _scale(food.protein_per_100g),
        "fat": _scale(food.fat_per_100g),
        "sugar": _scale(food.sugar_per_100g),
        "sodium": _scale(food.sodium_per_100g),
    }


def daily_totals(pairs: list[tuple[Entry, Food]]) -> dict:
    """Sum nutrients across (entry, food) pairs for the day."""
    total = {k: 0.0 for k in (
        "calories", "carbs", "fiber", "net_carbs",
        "protein", "fat", "sugar", "sodium",
    )}
    has_value = {k: False for k in total}
    for entry, food in pairs:
        n = compute_nutrients(food, entry.amount_g)
        for k, v in n.items():
            if v is not None:
                total[k] += v
                has_value[k] = True
    return {k: (total[k] if has_value[k] else None) for k in total}


async def update_entry(
    session: AsyncSession,
    entry: Entry,
    *,
    amount_g: Optional[float] = None,
    meal_type: Optional[str] = None,
    notes: Optional[str] = None,
    logged_at: Optional[datetime] = None,
) -> Entry:
    if amount_g is not None:
        entry.amount_g = amount_g
    if meal_type is not None:
        entry.meal_type = meal_type or None
    if notes is not None:
        entry.notes = notes.strip() or None
    if logged_at is not None:
        entry.logged_at = logged_at
    await session.flush()
    return entry


async def delete_entry(session: AsyncSession, entry: Entry) -> None:
    await session.delete(entry)
