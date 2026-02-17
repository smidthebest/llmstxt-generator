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
