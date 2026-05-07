"""Scheduler tick logic. Decides what's due for whom and dispatches via the
Discord client. Idempotent across restarts via reminder_log dedupe.
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import AsyncSessionLocal
from app.models import DiscordSettings, Entry, ReminderLog, User
from app.services import discord as discord_svc
from app.services import logging as log_svc
from app.services import trends as trends_svc

logger = logging.getLogger(__name__)

# How late after a configured time we'll still fire (catches a missed tick).
_GRACE = timedelta(minutes=60)
# Waking-hour anchor for log-nudge math.
_WAKING_START_HOUR = 8
_FAILURE_THRESHOLD = 3


def _now_user_local(user: User) -> datetime:
    return datetime.now(timezone.utc).astimezone(log_svc._user_tz(user))


def _meal_label_for_hour(hour: int) -> str:
    if hour < 11:
        return "breakfast"
    if hour < 15:
        return "lunch"
    if hour < 22:
        return "dinner"
    return "a snack"


async def _already_sent_today(
    db: AsyncSession, user: User, slot: str
) -> bool:
    today_local = _now_user_local(user).date()
    start, end = log_svc.local_day_bounds_utc(user, today_local)
    row = (
        await db.execute(
            select(ReminderLog.id)
            .where(
                ReminderLog.user_id == user.id,
                ReminderLog.reminder_type == slot,
                ReminderLog.sent_at >= start,
                ReminderLog.sent_at < end,
            )
            .limit(1)
        )
    ).first()
    return row is not None


async def _record(
    db: AsyncSession, user_id: int, reminder_type: str
) -> None:
    db.add(ReminderLog(user_id=user_id, reminder_type=reminder_type))


async def _record_failure(
    db: AsyncSession, cfg: DiscordSettings, detail: str
) -> None:
    cfg.consecutive_failures = (cfg.consecutive_failures or 0) + 1
    if cfg.consecutive_failures >= _FAILURE_THRESHOLD:
        cfg.auto_disabled = True
        logger.warning(
            "Discord reminders auto-disabled for user %s after %s failures: %s",
            cfg.user_id,
            cfg.consecutive_failures,
            detail,
        )


def _record_success(cfg: DiscordSettings) -> None:
    cfg.consecutive_failures = 0


async def _send_or_track(
    db: AsyncSession,
    cfg: DiscordSettings,
    user: User,
    slot: str,
    sender,
    *args,
    **kwargs,
) -> bool:
    """Run a sender, write reminder_log on success, track failures otherwise.
    Returns True if we should consider this user 'still active' for further sends."""
    try:
        ok, detail = await sender(cfg.webhook_url, user, *args, **kwargs)
    except Exception as e:
        logger.exception("Reminder sender raised for user %s: %s", user.id, e)
        ok, detail = False, str(e)
    if ok:
        await _record(db, user.id, slot)
        _record_success(cfg)
        return True
    await _record_failure(db, cfg, detail)
    return not cfg.auto_disabled


async def _maybe_meal(
    db: AsyncSession, user: User, cfg: DiscordSettings
) -> bool:
    if not cfg.meal_reminders_enabled:
        return True
    times = discord_svc.deserialize_meal_times(cfg.meal_reminders_times)
    if not times:
        return True
    now_local = _now_user_local(user)
    for hhmm in times:
        h, m = int(hhmm[:2]), int(hhmm[3:])
        target_dt = now_local.replace(hour=h, minute=m, second=0, microsecond=0)
        if now_local < target_dt:
            continue
        if (now_local - target_dt) > _GRACE:
            continue
        slot = f"meal:{hhmm}"
        if await _already_sent_today(db, user, slot):
            continue
        label = _meal_label_for_hour(h)
        if not await _send_or_track(
            db, cfg, user, slot, discord_svc.send_meal_nudge, label
        ):
            return False
    return True


async def _maybe_eod(
    db: AsyncSession, user: User, cfg: DiscordSettings
) -> bool:
    if not cfg.eod_summary_enabled:
        return True
    if not discord_svc._valid_hhmm(cfg.eod_summary_time):
        return True
    h, m = int(cfg.eod_summary_time[:2]), int(cfg.eod_summary_time[3:])
    now_local = _now_user_local(user)
    target_dt = now_local.replace(hour=h, minute=m, second=0, microsecond=0)
    if now_local < target_dt or (now_local - target_dt) > _GRACE:
        return True
    if await _already_sent_today(db, user, "eod"):
        return True
    today = now_local.date()
    pairs = await log_svc.list_entries_with_foods(db, user, today)
    totals = log_svc.daily_totals(pairs)
    return await _send_or_track(
        db,
        cfg,
        user,
        "eod",
        discord_svc.send_eod_summary,
        today,
        totals,
        user.primary_metric,
        user.daily_target_primary,
    )


async def _maybe_weekly(
    db: AsyncSession, user: User, cfg: DiscordSettings
) -> bool:
    if not cfg.weekly_summary_enabled:
        return True
    now_local = _now_user_local(user)
    # weekday: Monday=0 ... Sunday=6 in Python's isoweekday-1; we store Sun=0.
    # Convert: our_day = 0 -> Sunday -> python's weekday()==6
    target_python_weekday = (cfg.weekly_summary_day - 1) % 7  # 0->6, 1->0, ...
    if now_local.weekday() != target_python_weekday:
        return True
    if not discord_svc._valid_hhmm(cfg.eod_summary_time):
        return True
    h, m = int(cfg.eod_summary_time[:2]), int(cfg.eod_summary_time[3:])
    target_dt = now_local.replace(hour=h, minute=m, second=0, microsecond=0)
    if now_local < target_dt or (now_local - target_dt) > _GRACE:
        return True
    if await _already_sent_today(db, user, "weekly"):
        return True

    week_end = now_local.date()
    week_start = week_end - timedelta(days=6)
    series = await trends_svc.daily_series(db, user, days=7)
    stats = trends_svc.summary_stats(series, user.daily_target_primary)
    return await _send_or_track(
        db,
        cfg,
        user,
        "weekly",
        discord_svc.send_weekly_summary,
        week_start=week_start,
        week_end=week_end,
        avg_primary=stats["avg"],
        days_logged=stats["days_logged"],
        days_under_or_at=stats["days_under_or_at"],
        days_over=stats["days_over"],
        primary_metric=user.primary_metric,
        primary_target=user.daily_target_primary,
    )


async def _maybe_log_nudge(
    db: AsyncSession, user: User, cfg: DiscordSettings
) -> bool:
    if not cfg.log_nudge_enabled:
        return True
    now_local = _now_user_local(user)
    threshold_hour = _WAKING_START_HOUR + max(1, min(24, cfg.log_nudge_after_hours))
    if now_local.hour < threshold_hour:
        return True
    if await _already_sent_today(db, user, "log_nudge"):
        return True
    today = now_local.date()
    start, end = log_svc.local_day_bounds_utc(user, today)
    has_entry = (
        await db.execute(
            select(Entry.id)
            .where(
                Entry.user_id == user.id,
                Entry.logged_at >= start,
                Entry.logged_at < end,
            )
            .limit(1)
        )
    ).first()
    if has_entry is not None:
        return True
    return await _send_or_track(
        db, cfg, user, "log_nudge", discord_svc.send_log_nudge
    )


async def _process_user(
    db: AsyncSession, user: User, cfg: DiscordSettings
) -> None:
    if cfg.auto_disabled or not cfg.webhook_url:
        return
    if not await _maybe_meal(db, user, cfg):
        return
    if not await _maybe_eod(db, user, cfg):
        return
    if not await _maybe_weekly(db, user, cfg):
        return
    await _maybe_log_nudge(db, user, cfg)


async def tick() -> None:
    """One pass: dispatch any due reminders for any user. Idempotent."""
    async with AsyncSessionLocal() as db:
        rows = (
            await db.execute(
                select(User, DiscordSettings)
                .join(DiscordSettings, DiscordSettings.user_id == User.id)
                .where(
                    User.is_active.is_(True),
                    DiscordSettings.auto_disabled.is_(False),
                    DiscordSettings.webhook_url.is_not(None),
                )
            )
        ).all()
        for user, cfg in rows:
            try:
                await _process_user(db, user, cfg)
            except Exception:
                logger.exception("Reminder tick failed for user %s", user.id)
        await db.commit()


# ----- Per-user "send a sample of each enabled reminder type" --------------


async def send_sample_of_each(
    db: AsyncSession, user: User, cfg: DiscordSettings
) -> dict:
    """For the settings 'Test webhook' button. Returns a dict of {type: msg}."""
    results: dict[str, str] = {}
    if not cfg.webhook_url:
        return {"all": "No webhook URL saved."}

    if cfg.meal_reminders_enabled:
        ok, msg = await discord_svc.send_meal_nudge(
            cfg.webhook_url, user, "a meal"
        )
        results["meal"] = "sent" if ok else f"failed: {msg}"

    if cfg.eod_summary_enabled:
        today = _now_user_local(user).date()
        pairs = await log_svc.list_entries_with_foods(db, user, today)
        totals = log_svc.daily_totals(pairs)
        ok, msg = await discord_svc.send_eod_summary(
            cfg.webhook_url, user, today,
            totals, user.primary_metric, user.daily_target_primary,
        )
        results["eod"] = "sent" if ok else f"failed: {msg}"

    if cfg.weekly_summary_enabled:
        now_local = _now_user_local(user)
        week_end = now_local.date()
        week_start = week_end - timedelta(days=6)
        series = await trends_svc.daily_series(db, user, days=7)
        stats = trends_svc.summary_stats(series, user.daily_target_primary)
        ok, msg = await discord_svc.send_weekly_summary(
            cfg.webhook_url, user,
            week_start=week_start, week_end=week_end,
            avg_primary=stats["avg"],
            days_logged=stats["days_logged"],
            days_under_or_at=stats["days_under_or_at"],
            days_over=stats["days_over"],
            primary_metric=user.primary_metric,
            primary_target=user.daily_target_primary,
        )
        results["weekly"] = "sent" if ok else f"failed: {msg}"

    if cfg.log_nudge_enabled:
        ok, msg = await discord_svc.send_log_nudge(cfg.webhook_url, user)
        results["log_nudge"] = "sent" if ok else f"failed: {msg}"

    if not results:
        # Nothing enabled — fall back to the basic "connected" test.
        ok, msg = await discord_svc.send_test(cfg.webhook_url, user)
        results["connection"] = "sent" if ok else f"failed: {msg}"
    return results
