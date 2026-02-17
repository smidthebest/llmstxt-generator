import asyncio
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session, get_db
from app.models import CrawlJob, Site
from app.schemas import SiteCreate, SiteListResponse, SiteResponse
from app.schemas.crawl import CrawlJobResponse
from app.tasks.crawl_task import run_crawl_job

router = APIRouter(prefix="/api/sites", tags=["sites"])


@router.post("", response_model=SiteResponse, status_code=201)
async def create_site(body: SiteCreate, db: AsyncSession = Depends(get_db)):
    url = str(body.url).rstrip("/")
    domain = urlparse(url).netloc

    # Check if site already exists
    result = await db.execute(select(Site).where(Site.domain == domain))
    existing = result.scalar_one_or_none()
    if existing:
        # Trigger a new crawl and return existing site
        job = CrawlJob(site_id=existing.id, status="pending")
        db.add(job)
        await db.commit()
        await db.refresh(job)

        async def _crawl():
            async with async_session() as session:
                await run_crawl_job(session, existing.id, job.id)

        asyncio.create_task(_crawl())
        return existing

    site = Site(url=url, domain=domain)
    db.add(site)
    await db.commit()
    await db.refresh(site)

    # Create crawl job and start crawling
    job = CrawlJob(site_id=site.id, status="pending")
    db.add(job)
    await db.commit()
    await db.refresh(job)

    async def _crawl():
        async with async_session() as session:
            await run_crawl_job(session, site.id, job.id)

    asyncio.create_task(_crawl())
    return site


@router.get("", response_model=SiteListResponse)
async def list_sites(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Site).order_by(Site.created_at.desc()))
    sites = result.scalars().all()
    return SiteListResponse(sites=sites)


@router.get("/{site_id}", response_model=SiteResponse)
async def get_site(site_id: int, db: AsyncSession = Depends(get_db)):
    site = await db.get(Site, site_id)
    if not site:
        raise HTTPException(status_code=404, detail="Site not found")
    return site


@router.delete("/{site_id}", status_code=204)
async def delete_site(site_id: int, db: AsyncSession = Depends(get_db)):
    site = await db.get(Site, site_id)
    if not site:
        raise HTTPException(status_code=404, detail="Site not found")
    await db.delete(site)
    await db.commit()
