import asyncio
import logging
import signal
import uuid

from app.config import settings
from app.database import async_session
from app.models import CrawlJob, CrawlTask
from app.services.scheduler import load_schedules_from_db, scheduler, sync_schedules_from_db
from app.services.task_queue import (
    claim_next_task,
    complete_task,
    fail_task,
    heartbeat_task,
    recover_expired_running_tasks,
)
from app.tasks.crawl_task import run_crawl_job

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def process_task(task_id: int, worker_id: str) -> None:
    done = asyncio.Event()

    async def heartbeat_loop() -> None:
        while not done.is_set():
            try:
                await asyncio.wait_for(
                    done.wait(), timeout=settings.task_heartbeat_interval_seconds
                )
                break
            except asyncio.TimeoutError:
                pass

            async with async_session() as heartbeat_db:
                ok = await heartbeat_task(
                    heartbeat_db,
                    task_id=task_id,
                    worker_id=worker_id,
                    lease_seconds=settings.task_lease_seconds,
                )
                if not ok:
                    logger.warning(
                        "Heartbeat stopped for task=%s worker=%s", task_id, worker_id
                    )
                    return
                logger.info("Heartbeat renewed for task=%s", task_id)

    heartbeat = asyncio.create_task(heartbeat_loop())

    success = False
    failure_error = "run_crawl_job returned unsuccessful status"

    try:
        async with async_session() as db:
            task = await db.get(CrawlTask, task_id)
            if not task:
                done.set()
                await heartbeat
                return

            payload = task.payload_json or {}
            max_depth = payload.get("max_depth")
            max_pages = payload.get("max_pages")

            logger.info(
                "Running task=%s crawl_job=%s site=%s attempt=%s",
                task.id,
                task.crawl_job_id,
                task.site_id,
                task.attempt_count,
            )
            success = await run_crawl_job(
                db,
                task.site_id,
                task.crawl_job_id,
                max_depth=max_depth,
                max_pages=max_pages,
            )
    except Exception as exc:
        logger.exception("Unhandled worker exception for task=%s", task_id)
        failure_error = str(exc)
        success = False
    finally:
        done.set()
        await heartbeat

    async with async_session() as db:
        if success:
            completed = await complete_task(db, task_id=task_id, worker_id=worker_id)
            if completed:
                logger.info("Completed task=%s worker=%s", task_id, worker_id)
            else:
                logger.warning(
                    "Task completion skipped (not leased by worker) task=%s worker=%s",
                    task_id,
                    worker_id,
                )
            return

        failure = await fail_task(
            db,
            task_id=task_id,
            worker_id=worker_id,
            error_message=failure_error,
        )

        task = await db.get(CrawlTask, task_id)
        if failure["status"] == "failed":
            if task and task.crawl_job_id:
                job = await db.get(CrawlJob, task.crawl_job_id)
                if job:
                    job.status = "pending"
                    job.error_message = f"Retrying (attempt {task.attempt_count}/{task.max_attempts}): {failure_error[:200]}"
                    await db.commit()

            logger.warning(
                "Retry scheduled for task=%s in %ss",
                task_id,
                failure["retry_in_seconds"],
            )
        elif failure["status"] == "dead_letter":
            logger.error("Task=%s moved to dead_letter", task_id)
        else:
            logger.error("Task=%s failed but could not be updated", task_id)


async def worker_loop(stop_event: asyncio.Event, worker_id: str) -> None:
    max_concurrent = settings.worker_max_concurrent_tasks
    logger.info(
        "Worker started with id=%s max_concurrent=%s", worker_id, max_concurrent
    )
    poll_interval = settings.task_poll_interval_ms / 1000
    scheduler_sync_interval = settings.scheduler_sync_interval_seconds
    next_scheduler_sync = 0.0

    active_tasks: dict[int, asyncio.Task] = {}  # task_id -> asyncio.Task

    while not stop_event.is_set():
        # Clean up finished tasks
        finished = [tid for tid, t in active_tasks.items() if t.done()]
        for tid in finished:
            task = active_tasks.pop(tid)
            if task.exception():
                logger.error(
                    "Task=%s raised unhandled exception: %s", tid, task.exception()
                )

        now = asyncio.get_running_loop().time()
        if settings.run_scheduler and now >= next_scheduler_sync:
            await sync_schedules_from_db()
            next_scheduler_sync = now + scheduler_sync_interval

        async with async_session() as db:
            recovered = await recover_expired_running_tasks(db)
            if recovered:
                logger.warning(
                    "Recovered %s expired leased task(s) back to failed", recovered
                )

        # Claim tasks up to max concurrency
        while len(active_tasks) < max_concurrent:
            async with async_session() as db:
                task = await claim_next_task(
                    db,
                    worker_id=worker_id,
                    lease_seconds=settings.task_lease_seconds,
                )

            if not task:
                break  # no more tasks available

            logger.info(
                "Dispatching task=%s (active: %s/%s)",
                task.id,
                len(active_tasks) + 1,
                max_concurrent,
            )
            t = asyncio.create_task(process_task(task.id, worker_id))
            active_tasks[task.id] = t

        try:
            await asyncio.wait_for(stop_event.wait(), timeout=poll_interval)
        except asyncio.TimeoutError:
            continue


async def main() -> None:
    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()

    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop_event.set)

    worker_id = settings.worker_id or f"worker-{uuid.uuid4().hex[:8]}"

    if settings.run_scheduler:
        scheduler.start()
        await load_schedules_from_db()
        logger.info("Scheduler enabled in worker process")

    try:
        await worker_loop(stop_event, worker_id)
    finally:
        # Shut down Playwright browser pool if it was started
        from app.services.browser_pool import shutdown_pool
        await shutdown_pool()

        if settings.run_scheduler and scheduler.running:
            scheduler.shutdown(wait=False)
        logger.info("Worker shutting down")


if __name__ == "__main__":
    asyncio.run(main())
