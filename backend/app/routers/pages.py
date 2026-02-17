from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Page, Site
from app.schemas.page import PageResponse

router = APIRouter(prefix="/api/sites/{site_id}/pages", tags=["pages"])


@router.get("", response_model=list[PageResponse])
async def list_pages(site_id: int, db: AsyncSession = Depends(get_db)):
    site = await db.get(Site, site_id)
    if not site:
        raise HTTPException(status_code=404, detail="Site not found")

    result = await db.execute(
        select(Page)
        .where(Page.site_id == site_id)
        .order_by(Page.relevance_score.desc())
    )
    return result.scalars().all()
