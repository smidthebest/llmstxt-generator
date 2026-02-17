from datetime import datetime

from pydantic import BaseModel, Field


class CrawlConfig(BaseModel):
    max_depth: int = Field(default=3, ge=1, le=5)
    max_pages: int = Field(default=200, ge=50, le=500)


class CrawlJobResponse(BaseModel):
    id: int
    site_id: int
    status: str
    pages_found: int
    pages_crawled: int
    pages_changed: int
    error_message: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
