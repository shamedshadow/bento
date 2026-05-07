"""Favorite toggle + listing."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Favorite, Food


async def is_favorited(
    session: AsyncSession, user_id: int, food_id: int
) -> bool:
    row = (
        await session.execute(
            select(Favorite).where(
                Favorite.user_id == user_id, Favorite.food_id == food_id
            )
        )
    ).scalar_one_or_none()
    return row is not None


async def toggle(
    session: AsyncSession, user_id: int, food_id: int
) -> bool:
    row = (
        await session.execute(
            select(Favorite).where(
                Favorite.user_id == user_id, Favorite.food_id == food_id
            )
        )
    ).scalar_one_or_none()
    if row is None:
        session.add(Favorite(user_id=user_id, food_id=food_id))
        await session.flush()
        return True
    await session.delete(row)
    return False


async def list_for_user(
    session: AsyncSession, user_id: int
) -> list[Food]:
    rows = (
        await session.execute(
            select(Food)
            .join(Favorite, Favorite.food_id == Food.id)
            .where(Favorite.user_id == user_id)
            .order_by(Favorite.created_at.desc())
        )
    ).scalars().all()
    return list(rows)
