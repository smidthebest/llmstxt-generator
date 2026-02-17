import logging
import random
from datetime import datetime, timedelta, timezone

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import CrawlTask

logger = logging.getLogger(__name__)

QUEUE_READY_STATUSES = ("queued", "failed")
RUNNING_STATUS = "running"
TERMINAL_STATUS = "completed"
DEAD_LETTER_STATUS = "dead_letter"
LEASE_EXPIRY_ERROR = "Lease expired before worker heartbeat"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _compute_retry_delay_seconds(attempt_count: int) -> int:
    base = 15 * (2 ** max(attempt_count - 1, 0))
    delay = base * (1 + random.uniform(0, 0.2))
    return int(delay)


async def enqueue_crawl_task(
    db: AsyncSession,
    site_id: int,
    crawl_job_id: int,
    *,
    priority: int = 100,
    idempotency_key: str | None = None,
    payload_json: dict | None = None,
    max_attempts: int | None = None,
) -> CrawlTask:
    if idempotency_key:
        result = await db.execute(
            select(CrawlTask).where(CrawlTask.idempotency_key == idempotency_key)
        )
        existing = result.scalar_one_or_none()
        if existing:
            logger.info(
                "Found existing crawl task for idempotency key %s -> task=%s",
                idempotency_key,
                existing.id,
            )
            return existing

    task = CrawlTask(
        site_id=site_id,
        crawl_job_id=crawl_job_id,
        status="queued",
        priority=priority,
        attempt_count=0,
        max_attempts=max_attempts or settings.task_max_attempts,
        available_at=_utcnow(),
        idempotency_key=idempotency_key,
        payload_json=payload_json,
    )
    db.add(task)
    await db.commit()
    await db.refresh(task)

    logger.info(
        "Enqueued crawl task=%s crawl_job=%s site_id=%s",
        task.id,
        crawl_job_id,
        site_id,
    )
    return task


async def claim_next_task(
    db: AsyncSession,
    *,
    worker_id: str,
    lease_seconds: int,
) -> CrawlTask | None:
    now = _utcnow()

    result = await db.execute(
        select(CrawlTask)
        .where(CrawlTask.status.in_(QUEUE_READY_STATUSES))
        .where(CrawlTask.available_at <= now)
        .where(or_(CrawlTask.leased_until.is_(None), CrawlTask.leased_until < now))
        .order_by(CrawlTask.priority.asc(), CrawlTask.created_at.asc())
        .limit(1)
        .with_for_update(skip_locked=True)
    )
    task = result.scalar_one_or_none()
    if not task:
        return None

    task.status = RUNNING_STATUS
    task.attempt_count += 1
    task.lease_owner = worker_id
    task.leased_until = now + timedelta(seconds=lease_seconds)
    await db.commit()
    await db.refresh(task)

    logger.info(
        "Claimed crawl task=%s crawl_job=%s attempt=%s worker=%s",
        task.id,
        task.crawl_job_id,
        task.attempt_count,
        worker_id,
    )
    return task


async def heartbeat_task(
    db: AsyncSession,
    *,
    task_id: int,
    worker_id: str,
    lease_seconds: int,
) -> bool:
    result = await db.execute(
        select(CrawlTask)
        .where(CrawlTask.id == task_id)
        .where(CrawlTask.lease_owner == worker_id)
        .where(CrawlTask.status == RUNNING_STATUS)
        .with_for_update(skip_locked=True)
    )
    task = result.scalar_one_or_none()
    if not task:
        return False

    task.leased_until = _utcnow() + timedelta(seconds=lease_seconds)
    await db.commit()
    return True


async def complete_task(db: AsyncSession, *, task_id: int, worker_id: str) -> bool:
    result = await db.execute(
        select(CrawlTask)
        .where(CrawlTask.id == task_id)
        .where(CrawlTask.lease_owner == worker_id)
        .where(CrawlTask.status == RUNNING_STATUS)
        .with_for_update(skip_locked=True)
    )
    task = result.scalar_one_or_none()
    if not task:
        return False

    task.status = TERMINAL_STATUS
    task.leased_until = None
    task.lease_owner = None
    await db.commit()
    return True


async def fail_task(
    db: AsyncSession,
    *,
    task_id: int,
    worker_id: str,
    error_message: str,
) -> dict[str, int | str | None]:
    result = await db.execute(
        select(CrawlTask)
        .where(CrawlTask.id == task_id)
        .where(CrawlTask.lease_owner == worker_id)
        .where(CrawlTask.status == RUNNING_STATUS)
        .with_for_update(skip_locked=True)
    )
    task = result.scalar_one_or_none()
    if not task:
        return {"status": "missing", "retry_in_seconds": None}

    task.last_error = (error_message or "Unknown worker failure")[:2048]
    task.leased_until = None
    task.lease_owner = None

    if task.attempt_count >= task.max_attempts:
        task.status = DEAD_LETTER_STATUS
        await db.commit()
        return {"status": DEAD_LETTER_STATUS, "retry_in_seconds": None}

    retry_in = _compute_retry_delay_seconds(task.attempt_count)
    task.status = "failed"
    task.available_at = _utcnow() + timedelta(seconds=retry_in)
    await db.commit()
    return {"status": "failed", "retry_in_seconds": retry_in}


async def recover_expired_running_tasks(db: AsyncSession) -> int:
    now = _utcnow()
    result = await db.execute(
        select(CrawlTask)
        .where(CrawlTask.status == RUNNING_STATUS)
        .where(CrawlTask.leased_until.is_not(None))
        .where(CrawlTask.leased_until < now)
        .with_for_update(skip_locked=True)
    )
    stale = result.scalars().all()
    if not stale:
        return 0

    for task in stale:
        task.status = "failed"
        task.available_at = now
        task.lease_owner = None
        task.leased_until = None
        if not task.last_error:
            task.last_error = LEASE_EXPIRY_ERROR

    await db.commit()
    return len(stale)
