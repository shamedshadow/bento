"""APScheduler wiring — periodic jobs for reminders and Mealie sync."""

import logging
from zoneinfo import ZoneInfo

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from app.db import AsyncSessionLocal
from app.services import mealie as mealie_svc
from app.services import reminders as reminders_svc

logger = logging.getLogger(__name__)

# Cron jobs run on this timezone. Anchored to the homelab admin's locale rather
# than container time, which is usually UTC. Hardcoded for now; revisit if the
# project ever serves users in different timezones.
SCHEDULER_TZ = ZoneInfo("America/New_York")


async def mealie_nightly_sync() -> None:
    """Pull recipes nightly. No-op when Mealie isn't configured."""
    async with AsyncSessionLocal() as db:
        cfg = await mealie_svc.get_or_create_settings(db)
        if not cfg.url or not cfg.api_token:
            return
        result = await mealie_svc.sync(db, cfg)
        await db.commit()
        if "error" in result:
            logger.warning("Nightly Mealie sync failed: %s", result["error"])
        else:
            logger.info(
                "Nightly Mealie sync: %d new, %d updated, %d skipped (of %d)",
                result.get("imported", 0),
                result.get("updated", 0),
                result.get("skipped", 0),
                result.get("total", 0),
            )


def build_scheduler() -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone=SCHEDULER_TZ)
    scheduler.add_job(
        reminders_svc.tick,
        trigger=IntervalTrigger(minutes=5),
        id="reminders_tick",
        max_instances=1,
        coalesce=True,
        replace_existing=True,
        next_run_time=None,
    )
    scheduler.add_job(
        mealie_nightly_sync,
        trigger=CronTrigger(hour=2, minute=0, timezone=SCHEDULER_TZ),
        id="mealie_nightly_sync",
        max_instances=1,
        coalesce=True,
        replace_existing=True,
    )
    return scheduler
