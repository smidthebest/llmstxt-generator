import hashlib

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import PlainTextResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import GeneratedFile, Page, Site
from app.schemas.generated_file import GeneratedFileResponse, GeneratedFileUpdate
from app.services.generator import generate_llms_txt

router = APIRouter(prefix="/api/sites/{site_id}/llms-txt", tags=["generate"])


@router.get("", response_model=GeneratedFileResponse)
async def get_llms_txt(site_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(GeneratedFile)
        .where(GeneratedFile.site_id == site_id)
        .order_by(GeneratedFile.created_at.desc())
        .limit(1)
    )
    generated = result.scalar_one_or_none()
    if not generated:
        raise HTTPException(status_code=404, detail="No generated file found. Run a crawl first.")
    return generated


@router.put("", response_model=GeneratedFileResponse)
async def update_llms_txt(
    site_id: int, body: GeneratedFileUpdate, db: AsyncSession = Depends(get_db)
):
    result = await db.execute(
        select(GeneratedFile)
        .where(GeneratedFile.site_id == site_id)
        .order_by(GeneratedFile.created_at.desc())
        .limit(1)
    )
    generated = result.scalar_one_or_none()
    if not generated:
        raise HTTPException(status_code=404, detail="No generated file found")

    generated.content = body.content
    generated.content_hash = hashlib.sha256(body.content.encode()).hexdigest()
    generated.is_edited = True
    await db.commit()
    await db.refresh(generated)
    return generated


@router.get("/download")
async def download_llms_txt(site_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(GeneratedFile)
        .where(GeneratedFile.site_id == site_id)
        .order_by(GeneratedFile.created_at.desc())
        .limit(1)
    )
    generated = result.scalar_one_or_none()
    if not generated:
        raise HTTPException(status_code=404, detail="No generated file found")

    return PlainTextResponse(
        content=generated.content,
        media_type="text/plain",
        headers={"Content-Disposition": "attachment; filename=llms.txt"},
    )


@router.get("/history", response_model=list[GeneratedFileResponse])
async def get_history(site_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(GeneratedFile)
        .where(GeneratedFile.site_id == site_id)
        .order_by(GeneratedFile.created_at.desc())
        .limit(50)
    )
    return result.scalars().all()
