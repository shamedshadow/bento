"""APScheduler wiring — one job that polls the reminders service every 5 min."""

import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from app.services import reminders as reminders_svc

logger = logging.getLogger(__name__)


def build_scheduler() -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        reminders_svc.tick,
        trigger=IntervalTrigger(minutes=5),
        id="reminders_tick",
        max_instances=1,
        coalesce=True,
        replace_existing=True,
        next_run_time=None,
    )
    return scheduler
