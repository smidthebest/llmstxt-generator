from datetime import datetime

from pydantic import BaseModel, Field


class CrawlConfig(BaseModel):
    max_depth: int = Field(default=3, ge=1, le=5)
    max_pages: int = Field(default=500, ge=50, le=500)


class CrawlJobResponse(BaseModel):
    id: int
    site_id: int
    status: str
    pages_found: int
    pages_crawled: int
    pages_changed: int
    pages_added: int
    pages_updated: int
    pages_removed: int
    pages_unchanged: int
    pages_skipped: int
    max_pages: int
    llms_regenerated: bool
    change_summary_json: dict | None
    error_message: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
