"""CSV export for entries. Streamed so big exports don't sit in memory."""

import csv
import io
from datetime import date, datetime, timezone
from typing import AsyncIterator, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Entry, Food, User
from app.services import logging as log_svc

CSV_COLUMNS = [
    "logged_at",
    "meal_type",
    "food_name",
    "brand",
    "amount_g",
    "calories",
    "carbs",
    "fiber",
    "net_carbs",
    "protein",
    "fat",
    "sugar",
    "sodium",
    "notes",
]


def _round(value, ndigits: int = 2):
    if value is None:
        return ""
    return round(value, ndigits)


async def stream_entries_csv(
    session: AsyncSession,
    user: User,
    *,
    start_day: Optional[date] = None,
    end_day: Optional[date] = None,
) -> AsyncIterator[str]:
    """Yield CSV text in chunks. Includes UTF-8 BOM so Excel opens it cleanly.

    `start_day`/`end_day` are inclusive in the user's local timezone. Either
    can be None for open-ended.
    """
    # Header (with UTF-8 BOM as the very first chunk for Excel).
    header_buf = io.StringIO()
    header_buf.write("﻿")
    writer = csv.writer(header_buf, lineterminator="\n")
    writer.writerow(CSV_COLUMNS)
    yield header_buf.getvalue()

    # Build the query with optional date bounds.
    stmt = (
        select(Entry, Food)
        .join(Food, Food.id == Entry.food_id)
        .where(Entry.user_id == user.id)
        .order_by(Entry.logged_at)
    )
    if start_day is not None:
        start_utc, _ = log_svc.local_day_bounds_utc(user, start_day)
        stmt = stmt.where(Entry.logged_at >= start_utc)
    if end_day is not None:
        _, end_utc = log_svc.local_day_bounds_utc(user, end_day)
        stmt = stmt.where(Entry.logged_at < end_utc)

    tz = log_svc._user_tz(user)
    rows = (await session.execute(stmt)).all()

    # Chunk every 200 rows so we don't accumulate a huge string.
    buf = io.StringIO()
    chunk_writer = csv.writer(buf, lineterminator="\n")
    written = 0
    for entry, food in rows:
        n = log_svc.compute_nutrients(food, entry.amount_g)
        local_dt = entry.logged_at.replace(tzinfo=timezone.utc).astimezone(tz)
        chunk_writer.writerow(
            [
                local_dt.strftime("%Y-%m-%d %H:%M:%S"),
                entry.meal_type or "",
                food.name,
                food.brand or "",
                _round(entry.amount_g, 2),
                _round(n.get("calories"), 1),
                _round(n.get("carbs"), 2),
                _round(n.get("fiber"), 2),
                _round(n.get("net_carbs"), 2),
                _round(n.get("protein"), 2),
                _round(n.get("fat"), 2),
                _round(n.get("sugar"), 2),
                _round(n.get("sodium"), 4),
                (entry.notes or "").replace("\r", " ").replace("\n", " "),
            ]
        )
        written += 1
        if written % 200 == 0:
            yield buf.getvalue()
            buf = io.StringIO()
            chunk_writer = csv.writer(buf, lineterminator="\n")

    tail = buf.getvalue()
    if tail:
        yield tail


def filename_for(user: User) -> str:
    today = datetime.now(log_svc._user_tz(user)).strftime("%Y-%m-%d")
    safe_name = "".join(c if c.isalnum() else "_" for c in user.name).strip("_") or "user"
    return f"bento-{safe_name}-{today}.csv"
