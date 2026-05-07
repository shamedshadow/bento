"""DB-backed sessions.

Cookie carries a random token; the truth lives in the `sessions` table. Sliding
expiry — accessed sessions get extended back out to the full lifetime, but only
when they're more than `_REFRESH_THRESHOLD` past their last refresh, to avoid a
write per request.

Also exposes a session-secret helper used to seed a Starlette signing key if we
ever need one. Currently unused — kept here so a future feature (signed flash
messages, etc.) doesn't have to re-invent it.
"""

import secrets
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import Session as SessionModel
from app.models import User

SESSION_COOKIE_NAME = "bento_session"
_LIFETIME = timedelta(days=90)
_REFRESH_THRESHOLD = timedelta(days=1)


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


async def create_session(session: AsyncSession, user: User) -> SessionModel:
    token = secrets.token_urlsafe(32)
    row = SessionModel(
        user_id=user.id,
        token=token,
        expires_at=_now() + _LIFETIME,
    )
    session.add(row)
    await session.flush()
    return row


async def lookup_session(
    session: AsyncSession, token: str
) -> tuple[SessionModel, User] | None:
    row = (
        await session.execute(
            select(SessionModel).where(SessionModel.token == token)
        )
    ).scalar_one_or_none()
    if row is None:
        return None
    now = _now()
    if row.expires_at <= now:
        await session.delete(row)
        return None
    user = await session.get(User, row.user_id)
    if user is None or not user.is_active:
        return None

    # Sliding expiry — only write if the session is close to or past its
    # refresh threshold to avoid a write per request.
    if row.expires_at - now < _LIFETIME - _REFRESH_THRESHOLD:
        row.expires_at = now + _LIFETIME

    return row, user


async def destroy_session(session: AsyncSession, token: str) -> None:
    row = (
        await session.execute(
            select(SessionModel).where(SessionModel.token == token)
        )
    ).scalar_one_or_none()
    if row is not None:
        await session.delete(row)


def cookie_max_age_seconds() -> int:
    return int(_LIFETIME.total_seconds())


# --- Session secret (for future signing needs; not used by DB-backed sessions) ---


def _db_file_path() -> Path:
    url = settings.database_url
    marker = "sqlite+aiosqlite:///"
    if not url.startswith(marker):
        raise RuntimeError(f"Unsupported database URL: {url}")
    return Path(url[len(marker):]).resolve()


def _load_or_create_secret_sync() -> str:
    db_path = _db_file_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS app_settings ("
            "key TEXT PRIMARY KEY, value TEXT, "
            "updated_at DATETIME DEFAULT CURRENT_TIMESTAMP)"
        )
        row = conn.execute(
            "SELECT value FROM app_settings WHERE key = ?", ("session_secret",)
        ).fetchone()
        if row and row[0]:
            return row[0]
        generated = secrets.token_urlsafe(48)
        conn.execute(
            "INSERT OR REPLACE INTO app_settings (key, value) VALUES (?, ?)",
            ("session_secret", generated),
        )
        conn.commit()
        return generated
    finally:
        conn.close()


def resolve_session_secret() -> str:
    if settings.session_secret:
        return settings.session_secret
    return _load_or_create_secret_sync()
