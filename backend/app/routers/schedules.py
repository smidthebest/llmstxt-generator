from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import MonitoringSchedule, Site
from app.schemas.schedule import ScheduleCreate, ScheduleResponse
from app.services.scheduler import add_schedule, remove_schedule

router = APIRouter(prefix="/api/sites/{site_id}/schedule", tags=["schedules"])


@router.get("", response_model=ScheduleResponse)
async def get_schedule(site_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(MonitoringSchedule).where(MonitoringSchedule.site_id == site_id)
    )
    schedule = result.scalar_one_or_none()
    if not schedule:
        raise HTTPException(status_code=404, detail="No schedule found")
    return schedule


@router.put("", response_model=ScheduleResponse)
async def upsert_schedule(
    site_id: int, body: ScheduleCreate, db: AsyncSession = Depends(get_db)
):
    site = await db.get(Site, site_id)
    if not site:
        raise HTTPException(status_code=404, detail="Site not found")

    result = await db.execute(
        select(MonitoringSchedule).where(MonitoringSchedule.site_id == site_id)
    )
    schedule = result.scalar_one_or_none()

    if schedule:
        schedule.cron_expression = body.cron_expression
        schedule.is_active = body.is_active
    else:
        schedule = MonitoringSchedule(
            site_id=site_id,
            cron_expression=body.cron_expression,
            is_active=body.is_active,
        )
        db.add(schedule)

    await db.commit()
    await db.refresh(schedule)

    if body.is_active:
        next_run = add_schedule(site_id, body.cron_expression)
        schedule.next_run_at = next_run
    else:
        remove_schedule(site_id)
        schedule.next_run_at = None
    await db.commit()
    await db.refresh(schedule)

    return schedule


@router.delete("", status_code=204)
async def delete_schedule(site_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(MonitoringSchedule).where(MonitoringSchedule.site_id == site_id)
    )
    schedule = result.scalar_one_or_none()
    if not schedule:
        raise HTTPException(status_code=404, detail="No schedule found")

    remove_schedule(site_id)
    await db.delete(schedule)
    await db.commit()
