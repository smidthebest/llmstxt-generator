import logging
from datetime import datetime, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy import select

from app.database import async_session
from app.models import MonitoringSchedule

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler()


async def scheduled_crawl(site_id: int):
    """Run a scheduled crawl for a site."""
    from app.tasks.crawl_task import run_crawl_job

    logger.info(f"Scheduled crawl starting for site {site_id}")
    async with async_session() as db:
        await run_crawl_job(db, site_id)
        # Update last_run_at
        result = await db.execute(
            select(MonitoringSchedule).where(MonitoringSchedule.site_id == site_id)
        )
        schedule = result.scalar_one_or_none()
        if schedule:
            schedule.last_run_at = datetime.now(timezone.utc)
            await db.commit()


def add_schedule(site_id: int, cron_expression: str):
    """Add or replace a schedule for a site."""
    job_id = f"crawl_site_{site_id}"
    if scheduler.get_job(job_id):
        scheduler.remove_job(job_id)

    trigger = CronTrigger.from_crontab(cron_expression)
    scheduler.add_job(
        scheduled_crawl,
        trigger=trigger,
        id=job_id,
        args=[site_id],
        replace_existing=True,
    )
    logger.info(f"Scheduled crawl for site {site_id} with cron: {cron_expression}")


def remove_schedule(site_id: int):
    """Remove a schedule for a site."""
    job_id = f"crawl_site_{site_id}"
    if scheduler.get_job(job_id):
        scheduler.remove_job(job_id)


async def load_schedules_from_db():
    """Load all active schedules from the database on startup."""
    async with async_session() as db:
        result = await db.execute(
            select(MonitoringSchedule).where(MonitoringSchedule.is_active.is_(True))
        )
        schedules = result.scalars().all()
        for schedule in schedules:
            add_schedule(schedule.site_id, schedule.cron_expression)
        logger.info(f"Loaded {len(schedules)} schedules from database")
