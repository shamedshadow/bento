"""Discord webhook client + embed builders for each reminder type."""

import json
import logging
from datetime import date
from typing import Optional

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import DiscordSettings, User

logger = logging.getLogger(__name__)

# Bento brand-ish neutral color for embed sidebars.
EMBED_COLOR = 0x968C6E


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


async def _post(webhook_url: str, payload: dict) -> tuple[bool, str]:
    """Bare POST to a webhook. Returns (ok, detail)."""
    if not webhook_url:
        return False, "No webhook URL provided."
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(webhook_url, json=payload)
            if 200 <= resp.status_code < 300:
                return True, "OK"
            return False, f"Discord returned {resp.status_code}: {resp.text[:200]}"
    except httpx.HTTPError as e:
        logger.warning("Discord webhook POST failed: %s", e)
        return False, f"Network error: {e}"


async def send_test(webhook_url: str, user: User) -> tuple[bool, str]:
    """Generic 'connected' test used on URL save (F7)."""
    payload = {
        "username": "Bento",
        "embeds": [
            {
                "title": "Bento is connected",
                "description": (
                    f"Test message from Bento for **{user.name}**. "
                    "Reminders you enable will arrive here."
                ),
                "color": EMBED_COLOR,
            }
        ],
    }
    ok, detail = await _post(webhook_url, payload)
    return ok, "Test message sent." if ok else detail


# ----- Reminder embeds (F8) -------------------------------------------------


def _label_metric(metric: str) -> str:
    return {
        "calories": "calories",
        "net_carbs": "g net carbs",
        "total_carbs": "g carbs",
        "protein": "g protein",
    }.get(metric, metric)


def _format_value(metric: str, value: Optional[float]) -> str:
    if value is None:
        return "—"
    if metric == "calories":
        return f"{round(value):.0f}"
    return f"{value:.1f}"


async def send_meal_nudge(
    webhook_url: str, user: User, meal_label: str
) -> tuple[bool, str]:
    """Plain content. Short and neutral."""
    payload = {
        "username": "Bento",
        "content": f"Time for {meal_label}, {user.name}?",
    }
    return await _post(webhook_url, payload)


async def send_eod_summary(
    webhook_url: str,
    user: User,
    day: date,
    totals: dict,
    primary_metric: str,
    primary_target: int,
) -> tuple[bool, str]:
    """Today's totals vs target. Descriptive language only — no judgement."""
    metric_key = {
        "calories": "calories",
        "net_carbs": "net_carbs",
        "total_carbs": "carbs",
        "protein": "protein",
    }.get(primary_metric, "calories")
    primary_value = totals.get(metric_key)

    fields = [
        {
            "name": primary_metric.replace("_", " ").title(),
            "value": (
                f"{_format_value(primary_metric, primary_value)} / {primary_target} "
                f"{_label_metric(primary_metric)}"
            ),
            "inline": False,
        }
    ]
    secondary_pairs = [
        ("Calories", "calories", "calories"),
        ("Net carbs", "net_carbs", "net_carbs"),
        ("Protein", "protein", "protein"),
        ("Fat", "fat", "fat"),
    ]
    for name, metric, key in secondary_pairs:
        if metric == primary_metric:
            continue
        v = totals.get(key)
        if v is None:
            continue
        fields.append(
            {
                "name": name,
                "value": f"{_format_value(metric, v)} {_label_metric(metric)}",
                "inline": True,
            }
        )

    payload = {
        "username": "Bento",
        "embeds": [
            {
                "title": f"Today's totals · {day.strftime('%a, %b %d')}",
                "color": EMBED_COLOR,
                "fields": fields,
            }
        ],
    }
    return await _post(webhook_url, payload)


async def send_weekly_summary(
    webhook_url: str,
    user: User,
    *,
    week_start: date,
    week_end: date,
    avg_primary: Optional[float],
    days_logged: int,
    days_under_or_at: int,
    days_over: int,
    primary_metric: str,
    primary_target: int,
) -> tuple[bool, str]:
    payload = {
        "username": "Bento",
        "embeds": [
            {
                "title": f"Weekly recap · {week_start.strftime('%b %d')}{chr(8211)}{week_end.strftime('%b %d')}",
                "color": EMBED_COLOR,
                "fields": [
                    {
                        "name": "Average daily",
                        "value": (
                            f"{_format_value(primary_metric, avg_primary)} "
                            f"{_label_metric(primary_metric)}"
                            if avg_primary is not None
                            else "—"
                        ),
                        "inline": False,
                    },
                    {"name": "Days logged", "value": str(days_logged), "inline": True},
                    {
                        "name": "At or under target",
                        "value": str(days_under_or_at),
                        "inline": True,
                    },
                    {"name": "Over target", "value": str(days_over), "inline": True},
                ],
                "footer": {"text": f"Target: {primary_target} {_label_metric(primary_metric)}/day"},
            }
        ],
    }
    return await _post(webhook_url, payload)


async def send_log_nudge(webhook_url: str, user: User) -> tuple[bool, str]:
    payload = {
        "username": "Bento",
        "content": f"Haven't seen you log anything today, {user.name} — when you get a moment.",
    }
    return await _post(webhook_url, payload)


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
