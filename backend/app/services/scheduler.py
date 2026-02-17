import logging
from datetime import datetime, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy import select

from app.database import async_session
from app.models import CrawlJob, CrawlTask, MonitoringSchedule, Site
from app.services.task_queue import enqueue_crawl_task

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler()


def _schedule_job_id(site_id: int) -> str:
    return f"crawl_site_{site_id}"


def _schedule_idempotency_key(site_id: int, current_time: datetime) -> str:
    window = current_time.replace(second=0, microsecond=0).isoformat()
    return f"site:{site_id}:cron:{window}"


async def scheduled_crawl(site_id: int):
    """Enqueue a scheduled crawl for a site."""
    now = datetime.now(timezone.utc)
    idempotency_key = _schedule_idempotency_key(site_id, now)

    logger.info("Scheduled crawl trigger for site %s", site_id)

    async with async_session() as db:
        site = await db.get(Site, site_id)
        if not site:
            logger.warning("Scheduled crawl skipped: site %s no longer exists", site_id)
            return

        existing_result = await db.execute(
            select(CrawlTask).where(CrawlTask.idempotency_key == idempotency_key)
        )
        existing_task = existing_result.scalar_one_or_none()
        if existing_task:
            logger.info(
                "Scheduled crawl deduped for site %s with key %s (task=%s)",
                site_id,
                idempotency_key,
                existing_task.id,
            )
            return

        job = CrawlJob(site_id=site_id, status="pending")
        db.add(job)
        await db.commit()
        await db.refresh(job)

        result = await db.execute(
            select(MonitoringSchedule).where(MonitoringSchedule.site_id == site_id)
        )
        schedule = result.scalar_one_or_none()
        if schedule:
            schedule.last_run_at = now

        task = await enqueue_crawl_task(
            db,
            site_id,
            job.id,
            idempotency_key=idempotency_key,
        )

        logger.info(
            "Scheduled crawl enqueued task=%s crawl_job=%s site=%s key=%s",
            task.id,
            job.id,
            site_id,
            idempotency_key,
        )


def add_schedule(site_id: int, cron_expression: str):
    """Add or replace a schedule for a site."""
    job_id = _schedule_job_id(site_id)
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
    logger.info("Scheduled crawl for site %s with cron: %s", site_id, cron_expression)


def remove_schedule(site_id: int):
    """Remove a schedule for a site."""
    job_id = _schedule_job_id(site_id)
    if scheduler.get_job(job_id):
        scheduler.remove_job(job_id)


async def sync_schedules_from_db() -> int:
    """Sync in-memory APScheduler jobs with active DB schedules."""
    async with async_session() as db:
        result = await db.execute(
            select(MonitoringSchedule).where(MonitoringSchedule.is_active.is_(True))
        )
        schedules = result.scalars().all()

    active_site_ids = {schedule.site_id for schedule in schedules}

    for job in scheduler.get_jobs():
        if not job.id.startswith("crawl_site_"):
            continue
        site_id = int(job.id.replace("crawl_site_", ""))
        if site_id not in active_site_ids:
            scheduler.remove_job(job.id)

    for schedule in schedules:
        add_schedule(schedule.site_id, schedule.cron_expression)

    logger.info("Synced %s active schedules from database", len(schedules))
    return len(schedules)


async def load_schedules_from_db():
    """Backward-compatible wrapper used at worker startup."""
    await sync_schedules_from_db()
