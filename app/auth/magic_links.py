"""Magic link issuance and consumption."""

import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import MagicLink, User

_LIFETIME = timedelta(days=7)


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


async def create_magic_link(session: AsyncSession, user: User) -> MagicLink:
    """Generate a magic link for the user. Invalidates any prior unused link."""
    existing = (
        await session.execute(
            select(MagicLink)
            .where(MagicLink.user_id == user.id, MagicLink.used_at.is_(None))
        )
    ).scalars().all()
    now = _now()
    for link in existing:
        link.used_at = now

    token = secrets.token_urlsafe(32)
    link = MagicLink(
        user_id=user.id,
        token=token,
        expires_at=now + _LIFETIME,
    )
    session.add(link)
    await session.flush()
    return link


async def find_valid_link(session: AsyncSession, token: str) -> MagicLink | None:
    """Return the link if it exists, hasn't been used, and hasn't expired."""
    link = (
        await session.execute(select(MagicLink).where(MagicLink.token == token))
    ).scalar_one_or_none()
    if link is None or link.used_at is not None:
        return None
    if link.expires_at <= _now():
        return None
    return link


async def consume_link(session: AsyncSession, link: MagicLink) -> None:
    link.used_at = _now()
