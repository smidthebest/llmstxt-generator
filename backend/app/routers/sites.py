from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import CrawlJob, GeneratedFile, MonitoringSchedule, Site
from app.schemas import (
    SiteCreate,
    SiteListResponse,
    SiteOverviewListResponse,
    SiteOverviewResponse,
    SiteResponse,
)
from app.services.task_queue import enqueue_crawl_task

router = APIRouter(prefix="/api/sites", tags=["sites"])


@router.post("", response_model=SiteResponse, status_code=201)
async def create_site(body: SiteCreate, db: AsyncSession = Depends(get_db)):
    url = str(body.url).rstrip("/")
    domain = urlparse(url).netloc

    # Check if site already exists (match on full URL, not just domain)
    result = await db.execute(select(Site).where(Site.url == url))
    existing = result.scalar_one_or_none()
    if existing:
        # Trigger a new crawl and return existing site
        job = CrawlJob(
            site_id=existing.id,
            status="pending",
            max_pages=body.max_pages,
        )
        db.add(job)
        await db.commit()
        await db.refresh(job)

        await enqueue_crawl_task(
            db,
            existing.id,
            job.id,
            idempotency_key=f"crawl-job-{job.id}",
            payload_json={
                "max_depth": body.max_depth,
                "max_pages": body.max_pages,
            },
        )
        return existing

    site = Site(url=url, domain=domain)
    db.add(site)
    await db.commit()
    await db.refresh(site)

    # Create crawl job and enqueue crawl task
    job = CrawlJob(
        site_id=site.id,
        status="pending",
        max_pages=body.max_pages,
    )
    db.add(job)
    await db.commit()
    await db.refresh(job)

    await enqueue_crawl_task(
        db,
        site.id,
        job.id,
        idempotency_key=f"crawl-job-{job.id}",
        payload_json={
            "max_depth": body.max_depth,
            "max_pages": body.max_pages,
        },
    )
    return site


@router.get("", response_model=SiteListResponse)
async def list_sites(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Site).order_by(Site.created_at.desc()))
    sites = result.scalars().all()
    return SiteListResponse(sites=sites)


@router.get("/overview", response_model=SiteOverviewListResponse)
async def list_sites_overview(db: AsyncSession = Depends(get_db)):
    sites_result = await db.execute(select(Site).order_by(Site.updated_at.desc()))
    sites = sites_result.scalars().all()

    latest_jobs_result = await db.execute(
        select(CrawlJob)
        .distinct(CrawlJob.site_id)
        .order_by(CrawlJob.site_id, CrawlJob.created_at.desc(), CrawlJob.id.desc())
    )
    latest_jobs = {job.site_id: job for job in latest_jobs_result.scalars().all()}

    latest_generated_result = await db.execute(
        select(GeneratedFile)
        .distinct(GeneratedFile.site_id)
        .order_by(
            GeneratedFile.site_id, GeneratedFile.created_at.desc(), GeneratedFile.id.desc()
        )
    )
    latest_generated = {
        generated.site_id: generated
        for generated in latest_generated_result.scalars().all()
    }

    schedules_result = await db.execute(select(MonitoringSchedule))
    schedules = {schedule.site_id: schedule for schedule in schedules_result.scalars().all()}

    overview_sites: list[SiteOverviewResponse] = []
    for site in sites:
        latest_job = latest_jobs.get(site.id)
        latest_file = latest_generated.get(site.id)
        schedule = schedules.get(site.id)

        overview_sites.append(
            SiteOverviewResponse(
                site=SiteResponse.model_validate(site),
                latest_crawl_job_id=latest_job.id if latest_job else None,
                latest_crawl_status=latest_job.status if latest_job else None,
                latest_crawl_pages_crawled=latest_job.pages_crawled if latest_job else None,
                latest_crawl_pages_found=latest_job.pages_found if latest_job else None,
                latest_crawl_pages_changed=latest_job.pages_changed if latest_job else None,
                latest_crawl_updated_at=latest_job.updated_at if latest_job else None,
                latest_crawl_error_message=latest_job.error_message if latest_job else None,
                llms_generated=latest_file is not None,
                llms_generated_at=latest_file.created_at if latest_file else None,
                llms_edited=latest_file.is_edited if latest_file else False,
                schedule_active=bool(schedule and schedule.is_active),
                schedule_cron_expression=schedule.cron_expression if schedule else None,
                schedule_next_run_at=schedule.next_run_at if schedule else None,
            )
        )

    return SiteOverviewListResponse(sites=overview_sites)


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
