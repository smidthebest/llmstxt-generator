from datetime import datetime

from pydantic import BaseModel


class GeneratedFileResponse(BaseModel):
    id: int
    site_id: int
    crawl_job_id: int | None
    content: str
    content_hash: str
    is_edited: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class GeneratedFileUpdate(BaseModel):
    content: str
