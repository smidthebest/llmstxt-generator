from datetime import datetime, timezone

from apscheduler.triggers.cron import CronTrigger
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import MonitoringSchedule, Site
from app.schemas.schedule import ScheduleCreate, ScheduleResponse
from app.services.scheduler import add_schedule, remove_schedule, scheduler

router = APIRouter(prefix="/api/sites/{site_id}/schedule", tags=["schedules"])


def _compute_next_run(cron_expression: str):
    trigger = CronTrigger.from_crontab(cron_expression)
    now = datetime.now(timezone.utc)
    return trigger.get_next_fire_time(None, now)


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

    if body.is_active:
        if scheduler.running:
            schedule.next_run_at = add_schedule(site_id, body.cron_expression)
        else:
            schedule.next_run_at = _compute_next_run(body.cron_expression)
    else:
        if scheduler.running:
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

    if scheduler.running:
        remove_schedule(site_id)

    await db.delete(schedule)
    await db.commit()
