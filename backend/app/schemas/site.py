from datetime import datetime

from pydantic import BaseModel, HttpUrl


class SiteCreate(BaseModel):
    url: HttpUrl


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
