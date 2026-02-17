import asyncio

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session, get_db
from app.models import CrawlJob, Site
from app.schemas.crawl import CrawlJobResponse
from app.tasks.crawl_task import run_crawl_job

router = APIRouter(prefix="/api/sites/{site_id}/crawl", tags=["crawl"])


@router.post("", response_model=CrawlJobResponse, status_code=201)
async def start_crawl(site_id: int, db: AsyncSession = Depends(get_db)):
    site = await db.get(Site, site_id)
    if not site:
        raise HTTPException(status_code=404, detail="Site not found")

    job = CrawlJob(site_id=site_id, status="pending")
    db.add(job)
    await db.commit()
    await db.refresh(job)

    async def _crawl():
        async with async_session() as session:
            await run_crawl_job(session, site_id, job.id)

    asyncio.create_task(_crawl())
    return job


@router.get("/{job_id}", response_model=CrawlJobResponse)
async def get_crawl_status(site_id: int, job_id: int, db: AsyncSession = Depends(get_db)):
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
