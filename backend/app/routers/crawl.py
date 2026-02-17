import asyncio
import json
import time

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session, get_db
from app.models import CrawlJob, Page, Site
from app.schemas.crawl import CrawlConfig, CrawlJobResponse
from app.services.crawl_events import subscribe, unsubscribe
from app.services.task_queue import enqueue_crawl_task

router = APIRouter(prefix="/api/sites/{site_id}/crawl", tags=["crawl"])


@router.post("", response_model=CrawlJobResponse, status_code=201)
async def start_crawl(
    site_id: int,
    config: CrawlConfig = CrawlConfig(),
    db: AsyncSession = Depends(get_db),
):
    site = await db.get(Site, site_id)
    if not site:
        raise HTTPException(status_code=404, detail="Site not found")

    job = CrawlJob(site_id=site_id, status="pending")
    db.add(job)
    await db.commit()
    await db.refresh(job)

    await enqueue_crawl_task(
        db,
        site_id,
        job.id,
        payload_json={
            "max_depth": config.max_depth,
            "max_pages": config.max_pages,
        },
    )
    return job


@router.get("/{job_id}/stream")
async def stream_crawl_events(
    site_id: int, job_id: int, request: Request, db: AsyncSession = Depends(get_db)
):
    """SSE endpoint for live crawl events."""
    job = await db.get(CrawlJob, job_id)
    if not job or job.site_id != site_id:
        raise HTTPException(status_code=404, detail="Crawl job not found")

    # If already finished, replay stored pages from DB then send terminal event
    if job.status in ("completed", "failed"):
        pages_result = await db.execute(
            select(Page)
            .where(Page.site_id == site_id, Page.created_at >= job.created_at)
            .order_by(Page.id)
        )
        stored_pages = pages_result.scalars().all()

        async def finished_stream():
            for p in stored_pages:
                yield (
                    "data: "
                    + json.dumps(
                        {
                            "type": "page_crawled",
                            "url": p.url,
                            "title": p.title,
                            "description": p.description,
                            "category": p.category,
                            "relevance_score": round(p.relevance_score, 2),
                            "depth": p.depth,
                        }
                    )
                    + "\n\n"
                )
            yield (
                "data: "
                + json.dumps(
                    {
                        "type": "progress",
                        "pages_found": job.pages_found,
                        "pages_crawled": job.pages_crawled,
                        "pages_changed": job.pages_changed,
                        "max_pages": max(job.pages_crawled, 1),
                    }
                )
                + "\n\n"
            )
            if job.status == "completed":
                yield f"data: {json.dumps({'type': 'completed'})}\n\n"
            else:
                yield (
                    "data: "
                    + json.dumps({"type": "failed", "error": job.error_message})
                    + "\n\n"
                )

        return StreamingResponse(
            finished_stream(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    queue = subscribe(job_id)
    sent_urls: set[str] = set()
    last_progress: tuple[int, int, int] | None = None
    last_heartbeat_at = time.monotonic()

    async def poll_db_events():
        nonlocal last_progress
        async with async_session() as poll_db:
            current_job = await poll_db.get(CrawlJob, job_id)
            if not current_job or current_job.site_id != site_id:
                return [], None, {"type": "failed", "error": "Crawl job not found"}

            pages_result = await poll_db.execute(
                select(Page)
                .where(
                    Page.site_id == site_id,
                    Page.created_at >= job.created_at,
                )
                .order_by(Page.id)
            )
            all_pages = pages_result.scalars().all()

            page_events = []
            for p in all_pages:
                if p.url in sent_urls:
                    continue
                sent_urls.add(p.url)
                page_events.append(
                    {
                        "type": "page_crawled",
                        "url": p.url,
                        "title": p.title,
                        "description": p.description,
                        "category": p.category,
                        "relevance_score": round(p.relevance_score, 2),
                        "depth": p.depth,
                    }
                )

            current_progress = (
                current_job.pages_found,
                current_job.pages_crawled,
                current_job.pages_changed,
            )
            progress_event = None
            if current_progress != last_progress:
                progress_event = {
                    "type": "progress",
                    "pages_found": current_job.pages_found,
                    "pages_crawled": current_job.pages_crawled,
                    "pages_changed": current_job.pages_changed,
                    "max_pages": max(current_job.pages_crawled, 1),
                }
                last_progress = current_progress

            terminal_event = None
            if current_job.status == "completed":
                terminal_event = {"type": "completed"}
            elif current_job.status == "failed":
                terminal_event = {
                    "type": "failed",
                    "error": current_job.error_message or "Crawl failed",
                }

            return page_events, progress_event, terminal_event

    async def event_generator():
        nonlocal last_heartbeat_at
        try:
            while True:
                if await request.is_disconnected():
                    break
                emitted = False
                got_queue_event = False
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=1.0)
                    got_queue_event = True
                except asyncio.TimeoutError:
                    event = None

                if got_queue_event and event is None:
                    break

                if event is not None:
                    yield f"data: {json.dumps(event)}\n\n"
                    emitted = True
                    if event.get("type") in ("completed", "failed"):
                        break

                page_events, progress_event, terminal_event = await poll_db_events()

                for page_event in page_events:
                    yield f"data: {json.dumps(page_event)}\n\n"
                    emitted = True

                if progress_event is not None:
                    yield f"data: {json.dumps(progress_event)}\n\n"
                    emitted = True

                if terminal_event is not None:
                    yield f"data: {json.dumps(terminal_event)}\n\n"
                    break

                if emitted:
                    last_heartbeat_at = time.monotonic()
                elif time.monotonic() - last_heartbeat_at >= 15:
                    yield ": heartbeat\n\n"
                    last_heartbeat_at = time.monotonic()
        finally:
            unsubscribe(job_id, queue)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/{job_id}", response_model=CrawlJobResponse)
async def get_crawl_status(
    site_id: int, job_id: int, db: AsyncSession = Depends(get_db)
):
    job = await db.get(CrawlJob, job_id)
    if not job or job.site_id != site_id:
        raise HTTPException(status_code=404, detail="Crawl job not found")
    return job


@router.get("", response_model=list[CrawlJobResponse])
async def list_crawl_jobs(site_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(CrawlJob)
        .where(CrawlJob.site_id == site_id)
        .order_by(CrawlJob.created_at.desc())
        .limit(20)
    )
    return result.scalars().all()
