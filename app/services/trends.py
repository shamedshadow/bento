"""Trends data: daily series, rolling average, summary stats, per-meal scatter.

All numbers are computed at display time from raw entries — net carbs included.
"""

from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Entry, Food, User
from app.services import logging as log_svc

_METRIC_KEY = {
    "calories": "calories",
    "net_carbs": "net_carbs",
    "total_carbs": "carbs",
    "protein": "protein",
}


async def _entries_in_range(
    session: AsyncSession, user: User, start_day: date, end_day: date
) -> list[tuple[Entry, Food]]:
    """Inclusive range of user-local days. Returns (entry, food) pairs ordered by logged_at."""
    start_utc, _ = log_svc.local_day_bounds_utc(user, start_day)
    _, end_utc = log_svc.local_day_bounds_utc(user, end_day)
    rows = (
        await session.execute(
            select(Entry, Food)
            .join(Food, Food.id == Entry.food_id)
            .where(
                Entry.user_id == user.id,
                Entry.logged_at >= start_utc,
                Entry.logged_at < end_utc,
            )
            .order_by(Entry.logged_at)
        )
    ).all()
    return [(r[0], r[1]) for r in rows]


def _entry_local_date(entry: Entry, user: User) -> date:
    return (
        entry.logged_at.replace(tzinfo=timezone.utc)
        .astimezone(log_svc._user_tz(user))
        .date()
    )


async def daily_series(
    session: AsyncSession, user: User, days: int
) -> list[tuple[date, float]]:
    """Daily totals of the user's primary metric, oldest first. Empty days = 0."""
    today = log_svc.user_today(user)
    start_day = today - timedelta(days=days - 1)
    pairs = await _entries_in_range(session, user, start_day, today)

    metric_key = _METRIC_KEY.get(user.primary_metric, "calories")
    bucket: dict[date, float] = {}
    for entry, food in pairs:
        d = _entry_local_date(entry, user)
        n = log_svc.compute_nutrients(food, entry.amount_g)
        v = n.get(metric_key)
        if v is not None:
            bucket[d] = bucket.get(d, 0.0) + v

    result: list[tuple[date, float]] = []
    cur = start_day
    while cur <= today:
        result.append((cur, bucket.get(cur, 0.0)))
        cur = cur + timedelta(days=1)
    return result


def rolling_average(
    series: list[tuple[date, float]], window: int = 7
) -> list[tuple[date, float]]:
    """7-day trailing average."""
    out: list[tuple[date, float]] = []
    for i, (d, _) in enumerate(series):
        start = max(0, i - window + 1)
        window_vals = [v for _, v in series[start : i + 1]]
        out.append((d, sum(window_vals) / len(window_vals)))
    return out


def summary_stats(
    series: list[tuple[date, float]], target: float
) -> dict:
    """Descriptive observations only — no judgement framing."""
    if not series:
        return {
            "avg": None,
            "days_logged": 0,
            "days_under_or_at": 0,
            "days_over": 0,
            "longest_under_or_at_streak": 0,
        }
    # "Days logged" = days with any data; everything else is computed across all
    # days in the window so the user sees the full picture.
    days_logged = sum(1 for _, v in series if v > 0)
    vals = [v for _, v in series]
    avg = sum(vals) / len(vals)
    days_under = sum(1 for v in vals if v <= target)
    days_over = sum(1 for v in vals if v > target)

    longest = streak = 0
    for v in vals:
        if v <= target:
            streak += 1
            longest = max(longest, streak)
        else:
            streak = 0

    return {
        "avg": avg,
        "days_logged": days_logged,
        "days_under_or_at": days_under,
        "days_over": days_over,
        "longest_under_or_at_streak": longest,
    }


async def per_meal_scatter(
    session: AsyncSession, user: User, days: int = 14
) -> list[dict]:
    """One point per entry for the last `days` days. For carb-tracking users,
    timing matters as much as daily totals.
    """
    today = log_svc.user_today(user)
    start_day = today - timedelta(days=days - 1)
    pairs = await _entries_in_range(session, user, start_day, today)
    metric_key = _METRIC_KEY.get(user.primary_metric, "calories")

    points: list[dict] = []
    for entry, food in pairs:
        local = entry.logged_at.replace(tzinfo=timezone.utc).astimezone(
            log_svc._user_tz(user)
        )
        n = log_svc.compute_nutrients(food, entry.amount_g)
        v = n.get(metric_key)
        if v is None:
            continue
        points.append(
            {
                "iso": local.isoformat(),
                "value": v,
                "meal_type": entry.meal_type or "other",
            }
        )
    return points
