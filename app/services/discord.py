"""Discord webhook helpers. Sending real reminders is F8; for F7 we just send a
generic 'Bento is connected' test message used by /settings/test-webhook and on
URL save (acceptance criterion: 'triggers a test message before persisting').
"""

import json
import logging
from typing import Optional

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import DiscordSettings, User

logger = logging.getLogger(__name__)


async def get_settings(
    session: AsyncSession, user_id: int
) -> Optional[DiscordSettings]:
    return (
        await session.execute(
            select(DiscordSettings).where(DiscordSettings.user_id == user_id)
        )
    ).scalar_one_or_none()


async def ensure_settings(session: AsyncSession, user_id: int) -> DiscordSettings:
    existing = await get_settings(session, user_id)
    if existing is not None:
        return existing
    row = DiscordSettings(user_id=user_id)
    session.add(row)
    await session.flush()
    return row


async def send_test(webhook_url: str, user: User) -> tuple[bool, str]:
    """POST a small embed to verify the URL works. Returns (ok, message)."""
    if not webhook_url:
        return False, "No webhook URL provided."
    payload = {
        "username": "Bento",
        "embeds": [
            {
                "title": "Bento is connected",
                "description": (
                    f"Test message from Bento for **{user.name}**. "
                    "Reminders you enable will arrive here."
                ),
                "color": 0x968C6E,
            }
        ],
    }
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(webhook_url, json=payload)
            if 200 <= resp.status_code < 300:
                return True, "Test message sent."
            return False, f"Discord returned {resp.status_code}: {resp.text[:200]}"
    except httpx.HTTPError as e:
        logger.warning("Discord webhook test failed: %s", e)
        return False, f"Network error: {e}"


def parse_meal_times(value: str) -> list[str]:
    """Accept 'HH:MM,HH:MM,...' or JSON list. Return validated list."""
    if not value:
        return []
    value = value.strip()
    parts: list[str]
    if value.startswith("["):
        try:
            parsed = json.loads(value)
            parts = [str(p) for p in parsed]
        except json.JSONDecodeError:
            return []
    else:
        parts = [p.strip() for p in value.split(",") if p.strip()]
    out: list[str] = []
    for p in parts:
        if _valid_hhmm(p):
            out.append(p)
    return out


def _valid_hhmm(s: str) -> bool:
    if len(s) != 5 or s[2] != ":":
        return False
    try:
        h, m = int(s[:2]), int(s[3:])
        return 0 <= h <= 23 and 0 <= m <= 59
    except ValueError:
        return False


def serialize_meal_times(times: list[str]) -> str:
    return json.dumps(times)


def deserialize_meal_times(stored: Optional[str]) -> list[str]:
    if not stored:
        return []
    try:
        parsed = json.loads(stored)
        return [str(t) for t in parsed if _valid_hhmm(str(t))]
    except json.JSONDecodeError:
        return []
