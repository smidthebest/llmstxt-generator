from datetime import datetime

from pydantic import BaseModel, Field, HttpUrl


class SiteCreate(BaseModel):
    url: HttpUrl
    max_depth: int = Field(default=3, ge=1, le=5)
    max_pages: int = Field(default=200, ge=50, le=500)


class SiteResponse(BaseModel):
    id: int
    url: str
    domain: str
    title: str | None
    description: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class SiteListResponse(BaseModel):
    sites: list[SiteResponse]


class SiteOverviewResponse(BaseModel):
    site: SiteResponse
    latest_crawl_job_id: int | None = None
    latest_crawl_status: str | None = None
    latest_crawl_pages_crawled: int | None = None
    latest_crawl_pages_found: int | None = None
    latest_crawl_pages_changed: int | None = None
    latest_crawl_updated_at: datetime | None = None
    latest_crawl_error_message: str | None = None
    llms_generated: bool = False
    llms_generated_at: datetime | None = None
    llms_edited: bool = False
    schedule_active: bool = False
    schedule_cron_expression: str | None = None
    schedule_next_run_at: datetime | None = None


class SiteOverviewListResponse(BaseModel):
    sites: list[SiteOverviewResponse]
