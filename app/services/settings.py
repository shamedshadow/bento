"""Profile + danger-zone helpers."""

from typing import Optional

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Entry, Session, User
from app.models.user import PRIMARY_METRICS, SECONDARY_TARGET_TYPES


def update_profile(
    user: User,
    *,
    name: str,
    primary_metric: str,
    daily_target_primary: int,
    secondary_metric: Optional[str],
    secondary_target: Optional[int],
    secondary_target_type: Optional[str],
    timezone: str,
) -> None:
    user.name = name.strip() or user.name
    if primary_metric in PRIMARY_METRICS:
        user.primary_metric = primary_metric
    if daily_target_primary > 0:
        user.daily_target_primary = int(daily_target_primary)

    sec = (secondary_metric or "").strip()
    user.secondary_metric = sec if sec in PRIMARY_METRICS else None
    if user.secondary_metric is None:
        user.secondary_target = None
        user.secondary_target_type = None
    else:
        user.secondary_target = (
            int(secondary_target)
            if secondary_target is not None and secondary_target > 0
            else None
        )
        user.secondary_target_type = (
            secondary_target_type
            if secondary_target_type in SECONDARY_TARGET_TYPES
            else None
        )

    if timezone:
        user.timezone = timezone.strip()


async def sign_out_everywhere(
    session: AsyncSession, user_id: int, except_token: Optional[str] = None
) -> int:
    """Delete all session rows for this user. Returns count deleted."""
    stmt = delete(Session).where(Session.user_id == user_id)
    if except_token:
        stmt = stmt.where(Session.token != except_token)
    result = await session.execute(stmt)
    return result.rowcount or 0


async def delete_all_entries(
    session: AsyncSession, user_id: int
) -> int:
    result = await session.execute(
        delete(Entry).where(Entry.user_id == user_id)
    )
    return result.rowcount or 0
