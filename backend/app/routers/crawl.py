import asyncio
import json

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
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
            select(Page).where(Page.site_id == site_id).order_by(Page.id)
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
                        "max_pages": job.pages_crawled,
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

    async def event_generator():
        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=15.0)
                except asyncio.TimeoutError:
                    yield ": heartbeat\n\n"
                    continue

                if event is None:
                    break

                yield f"data: {json.dumps(event)}\n\n"

                if event.get("type") in ("completed", "failed"):
                    break
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
