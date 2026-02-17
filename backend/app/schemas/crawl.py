from datetime import datetime

from pydantic import BaseModel


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
